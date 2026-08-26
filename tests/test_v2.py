"""Focused tests for the minimal independent V2 pipeline."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "v2"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MinimalV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = load("minimal_v2_core", V2 / "brief_v2.py")
        cls.runner = load("minimal_v2_runner", V2 / "run_v2.py")
        cls.renderer = load("minimal_v2_renderer", V2 / "render_report.py")
        cls.evaluator = load("minimal_v2_evaluator", V2 / "evaluate_outputs.py")

    def fixture_config(self, data_path: str = "items.json") -> dict:
        return {
            "schema_version": 1,
            "sources": {
                "wire": {
                    "driver": "json_file",
                    "path": data_path,
                    "items_path": "items",
                    "label": "NS",
                    "map": {
                        "title": ["title", "headline"],
                        "text": ["summary", "description"],
                        "url": ["url", "link"],
                        "publisher": "publisher",
                        "extra": {"category": "category"},
                    },
                }
            },
            "reports": {
                "noon-news": {
                    "sections": {
                        "international": [
                            {"source": "wire", "match": {"category": ["world"]}, "take": 2}
                        ],
                        "domestic": [{"source": "wire", "match": {"category": ["domestic"]}, "take": 1}],
                        "business": [{"source": "wire", "match": {"category": ["business"]}, "take": 1}],
                        "ai": [{"source": "wire", "match": {"category": ["ai"]}, "take": 2}],
                    }
                }
            },
        }

    def test_config_is_small_and_rejects_removed_dsl(self):
        config = self.fixture_config()
        self.core.validate_config(config)
        for field, value in (
            ("priority", 10),
            ("role", "fallback"),
            ("semantic_hints", {}),
            ("max_candidates", 10),
        ):
            broken = json.loads(json.dumps(config))
            if field == "semantic_hints":
                broken["reports"]["noon-news"]["sections"]["ai"] = {
                    "inputs": [], field: value
                }
            else:
                broken["reports"]["noon-news"]["sections"]["ai"][0][field] = value
            with self.assertRaises(ValueError):
                self.core.validate_config(broken)
        broken = json.loads(json.dumps(config))
        broken["reports"]["noon-news"]["contract"] = "noon-news-v2"
        with self.assertRaises(ValueError):
            self.core.validate_config(broken)

    def test_assemble_uses_exact_match_take_and_short_runtime_ids(self):
        data = {
            "items": [
                {"title": "World A", "summary": "A", "url": "https://a.test/1", "publisher": "BBC", "category": "world"},
                {"title": "World B", "summary": "B", "url": "https://a.test/2", "publisher": "NPR", "category": "world"},
                {"title": "World C", "summary": "C", "url": "https://a.test/3", "publisher": "AJ", "category": "world"},
                {"title": "AI A", "summary": "D", "url": "https://a.test/4", "publisher": "Lab", "category": "ai"},
            ]
        }
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "items.json").write_text(json.dumps(data), encoding="utf-8")
            assembled = self.core.assemble_report(self.fixture_config(), "noon-news", base)
        international = assembled["sections"]["international"]
        ids = [item["candidate_id"] for item in international]
        self.assertTrue(all(re.fullmatch(r"c[0-9a-f]{12}", value) for value in ids))
        self.assertEqual(len(set(ids)), 2)
        self.assertEqual([item["title"] for item in international], ["World A", "World B"])
        self.assertRegex(assembled["sections"]["ai"][0]["candidate_id"], r"^c[0-9a-f]{12}$")
        self.assertEqual(international[0]["provenance"][0]["label"], "NS")

    def test_candidate_id_is_stable_when_source_order_changes(self):
        first = {"title": "A", "summary": "one", "url": "https://a.test", "category": "world"}
        second = {"title": "B", "summary": "two", "url": "https://b.test", "category": "world"}
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            path = base / "items.json"
            path.write_text(json.dumps({"items": [first, second]}), encoding="utf-8")
            one = self.core.assemble_report(self.fixture_config(), "noon-news", base)
            path.write_text(json.dumps({"items": [second, first]}), encoding="utf-8")
            two = self.core.assemble_report(self.fixture_config(), "noon-news", base)
        ids_one = {item["title"]: item["candidate_id"] for item in one["sections"]["international"]}
        ids_two = {item["title"]: item["candidate_id"] for item in two["sections"]["international"]}
        self.assertEqual(ids_one, ids_two)

    def test_model_payload_hides_provenance_urls_and_deterministic_metrics(self):
        assembled = {
            "schema_version": 1,
            "report": "agents-report",
            "sections": {
                "ai_ecosystem": [{"candidate_id": "c001", "title": "A", "text": "B", "url": "https://a.test", "publisher": "P", "published_at": None, "extra": {}, "provenance": [{"label": "AIHOT", "url": "https://a.test"}]}],
                "model_efficiency": [{"candidate_id": "c002", "title": "m", "text": "", "url": "", "publisher": "", "published_at": None, "extra": {"ranking": "other"}, "provenance": []}],
                "open_source": [],
            },
        }
        payload = self.runner.build_model_payload(assembled)
        encoded = json.dumps(payload)
        self.assertNotIn("https://", encoded)
        self.assertNotIn("provenance", encoded)
        self.assertNotIn("model_efficiency", payload["sections"])
        self.assertEqual(set(payload["sections"]), {"ai_ecosystem"})

    def test_noon_model_payload_exposes_four_semantic_candidate_pools(self):
        assembled = {
            "report": "noon-news",
            "sections": {
                "international": [{"candidate_id": "c001", "title": "国际", "text": "事实", "extra": {}}],
                "domestic": [{"candidate_id": "c002", "title": "国内", "text": "事实", "extra": {}}],
                "business": [{"candidate_id": "c003", "title": "商业", "text": "事实", "extra": {}}],
                "ai": [{"candidate_id": "c004", "title": "AI", "text": "事实", "extra": {}}],
            },
        }
        payload = self.runner.build_model_payload(assembled)
        self.assertEqual(list(payload["sections"]), ["international", "domestic", "business", "ai"])
        self.assertEqual(payload["sections"]["domestic"][0]["candidate_id"], "c002")
        self.assertEqual(set(payload), {"sections"})

    def test_noon_model_payload_uses_lean_contract_without_redundant_instructions(self):
        assembled = {
            "report": "noon-news",
            "sections": {
                "international": [{"candidate_id": "c001", "title": "国际", "text": "事实", "extra": {}}],
                "domestic": [{"candidate_id": "c002", "title": "国内", "text": "事实", "extra": {}}],
                "business": [{"candidate_id": "c003", "title": "商业", "text": "事实", "extra": {}}],
                "ai": [{"candidate_id": "c004", "title": "AI", "text": "事实", "extra": {}}],
            },
        }
        payload = self.runner.build_model_payload(assembled)
        self.assertEqual(set(payload), {"sections"})
        self.assertEqual(set(payload["sections"]), {"international", "domestic", "business", "ai"})
        self.assertEqual(set(payload["sections"]["ai"][0]), {"candidate_id", "title", "text"})

    def test_build_model_prompt_does_not_duplicate_candidate_data_heading(self):
        prompt = self.runner.build_model_prompt(
            "规则\n\n## 候选数据\n",
            {"sections": {"ai": []}},
        )
        self.assertEqual(prompt.count("## 候选数据"), 1)

    def test_lean_noon_protocol_lets_program_own_item_ids(self):
        def candidate(candidate_id: str, title: str) -> dict:
            return {
                "candidate_id": candidate_id,
                "title": title,
                "text": f"{title} 的候选事实。",
                "url": f"https://example.test/{candidate_id}",
                "publisher": "媒体",
                "published_at": None,
                "extra": {},
                "provenance": [{"source_id": "wire", "label": "NS", "url": f"https://example.test/{candidate_id}"}],
            }

        sections = {
            "international": [candidate("c001", "国际事件")],
            "domestic": [candidate("c002", "国内事件")],
            "business": [candidate("c003", "商业事件")],
            "ai": [candidate("c004", "AI事件")],
        }
        model = {
            "top_points": [
                {"candidate_id": "c002", "topic": "国内", "fact": "国内事件出现进展"},
                {"candidate_id": "c001", "topic": "国际", "fact": "国际事件出现进展"},
                {"candidate_id": "c004", "topic": "AI", "fact": "AI事件出现进展"},
                {"candidate_id": "c003", "topic": "商业", "fact": "商业事件出现进展"},
            ],
            "sections": {
                "international": [{"candidate_id": "c001", "summary": "国际事件出现进展。", "headline_zh": "国际事件进展"}],
                "domestic": [{"candidate_id": "c002", "summary": "国内事件出现进展。", "headline_zh": "国内事件进展", "topic": "国内"}],
                "business": [{"candidate_id": "c003", "summary": "商业事件出现进展。", "headline_zh": "商业事件进展"}],
                "ai": [{"candidate_id": "c004", "summary": "AI事件出现进展。", "headline_zh": "AI事件进展"}],
            },
        }
        model["top_points"].extend([
            {"candidate_id": "c002", "topic": "国内", "fact": "国内事件重复要点"},
            {"candidate_id": "c001", "topic": "国际", "fact": "国际事件重复要点"},
        ])
        resolved = self.runner.resolve_semantic(
            {"report": "noon-news", "sections": sections},
            model,
            "2026-08-13",
            generated_at="2026-08-13T04:00:00+00:00",
        )
        self.assertEqual(len(resolved["top_points"]), 4)
        item = resolved["sections"]["domestic"][0]
        self.assertRegex(item["item_id"], r"^i[0-9a-f]{12}$")
        self.assertEqual(item["candidate_ids"], ["c002"])
        self.assertNotIn("why_it_matters", item)
        self.assertNotIn("evidence_level", item)
        self.assertEqual(resolved["top_points"][0]["item_ids"], [item["item_id"]])
        markdown = self.runner.render_resolved(resolved)
        self.assertIn("国内事件出现进展", markdown)

    def test_lean_noon_protocol_rejects_multi_candidate_detail(self):
        candidate = {
            "candidate_id": "c001",
            "title": "事件",
            "text": "候选事实",
            "url": "https://example.test/a",
            "publisher": "媒体",
            "published_at": None,
            "extra": {},
            "provenance": [{"source_id": "wire", "label": "NS", "url": "https://example.test/a"}],
        }
        assembled = {
            "report": "noon-news",
            "sections": {"international": [candidate], "domestic": [], "business": [], "ai": []},
        }
        model = {
            "top_points": [{"candidate_id": "c001", "topic": "国际", "fact": "事件"}] * 4,
            "sections": {
                "international": [{"candidate_id": ["c001", "c001"], "summary": "事件"}],
                "domestic": [],
                "business": [],
                "ai": [],
            },
        }
        with self.assertRaisesRegex(ValueError, "candidate_id"):
            self.runner.resolve_semantic(assembled, model, None)

    def test_lean_noon_protocol_keeps_numeric_fact_guard(self):
        candidate = {
            "candidate_id": "c001",
            "title": "The U.S. imposed tariffs on $20 billion of goods",
            "text": "",
            "url": "https://example.test/a",
            "publisher": "媒体",
            "published_at": None,
            "extra": {},
            "provenance": [{"source_id": "wire", "label": "NS", "url": "https://example.test/a"}],
        }
        assembled = {
            "report": "noon-news",
            "sections": {"international": [candidate], "domestic": [], "business": [], "ai": []},
        }
        model = {
            "top_points": [{"candidate_id": "c001", "topic": "贸易", "fact": "关税措施"}],
            "sections": {
                "international": [{"candidate_id": "c001", "summary": "涉及约500亿加元商品"}],
                "domestic": [],
                "business": [],
                "ai": [],
            },
        }
        with self.assertRaisesRegex(ValueError, "numeric claim"):
            self.runner.resolve_semantic(assembled, model, None)

    def test_resolver_recovers_sources_projects_metrics_and_date(self):
        assembled = {
            "schema_version": 1,
            "report": "agents-report",
            "sections": {
                "ai_ecosystem": [{"candidate_id": "c001", "title": "News", "text": "Evidence", "url": "https://news.test/a", "publisher": "Verge", "published_at": None, "extra": {}, "provenance": [{"source_id": "ai", "label": "AIHOT", "publisher": "Verge", "url": "https://news.test/a"}]}],
                "model_efficiency": [{"candidate_id": "c002", "title": "gpt-x", "text": "", "url": "", "publisher": "", "published_at": None, "extra": {"ranking": "intelligence_top2", "effort": "high", "iq": 99.0, "average_minutes": 10.0, "average_price_usd": 1.25}, "provenance": []}],
                "open_source": [
                    {"candidate_id": "c005", "title": "", "text": "趋势一", "url": "", "publisher": "", "published_at": None, "extra": {"kind": "trend"}, "provenance": []},
                    {"candidate_id": "c006", "title": "", "text": "趋势二", "url": "", "publisher": "", "published_at": None, "extra": {"kind": "trend"}, "provenance": []},
                    {"candidate_id": "c003", "title": "o/r", "text": "Repo", "url": "https://github.com/o/r", "publisher": "", "published_at": None, "extra": {"kind": "project", "role": "hot", "stars_today": 1138, "category": "Tools"}, "provenance": [{"source_id": "radar", "label": "Radar", "url": "https://github.com/o/r"}]},
                    {"candidate_id": "c004", "title": "o/s", "text": "Repo 2", "url": "https://github.com/o/s", "publisher": "", "published_at": None, "extra": {"kind": "project", "role": "other", "category": "Tools"}, "provenance": [{"source_id": "radar", "label": "Radar", "url": "https://github.com/o/s"}]},
                ],
            },
        }
        model = {
            "report": "agents-report",
            "sections": {
                "ai_ecosystem": [{"summary": "生态摘要", "candidate_ids": ["c001"]}],

            },
        }
        resolved = self.runner.resolve_semantic(assembled, model, "2026-08-12")
        self.assertEqual(resolved["date"], "2026-08-12")
        self.assertEqual(resolved["sections"]["ai_ecosystem"][0]["sources"][0]["url"], "https://news.test/a")
        metric = resolved["sections"]["model_efficiency"]["intelligence_top2"][0]
        self.assertEqual(metric, {"model": "gpt-x", "effort": "high", "iq": 99.0, "minutes": 10.0, "price_usd": 1.25})
        category = resolved["sections"]["open_source"]["categories"][0]
        self.assertEqual(category["hot_projects"][0]["url"], "https://github.com/o/r")
        self.assertEqual(category["hot_projects"][0]["stars_today"], 1138)
        self.assertEqual(category["other_projects"][0]["name"], "o/s")
        markdown = self.renderer.render_report(resolved)
        self.assertIn("（+1,138★/日）", markdown)
        self.assertNotIn("candidate_ids", resolved["sections"]["ai_ecosystem"][0])

    def test_unknown_or_wrong_section_candidate_id_is_rejected(self):
        assembled = {"report": "noon-news", "sections": {"international": [], "domestic": [], "business": [], "ai": []}}
        model = {
            "report": "noon-news",
            "top_points": [
                {"candidate_ids": ["c999"], "topic": "国际", "fact": "事实"},
            ] * 4,
            "sections": {
                "international": [{"summary": "y", "candidate_ids": ["c999"]}],
                "domestic": [],
                "business": [],
                "ai": [],
            },
        }
        with self.assertRaisesRegex(ValueError, "unknown candidate_id"):
            self.runner.resolve_semantic(assembled, model, None)

    def test_noon_limits_and_top_points_are_deterministic(self):
        sections = {name: [] for name in ("international", "domestic", "business", "ai")}
        model_sections = {name: [] for name in sections}
        counts = {"international": 7, "domestic": 2, "business": 5, "ai": 6}
        section_labels = {"international": "国际", "domestic": "国内", "business": "商业", "ai": "AI"}
        number = 0
        for section, count in counts.items():
            for index in range(count):
                number += 1
                candidate_id = f"c{number:03d}"
                sections[section].append({
                    "candidate_id": candidate_id,
                    "title": f"{section}-{index}",
                    "text": "evidence",
                    "url": f"https://example.test/{number}",
                    "publisher": "",
                    "published_at": None,
                    "extra": {},
                    "provenance": [{"source_id": "s", "label": "S", "url": f"https://example.test/{number}"}],
                })
                model_sections[section].append({
                    "item_ref": f"item-{number}",
                    "candidate_ids": [candidate_id],
                    "summary": f"{section_labels[section]}重点摘要",
                    "headline_zh": "",
                    "why_it_matters": "候选材料提供了背景",
                    "evidence_level": "direct",
                })
        model_top_points = [
            {"item_refs": ["item-1"], "topic": "国际", "fact": "国际重点"},
            {"item_refs": ["item-8"], "topic": "国内", "fact": "国内重点"},
            {"item_refs": ["item-10"], "topic": "商业", "fact": "商业重点"},
            {"item_refs": ["item-15"], "topic": "人工智能", "fact": "AI重点"},
        ]
        resolved = self.runner.resolve_semantic(
            {"report": "noon-news", "sections": sections},
            {
                "protocol": self.runner.NOON_MODEL_PROTOCOL,
                "report": "noon-news",
                "top_points": model_top_points,
                "sections": model_sections,
            },
            None,
        )
        self.assertEqual({key: len(value) for key, value in resolved["sections"].items()}, {"international": 5, "domestic": 2, "business": 3, "ai": 4})
        self.assertEqual([point["topic"] for point in resolved["top_points"]], ["国际", "国内", "商业", "人工智能"])

    def test_noon_semantic_protocol_has_explicit_traceable_top_points_and_domestic(self):
        def candidate(candidate_id: str, title: str) -> dict:
            return {
                "candidate_id": candidate_id,
                "title": title,
                "text": "候选事实证据",
                "url": f"https://example.test/{candidate_id}",
                "publisher": "媒体",
                "published_at": None,
                "extra": {},
                "provenance": [{"source_id": "wire", "label": "NS", "url": f"https://example.test/{candidate_id}"}],
            }

        assembled = {
            "report": "noon-news",
            "sections": {
                "international": [candidate("c001", "国际事件")],
                "domestic": [candidate("c002", "国内事件")],
                "business": [candidate("c003", "商业事件")],
                "ai": [candidate("c004", "AI事件")],
            },
        }
        model = {
            "report": "noon-news",
            "top_points": [
                {"candidate_ids": ["c002"], "topic": "国内", "fact": "国内事件受到关注"},
                {"candidate_ids": ["c001"], "topic": "国际", "fact": "国际事件出现最新进展"},
                {"candidate_ids": ["c004"], "topic": "人工智能", "fact": "AI事件发布最新消息"},
                {"candidate_ids": ["c003"], "topic": "商业", "fact": "商业事件影响市场"},
            ],
            "sections": {
                "international": [{"candidate_ids": ["c001"], "summary": "国际事件出现最新进展，候选材料提供了可核对的事实证据。"}],
                "domestic": [{"candidate_ids": ["c002"], "summary": "国内事件受到关注，候选材料提供了可核对的事实证据。"}],
                "business": [{"candidate_ids": ["c003"], "summary": "商业事件影响市场，候选材料提供了可核对的事实证据。"}],
                "ai": [{"candidate_ids": ["c004"], "summary": "AI事件发布最新消息，候选材料提供了可核对的事实证据。"}],
            },
        }
        resolved = self.runner.resolve_semantic(assembled, model, None)
        self.assertEqual(list(resolved["sections"]), ["international", "domestic", "business", "ai"])
        self.assertEqual(resolved["top_points"][0]["topic"], "国内")
        self.assertEqual(resolved["top_points"][0]["fact"], "国内事件受到关注")

    def test_top_point_fact_accepts_compact_fact_over_legacy_40_limit(self):
        fact = "中国" * 21
        self.assertEqual(self.runner._top_fact(fact, "top_points[0].fact"), fact)

    def test_noon_semantic_protocol_rejects_missing_or_unknown_top_point_references(self):
        assembled = {
            "report": "noon-news",
            "sections": {"international": [], "domestic": [], "business": [], "ai": []},
        }
        base = {
            "report": "noon-news",
            "sections": {"international": [], "domestic": [], "business": [], "ai": []},
        }
        with self.assertRaisesRegex(ValueError, "top_points"):
            self.runner.resolve_semantic(assembled, base, None)
        invalid = {
            **base,
            "top_points": [
                {"candidate_ids": ["c404"], "topic": "国际", "fact": "无法追溯的事实"},
            ] * 4,
        }
        with self.assertRaisesRegex(ValueError, "unknown candidate_id"):
            self.runner.resolve_semantic(assembled, invalid, None)

    def test_noon_semantic_protocol_rejects_source_or_url_in_top_point_fact(self):
        candidate = {
            "candidate_id": "c001",
            "title": "Title",
            "text": "Evidence",
            "url": "https://example.test/a",
            "publisher": "",
            "published_at": None,
            "extra": {},
            "provenance": [{"source_id": "s", "label": "S", "url": "https://example.test/a"}],
        }
        assembled = {
            "report": "noon-news",
            "sections": {"international": [candidate], "domestic": [], "business": [], "ai": []},
        }
        model = {
            "report": "noon-news",
            "top_points": [
                {"candidate_ids": ["c001"], "topic": "国际", "fact": "来源http://x"},
            ] * 4,
            "sections": {
                "international": [{"candidate_ids": ["c001"], "summary": "事实"}],
                "domestic": [], "business": [], "ai": [],
            },
        }
        with self.assertRaisesRegex(ValueError, "source-free fact"):
            self.runner.resolve_semantic(assembled, model, None)

    def test_noon_semantic_protocol_rejects_unsupported_numeric_claim(self):
        candidate = {
            "candidate_id": "c001",
            "title": "English headline",
            "text": "政策声明将继续执行。",
            "url": "https://example.test/a",
            "publisher": "媒体",
            "published_at": "2026-08-13T01:00:00Z",
            "extra": {},
            "provenance": [{"source_id": "s", "label": "NS", "url": "https://example.test/a"}],
        }
        assembled = {
            "report": "noon-news",
            "sections": {"international": [candidate], "domestic": [], "business": [], "ai": []},
        }
        detail = {
            "candidate_ids": ["c001"],
            "summary": "政策声明将继续执行。",
            "headline_zh": "政策声明",
            "why_it_matters": "候选材料未提供更多影响信息。",
            "evidence_level": "direct",
        }
        model = {
            "report": "noon-news",
            "top_points": [{"candidate_ids": ["c001"], "topic": "政策", "fact": "政策涉及100亿元"}] * 4,
            "sections": {"international": [detail], "domestic": [], "business": [], "ai": []},
        }
        with self.assertRaisesRegex(ValueError, "numeric claim"):
            self.runner.resolve_semantic(assembled, model, "2026-08-13")

    def test_noon_semantic_protocol_accepts_comma_normalized_supported_number(self):
        candidate = {
            "candidate_id": "c001",
            "title": "Outbreak has caused more than 2,000 deaths",
            "text": "The outbreak has caused more than 2,000 deaths.",
            "url": "https://example.test/a",
            "publisher": "Example Media",
            "published_at": "2026-08-13T01:00:00Z",
            "extra": {},
            "provenance": [{"source_id": "s", "label": "NS", "url": "https://example.test/a"}],
        }
        assembled = {
            "report": "noon-news",
            "sections": {"international": [candidate], "domestic": [], "business": [], "ai": []},
        }
        detail = {
            "candidate_ids": ["c001"],
            "summary": "疫情已造成超过2000人死亡。",
            "headline_zh": "疫情造成2000人死亡",
            "why_it_matters": "候选材料未提供更多影响信息。",
            "evidence_level": "direct",
        }
        model = {
            "report": "noon-news",
            "top_points": [{"candidate_ids": ["c001"], "topic": "国际", "fact": "疫情造成2000人死亡"}] * 4,
            "sections": {"international": [detail], "domestic": [], "business": [], "ai": []},
        }
        resolved = self.runner.resolve_semantic(assembled, model, "2026-08-13")
        self.assertEqual(resolved["sections"]["international"][0]["summary"], "疫情已造成超过2000人死亡。")

    def test_noon_semantic_protocol_accepts_localized_date_format(self):
        candidate = {
            "candidate_id": "c001",
            "title": "Outbreak declared on 15 May",
            "text": "The outbreak was declared on 15 May.",
            "url": "https://example.test/a",
            "publisher": "Example Media",
            "published_at": "2026-08-13T01:00:00Z",
            "extra": {},
            "provenance": [{"source_id": "s", "label": "NS", "url": "https://example.test/a"}],
        }
        assembled = {
            "report": "noon-news",
            "sections": {"international": [candidate], "domestic": [], "business": [], "ai": []},
        }
        detail = {
            "candidate_ids": ["c001"],
            "summary": "疫情于5月15日宣布。",
            "headline_zh": "疫情宣布",
            "why_it_matters": "候选材料未提供更多影响信息。",
            "evidence_level": "direct",
        }
        model = {
            "report": "noon-news",
            "top_points": [{"candidate_ids": ["c001"], "topic": "国际", "fact": "疫情已宣布"}] * 4,
            "sections": {"international": [detail], "domestic": [], "business": [], "ai": []},
        }
        resolved = self.runner.resolve_semantic(assembled, model, "2026-08-13")
        self.assertEqual(resolved["sections"]["international"][0]["summary"], "疫情于5月15日宣布。")

    def test_numeric_evidence_accepts_abbreviated_english_month_date(self):
        candidates = [{"title": "Tariffs start Sept. 8", "text": "Starting Sept. 8.", "extra": {}}]
        self.runner._check_supported_numbers("关税将自9月8日起实施", "summary", candidates)

    def test_numeric_evidence_accepts_equivalent_percent_wording(self):
        candidates = [{"title": "Fatality rate", "text": "Nearly 48 percent", "extra": {}}]
        self.runner._check_supported_numbers("致死率近48%", "summary", candidates)
        with self.assertRaisesRegex(ValueError, "47%"):
            self.runner._check_supported_numbers("致死率近47%", "summary", candidates)

    def test_noon_topic_allows_compact_mixed_alphanumeric_label(self):
        self.assertIsNotNone(self.runner._TOPIC_RE.fullmatch("A股港股"))
        self.assertIsNone(self.runner._TOPIC_RE.fullmatch("A 股港股"))

    def test_noon_semantic_protocol_accepts_localized_month_format(self):
        candidate = {
            "candidate_id": "c001",
            "title": "Inflation was lower than in May or June",
            "text": "Consumer prices were lower than in May or June.",
            "url": "https://example.test/a",
            "publisher": "Example Media",
            "published_at": "2026-08-13T01:00:00Z",
            "extra": {},
            "provenance": [{"source_id": "s", "label": "NS", "url": "https://example.test/a"}],
        }
        assembled = {
            "report": "noon-news",
            "sections": {"international": [candidate], "domestic": [], "business": [], "ai": []},
        }
        detail = {
            "candidate_ids": ["c001"],
            "summary": "通胀低于5月和6月水平。",
            "headline_zh": "通胀回落",
            "why_it_matters": "候选材料未提供更多影响信息。",
            "evidence_level": "direct",
        }
        model = {
            "report": "noon-news",
            "top_points": [{"candidate_ids": ["c001"], "topic": "商业", "fact": "通胀回落"}] * 4,
            "sections": {"international": [detail], "domestic": [], "business": [], "ai": []},
        }
        resolved = self.runner.resolve_semantic(assembled, model, "2026-08-13")
        self.assertEqual(resolved["sections"]["international"][0]["summary"], "通胀低于5月和6月水平。")

    def test_noon_semantic_protocol_accepts_fullwidth_grouped_number(self):
        candidate = {
            "candidate_id": "c001",
            "title": "Model supports 262，144 tokens",
            "text": "The context window supports 262，144 tokens.",
            "url": "https://example.test/a",
            "publisher": "Example Media",
            "published_at": "2026-08-13T01:00:00Z",
            "extra": {},
            "provenance": [{"source_id": "s", "label": "NS", "url": "https://example.test/a"}],
        }
        assembled = {
            "report": "noon-news",
            "sections": {"international": [candidate], "domestic": [], "business": [], "ai": []},
        }
        detail = {
            "candidate_ids": ["c001"],
            "summary": "模型支持262144个Token上下文。",
            "headline_zh": "模型支持长上下文",
            "why_it_matters": "候选材料未提供更多影响信息。",
            "evidence_level": "direct",
        }
        model = {
            "report": "noon-news",
            "top_points": [{"candidate_ids": ["c001"], "topic": "人工智能", "fact": "模型支持长上下文"}] * 4,
            "sections": {"international": [detail], "domestic": [], "business": [], "ai": []},
        }
        resolved = self.runner.resolve_semantic(assembled, model, "2026-08-13")
        self.assertEqual(resolved["sections"]["international"][0]["summary"], "模型支持262144个Token上下文。")

    def test_top_point_fact_requires_anchor_in_referenced_detail(self):
        self.runner._check_top_point_anchor(
            "朱镕基逝世，享年97岁",
            "前国务院总理朱镕基因病逝世，享年97岁",
            "top_points[0].fact",
        )
        with self.assertRaisesRegex(ValueError, "does not match referenced detail"):
            self.runner._check_top_point_anchor(
                "泽连斯基称乌军取得重大进展",
                "世卫组织称埃博拉疫情已造成逾2000人死亡",
                "top_points[0].fact",
            )

    def test_numeric_suffix_before_chinese_text_is_scaled(self):
        scaled = "1500000000000"
        self.assertIn(scaled, self.runner._number_keys("模型拥有1.5T参数"))
        self.assertIn(scaled, self.runner._number_keys("规模为1.5T，现已发布"))
        self.runner._check_supported_numbers(
            "约4.2 万人疏散，另有4.5 万人收到警报",
            "summary",
            [{"title": "42,000 people evacuated and 45,000 on alert", "text": "", "extra": {}}],
        )

    def test_numeric_evidence_accepts_equivalent_million_notation(self):
        candidates = [{"title": "Plan costs up to $20m", "text": "Evidence", "extra": {}}]
        self.runner._check_supported_numbers("计划采购最高2000万美元设备", "summary", candidates)
        with self.assertRaisesRegex(ValueError, "30000000"):
            self.runner._check_supported_numbers("计划采购最高3000万美元设备", "summary", candidates)

    def test_numeric_evidence_accepts_chinese_yi_notation(self):
        candidates = [{"title": "The U.S. imposed tariffs on $20 billion of goods", "text": "", "extra": {}}]
        self.runner._check_supported_numbers("涉及约200亿加元商品", "summary", candidates)
        short_candidates = [{"title": "Shein aims for almost $27bn valuation", "text": "", "extra": {}}]
        self.runner._check_supported_numbers("估值接近270亿美元", "summary", short_candidates)

    def test_numeric_evidence_accepts_equivalent_decade_notation(self):
        candidates = [{"title": "China's 1990s economic reforms", "text": "Evidence", "extra": {}}]
        self.runner._check_supported_numbers("上世纪90年代的市场化改革", "summary", candidates)
        with self.assertRaisesRegex(ValueError, "80"):
            self.runner._check_supported_numbers("上世纪80年代的市场化改革", "summary", candidates)

    def test_noon_semantic_protocol_accepts_chinese_number_unit(self):
        candidate = {
            "candidate_id": "c001",
            "title": "Model can scale to 1，010，000 tokens",
            "text": "The model can scale to 1，010，000 tokens.",
            "url": "https://example.test/a",
            "publisher": "Example Media",
            "published_at": "2026-08-13T01:00:00Z",
            "extra": {},
            "provenance": [{"source_id": "s", "label": "NS", "url": "https://example.test/a"}],
        }
        assembled = {
            "report": "noon-news",
            "sections": {"international": [candidate], "domestic": [], "business": [], "ai": []},
        }
        detail = {
            "candidate_ids": ["c001"],
            "summary": "模型可扩展至101万Token上下文。",
            "headline_zh": "模型支持长上下文",
            "why_it_matters": "候选材料未提供更多影响信息。",
            "evidence_level": "direct",
        }
        model = {
            "report": "noon-news",
            "top_points": [{"candidate_ids": ["c001"], "topic": "人工智能", "fact": "模型支持长上下文"}] * 4,
            "sections": {"international": [detail], "domestic": [], "business": [], "ai": []},
        }
        resolved = self.runner.resolve_semantic(assembled, model, "2026-08-13")
        self.assertEqual(resolved["sections"]["international"][0]["summary"], "模型可扩展至101万Token上下文。")

    def test_noon_semantic_protocol_allows_program_fallback_for_optional_short_headline(self):
        candidates = [
            {
                "candidate_id": f"c00{index}",
                "title": f"Original title {index}",
                "text": f"Evidence {index}",
                "url": f"https://example.test/{index}",
                "publisher": "Example Media",
                "published_at": "2026-08-13T01:00:00Z",
                "extra": {},
                "provenance": [
                    {"source_id": "s", "label": "NS", "url": f"https://example.test/{index}"}
                ],
            }
            for index in range(1, 5)
        ]
        assembled = {
            "report": "noon-news",
            "sections": {"international": candidates, "domestic": [], "business": [], "ai": []},
        }
        details = [
            {
                "candidate_ids": [f"c00{index}"],
                "item_ref": f"item-0{index}",
                "summary": f"证据{index}",
                "headline_zh": "" if index == 1 else f"短题{index}",
                "why_it_matters": "候选材料未提供更多影响信息。",
                "evidence_level": "direct",
            }
            for index in range(1, 5)
        ]
        model = {
            "protocol": self.runner.NOON_MODEL_PROTOCOL,
            "report": "noon-news",
            "top_points": [
                {"item_refs": [f"item-0{index}"], "topic": "国际", "fact": f"事实{index}"}
                for index in range(1, 5)
            ],
            "sections": {"international": details, "domestic": [], "business": [], "ai": []},
        }
        resolved = self.runner.resolve_semantic(assembled, model, "2026-08-13")
        self.assertEqual(resolved["sections"]["international"][0]["headline_zh"], "")

    def test_noon_semantic_protocol_preserves_traceability_and_recovered_metadata(self):
        candidate = {
            "candidate_id": "c001",
            "title": "English headline",
            "text": "The agency announced a policy statement.",
            "url": "https://example.test/a",
            "publisher": "Example Media",
            "published_at": "2026-08-13T01:00:00Z",
            "extra": {},
            "provenance": [{"source_id": "s", "label": "NS", "publisher": "Example Media", "url": "https://example.test/a"}],
        }
        assembled = {
            "report": "noon-news",
            "sections": {"international": [candidate], "domestic": [], "business": [], "ai": []},
        }
        detail = {
            "candidate_ids": ["c001"],
            "summary": "机构发布政策声明。",
            "headline_zh": "机构发布政策声明",
            "why_it_matters": "这是候选材料明确支持的事件。",
            "evidence_level": "direct",
        }
        model = {
            "report": "noon-news",
            "top_points": [{"candidate_ids": ["c001"], "topic": "政策", "fact": "机构发布声明"}] * 4,
            "sections": {"international": [detail], "domestic": [], "business": [], "ai": []},
        }
        resolved = self.runner.resolve_semantic(assembled, model, "2026-08-13", generated_at="2026-08-13T04:00:00+00:00")
        item = resolved["sections"]["international"][0]
        self.assertEqual(resolved["semantic_protocol"], "glance_brief.noon-news.v2")
        self.assertEqual(resolved["report_date"], "2026-08-13")
        self.assertEqual(resolved["generated_at"], "2026-08-13T04:00:00+00:00")
        self.assertRegex(item["item_id"], r"^i[0-9a-f]{12}$")
        self.assertEqual(item["candidate_ids"], ["c001"])
        self.assertEqual(item["headline"], "English headline")
        self.assertEqual(item["headline_zh"], "机构发布政策声明")
        self.assertEqual(item["published_at"], "2026-08-13T01:00:00Z")
        self.assertEqual(resolved["top_points"][0]["item_ids"], [item["item_id"]])
        markdown = self.runner.render_resolved(resolved)
        self.assertIn("**English headline**（机构发布政策声明）", markdown)

    def test_noon_strict_model_protocol_uses_item_refs_for_global_top_points(self):
        def candidate(candidate_id: str, section: str, title: str) -> dict:
            return {
                "candidate_id": candidate_id,
                "title": title,
                "text": f"{section} 候选明确事实。",
                "url": f"https://example.test/{candidate_id}",
                "publisher": "媒体",
                "published_at": "2026-08-13T01:00:00Z",
                "extra": {},
                "provenance": [{"source_id": "wire", "label": "NS", "url": f"https://example.test/{candidate_id}"}],
            }

        sections = {
            "international": [candidate("c001", "国际", "国际事件")],
            "domestic": [candidate("c002", "国内", "国内事件")],
            "business": [candidate("c003", "商业", "商业事件")],
            "ai": [candidate("c004", "AI", "AI事件")],
        }
        sections["ai"][0]["text"] = "阿里开源Qwen3.8-2.4T，2.4T参数MoE原生支持256K上下文"
        details = {
            "international": [{"item_ref": "int-01", "candidate_ids": ["c001"], "summary": "国际事件出现进展。", "headline_zh": "国际事件进展", "why_it_matters": "候选材料明确给出该事件。", "evidence_level": "direct"}],
            "domestic": [{"item_ref": "dom-01", "candidate_ids": ["c002"], "summary": "国内事件出现进展。", "headline_zh": "国内事件进展", "why_it_matters": "候选材料明确给出该事件。", "evidence_level": "direct"}],
            "business": [{"item_ref": "biz-01", "candidate_ids": ["c003"], "summary": "商业事件出现进展。", "headline_zh": "商业事件进展", "why_it_matters": "候选材料明确给出该事件。", "evidence_level": "direct"}],
            "ai": [{"item_ref": "ai-01", "candidate_ids": ["c004"], "summary": "AI事件出现进展。", "headline_zh": "AI事件进展", "why_it_matters": "候选材料明确给出该事件。", "evidence_level": "direct"}],
        }
        model = {
            "protocol": "glance_brief.noon-news.model.v2",
            "report": "noon-news",
            "top_points": [
                {"item_refs": ["dom-01"], "topic": "国内", "fact": "国内事件出现进展"},
                {"item_refs": ["int-01"], "topic": "国际", "fact": "国际事件出现进展"},
                {
                    "item_refs": ["ai-01"],
                    "topic": "AI",
                    "fact": "阿里开源Qwen3.8-2.4T，2.4T参数MoE原生支持256K上下文",
                },
                {"item_refs": ["biz-01"], "topic": "商业", "fact": "商业事件出现进展"},
            ],
            "sections": details,
        }
        resolved = self.runner.resolve_semantic(
            {"report": "noon-news", "sections": sections},
            model,
            "2026-08-13",
            generated_at="2026-08-13T04:00:00+00:00",
        )
        self.assertEqual(resolved["top_points"][0]["item_ids"], [resolved["sections"]["domestic"][0]["item_id"]])
        self.assertEqual(resolved["sections"]["domestic"][0]["candidate_ids"], ["c002"])
        self.assertEqual(
            resolved["top_points"][2]["fact"],
            "阿里开源Qwen3.8-2.4T，2.4T参数MoE原生支持256K上下文",
        )

    def test_noon_summary_preserves_moderate_overage_without_truncation(self):
        candidate = {
            "candidate_id": "c001",
            "title": "Title",
            "text": "Evidence",
            "url": "https://example.test/a",
            "publisher": "",
            "published_at": None,
            "extra": {},
            "provenance": [{"source_id": "s", "label": "S", "url": "https://example.test/a"}],
        }
        assembled = {
            "report": "noon-news",
            "sections": {"international": [candidate], "domestic": [], "business": [], "ai": []},
        }
        model = {
            "report": "noon-news",
            "top_points": [
                {"candidate_ids": ["c001"], "topic": "国际", "fact": "事实"},
            ] * 4,
            "sections": {
                "international": [{"candidate_ids": ["c001"], "summary": "长" * 101}],
                "domestic": [],
                "business": [],
                "ai": [],
            },
        }
        resolved = self.runner.resolve_semantic(assembled, model, None)
        summary = resolved["sections"]["international"][0]["summary"]
        self.assertEqual(summary, "长" * 101)

        model["sections"]["international"][0]["summary"] = "长" * 141
        with self.assertRaisesRegex(ValueError, "at most 140"):
            self.runner.resolve_semantic(assembled, model, None)

    def test_renderer_owns_visible_markdown(self):
        noon = {
            "report": "noon-news",
            "top_points": [
                {"topic": "市场", "fact": "核心事实"},
                {"topic": "国际", "fact": "国际事实"},
                {"topic": "国内", "fact": "国内事实"},
                {"topic": "人工智能", "fact": "AI事实"},
            ],
            "sections": {
                "international": [{"title": "Title", "summary": "事实", "sources": [{"label": "NS", "publisher": "BBC", "url": "https://bbc.test/a"}]}],
                "domestic": [],
                "business": [],
                "ai": [],
            },
        }
        markdown = self.renderer.render_report(noon)
        self.assertTrue(markdown.startswith("📰 今日热点简报\n"))
        self.assertIn("**① 国际要闻**", markdown)
        self.assertIn("**② 国内要闻**", markdown)
        self.assertIn("> 来源：[NS•BBC](https://bbc.test/a)", markdown)
        self.assertNotIn("candidate_id", markdown)

    def test_noon_renderer_groups_same_channel_and_limits_by_channel(self):
        noon = {
            "report": "noon-news",
            "top_points": [
                {"topic": "市场", "fact": "核心事实"},
                {"topic": "国际", "fact": "国际事实"},
                {"topic": "国内", "fact": "国内事实"},
                {"topic": "AI", "fact": "人工智能事实"},
            ],
            "sections": {
                "international": [
                    {
                        "title": "Title",
                        "summary": "事实",
                        "sources": [
                            {"label": "NS", "publisher": "BBC（RSS） (@BBC)", "url": "https://bbc.test/a"},
                            {"label": "NS", "publisher": "NPR", "url": "https://npr.test/a"},
                            {"label": "NA", "publisher": "Tencent News", "url": "https://qq.test/a"},
                            {"label": "AIHOT", "publisher": "IT之家（RSS）", "url": "https://ithome.test/a"},
                        ],
                    }
                ],
                "domestic": [],
                "business": [],
                "ai": [],
            },
        }
        markdown = self.renderer.render_report(noon)
        self.assertIn(
            "> 来源：[NS•BBC](https://bbc.test/a)•[NPR](https://npr.test/a)•[NA•Tencent News](https://qq.test/a) +1",
            markdown,
        )
        self.assertNotIn("[NS•NPR]", markdown)
        self.assertNotIn("IT之家", markdown)

    def test_noon_renderer_only_adds_short_headline_for_english_title(self):
        noon = {
            "report": "noon-news",
            "top_points": [
                {"topic": "市场", "fact": "核心事实"},
                {"topic": "国际", "fact": "国际事实"},
                {"topic": "国内", "fact": "国内事实"},
                {"topic": "AI", "fact": "人工智能事实"},
            ],
            "sections": {
                "international": [
                    {
                        "title": "English title",
                        "headline_zh": "英文短题",
                        "summary": "事实",
                        "sources": [{"label": "NS", "publisher": "BBC", "url": "https://bbc.test/a"}],
                    }
                ],
                "domestic": [
                    {
                        "title": "中文原标题",
                        "headline_zh": "重复短题",
                        "summary": "事实",
                        "sources": [{"label": "NA", "publisher": "腾讯新闻", "url": "https://qq.test/a"}],
                    }
                ],
                "business": [],
                "ai": [],
            },
        }
        markdown = self.renderer.render_report(noon)
        self.assertIn("- **English title**（英文短题）", markdown)
        self.assertIn("- **中文原标题**", markdown)
        self.assertNotIn("重复短题", markdown)

    def test_noon_evaluator_requires_all_four_current_sections(self):
        complete = "\n".join(
            (
                "📰 今日热点简报",
                "### 今日要点",
                "1. 国际：事实",
                "2. 国内：事实",
                "3. 商业：事实",
                "4. AI：事实",
                "### 分类详情",
                "**① 国际要闻**",
                "**② 国内要闻**",
                "**③ 宏观与商业**",
                "**④ AI 主线**",
            )
        )
        incomplete = complete.replace("**② 国内要闻**\n", "")
        self.assertTrue(self.evaluator.markdown_metrics(complete, "noon-news")["contract_complete"])
        self.assertFalse(self.evaluator.markdown_metrics(incomplete, "noon-news")["contract_complete"])

    def test_example_config_uses_single_cli(self):
        config = V2 / "config" / "brief.example.json"
        completed = subprocess.run(
            [sys.executable, str(V2 / "run_v2.py"), "check", "--config", str(config)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("configuration ok", completed.stdout)


if __name__ == "__main__":
    unittest.main()
