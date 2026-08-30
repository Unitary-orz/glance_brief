from __future__ import annotations

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v2 import adapters, contracts, render_report, resolve


class NoonCurrentContractTests(unittest.TestCase):
    def test_noon_uses_three_current_sections_and_no_separator(self):
        semantic = {
            "schema_version": 2,
            "report": "noon-news",
            "report_date": "2026-08-30",
            "generated_at": "2026-08-30T04:00:00+00:00",
            "top_points": [
                {"candidate_id": "c1111111111111111", "topic": "国际", "fact": "国际事件出现进展"},
                {"candidate_id": "c2222222222222222", "topic": "商业", "fact": "市场发布最新数据"},
            ],
            "sections": {
                "international": [
                    {
                        "candidate_id": "c1111111111111111",
                        "headline": "International event advances",
                        "headline_zh": "国际事件取得新进展",
                        "summary": "国际事件出现进展。",
                        "published_at": "2026-08-30T01:00:00Z",
                        "provenance": [
                            {
                                "channel_id": "aihot",
                                "channel_label": "AIHOT",
                                "links": [
                                    {"role": "item", "label": "AIHOT", "url": "https://aihot.test/item"},
                                    {"role": "original", "label": "X 阿易 AI Notes", "url": "https://x.test/status/1"},
                                ],
                            }
                        ],
                    }
                ],
                "macro_business": [
                    {
                        "candidate_id": "c2222222222222222",
                        "headline": "中文商业原标题",
                        "headline_zh": "不应出现的翻译",
                        "summary": "市场发布最新数据。",
                        "published_at": None,
                        "provenance": [
                            {
                                "channel_id": "wire",
                                "channel_label": "NS",
                                "links": [
                                    {"role": "article", "label": "Reuters", "url": "https://reuters.test/a"}
                                ],
                            }
                        ],
                    }
                ],
                "ai": [],
            },
        }

        output = render_report.render_report(semantic)

        self.assertTrue(output.startswith("📰 今日热点简报\n"))
        self.assertLess(output.index("### 今日要点"), output.index("### 分类详情"))
        self.assertLess(output.index("**① 国际要闻**"), output.index("**② 宏观与商业**"))
        self.assertLess(output.index("**② 宏观与商业**"), output.index("**③ AI 主线**"))
        self.assertNotIn("\n---\n", output)
        self.assertIn("- **International event advances**（国际事件取得新进展）", output)
        self.assertIn("- **中文商业原标题**", output)
        self.assertNotIn("不应出现的翻译", output)
        self.assertIn("> 来源：[AIHOT](https://aihot.test/item)•[X 阿易 AI Notes](https://x.test/status/1)", output)
        self.assertIn("> 来源：[NS•Reuters](https://reuters.test/a)", output)
        self.assertNotIn("X：", output)


class ResolvedSchemaContractTests(unittest.TestCase):
    def _noon(self):
        return {
            "schema_version": 2,
            "report": "noon-news",
            "report_date": "2026-08-30",
            "generated_at": "2026-08-30T04:00:00+00:00",
            "top_points": [],
            "sections": {
                "international": [],
                "macro_business": [],
                "ai": [],
            },
        }

    def test_current_noon_schema_is_accepted(self):
        self.assertIsNone(contracts.validate_resolved(self._noon()))

    def test_legacy_protocol_and_fourth_section_are_rejected(self):
        for broken in (
            {**self._noon(), "semantic_protocol": "glance_brief.noon-news.v2"},
            {
                **self._noon(),
                "sections": {
                    "international": [],
                    "domestic": [],
                    "macro_business": [],
                    "ai": [],
                },
            },
        ):
            with self.assertRaises(ValueError):
                contracts.validate_resolved(broken)

    def test_unsafe_resolved_text_is_rejected(self):
        broken = self._noon()
        broken["top_points"] = [{"candidate_id": "c000000000001", "topic": "国际", "fact": "bad\n- injected"}]
        with self.assertRaisesRegex(ValueError, "control|newline|Markdown"):
            contracts.validate_resolved(broken)


class AdapterContractTests(unittest.TestCase):
    def test_aihot_candidate_preserves_both_exact_links_and_hierarchy_spaces(self):
        source = {
            "driver": "json_file",
            "path": "items.json",
            "items_path": "items",
            "channel_id": "aihot",
            "channel_label": "AIHOT",
            "map": {
                "title": "title",
                "text": "summary",
                "published_at": "published_at",
                "links": [
                    {"role": "item", "label": "AIHOT", "path": "links.aihot"},
                    {"role": "original", "label_path": "source.name", "path": "links.original"},
                ],
            },
        }
        raw = {
            "title": "A source-backed item",
            "summary": "Evidence text",
            "published_at": "2026-08-30T01:00:00Z",
            "source": {"name": "X：阿易 AI Notes"},
            "links": {
                "aihot": "https://aihot.test/items/abc",
                "original": "https://x.test/status/1",
            },
        }

        candidate = adapters.normalize_candidate("aihot", source, raw)

        self.assertRegex(candidate["candidate_id"], r"^c[0-9a-f]{12,64}$")
        self.assertEqual(candidate["title"], raw["title"])
        self.assertEqual(candidate["text"], raw["summary"])
        self.assertEqual(candidate["provenance"][0]["channel_label"], "AIHOT")
        self.assertEqual(
            candidate["provenance"][0]["links"],
            [
                {"role": "item", "label": "AIHOT", "url": "https://aihot.test/items/abc"},
                {"role": "original", "label": "X 阿易 AI Notes", "url": "https://x.test/status/1"},
            ],
        )

    def test_relative_published_time_is_not_promoted_to_an_absolute_timestamp(self):
        source = {
            "channel_id": "wire",
            "channel_label": "NA",
            "map": {
                "title": "title",
                "text": "summary",
                "published_at": "time",
                "links": [{"role": "article", "label": "source", "path": "url"}],
            },
        }
        candidate = adapters.normalize_candidate(
            "wire",
            source,
            {"title": "Title", "summary": "Evidence", "time": "4 hours ago", "url": "https://example.test/item"},
        )
        self.assertIsNone(candidate["published_at"])

    def test_config_accepts_only_current_json_drivers_and_three_noon_sections(self):
        config = {
            "schema_version": 2,
            "sources": {
                "wire": {
                    "driver": "json_file",
                    "path": "items.json",
                    "items_path": "items",
                    "channel_id": "wire",
                    "channel_label": "NS",
                    "map": {"title": "title", "text": "summary", "links": [{"role": "article", "label": "Reuters", "path": "url"}]},
                }
            },
            "reports": {
                "noon-news": {
                    "selection_limits": {
                        "international": {"min": 1, "max": 2},
                        "macro_business": {"min": 0, "max": 2},
                        "ai": {"min": 0, "max": 2},
                    },
                    "sections": {
                        "international": [{"source": "wire", "take": 2}],
                        "macro_business": [{"source": "wire", "match": {"category": ["business"]}}],
                        "ai": [],
                    }
                }
            },
        }
        self.assertIsNone(adapters.validate_config(config))
        broken = {**config, "sources": {"wire": {**config["sources"]["wire"], "driver": "http_json"}}}
        with self.assertRaises(ValueError):
            adapters.validate_config(broken)
        broken = {**config, "reports": {"noon-news": {"sections": {**config["reports"]["noon-news"]["sections"], "domestic": []}}}}
        with self.assertRaises(ValueError):
            adapters.validate_config(broken)
        bad_required = {**config, "sources": {"wire": {**config["sources"]["wire"], "required": "yes"}}}
        with self.assertRaises(ValueError):
            adapters.validate_config(bad_required)
        bad_minimum = {
            **config,
            "reports": {"noon-news": {**config["reports"]["noon-news"], "minimum_candidates": {"unknown": 1}}},
        }
        with self.assertRaises(ValueError):
            adapters.validate_config(bad_minimum)
        negative_minimum = {
            **config,
            "reports": {"noon-news": {**config["reports"]["noon-news"], "minimum_candidates": {"international": -1}}},
        }
        with self.assertRaises(ValueError):
            adapters.validate_config(negative_minimum)
        bad_selection_limit = {
            **config,
            "reports": {
                "noon-news": {
                    **config["reports"]["noon-news"],
                    "selection_limits": {"international": {"min": 2, "max": 1}},
                }
            },
        }
        with self.assertRaises(ValueError):
            adapters.validate_config(bad_selection_limit)
        agents_selection_limit = {
            "schema_version": 2,
            "sources": config["sources"],
            "reports": {
                "agents-report": {
                    "selection_limits": {"ai_ecosystem": {"min": 0, "max": 1}},
                    "sections": {"ai_ecosystem": [], "codexradar": [], "open_source": []},
                }
            },
        }
        with self.assertRaisesRegex(ValueError, "only supported for noon-news"):
            adapters.validate_config(agents_selection_limit)


class ResolverContractTests(unittest.TestCase):
    def _candidate(self, cid, title, section):
        return {
            "candidate_id": cid,
            "title": title,
            "text": "Evidence supports this item.",
            "published_at": "2026-08-30T01:00:00Z",
            "extra": {"section": section},
            "provenance": [
                {
                    "channel_id": "wire",
                    "channel_label": "NS",
                    "links": [{"role": "article", "label": "Reuters", "url": f"https://reuters.test/{cid}"}],
                }
            ],
        }

    def _assembled(self):
        ids = {
            "international": "c1111111111111111",
            "macro_business": "c2222222222222222",
            "ai": "c3333333333333333",
        }
        return {
            "schema_version": 2,
            "report": "noon-news",
            "candidate_registry": {
                ids["international"]: self._candidate(ids["international"], "International title", "international"),
                ids["macro_business"]: self._candidate(ids["macro_business"], "Business title", "macro_business"),
                ids["ai"]: self._candidate(ids["ai"], "AI title", "ai"),
            },
            "sections": {name: [cid] for name, cid in ids.items()},
            "metadata": {},
        }

    def _model(self):
        ids = {section: values[0] for section, values in self._assembled()["sections"].items()}
        return {
            "top_points": [
                {"candidate_id": ids["international"], "topic": "国际", "fact": "国际事件出现进展"},
                {"candidate_id": ids["macro_business"], "topic": "商业", "fact": "商业市场保持稳定"},
                {"candidate_id": ids["ai"], "topic": "AI", "fact": "AI 工具出现进展"},
            ],
            "sections": {
                "international": [{"candidate_id": ids["international"], "summary": "国际事件出现进展。", "headline_zh": "国际事件取得最新进展消息"}],
                "macro_business": [{"candidate_id": ids["macro_business"], "summary": "商业市场保持稳定。"}],
                "ai": [{"candidate_id": ids["ai"], "summary": "AI 工具出现进展。"}],
            },
            "harmless_debug": {"ignored": True},
        }

    def test_noon_selection_limits_are_enforced(self):
        assembled = self._assembled()
        assembled["selection_limits"] = {
            "international": {"min": 1, "max": 1},
            "macro_business": {"min": 1, "max": 1},
            "ai": {"min": 1, "max": 1},
        }
        model = self._model()
        model["sections"]["international"] = []
        model["top_points"] = [point for point in model["top_points"] if point["candidate_id"] != "c1111111111111111"]
        with self.assertRaisesRegex(ValueError, "selection limit"):
            resolve.resolve_noon(model, assembled, "2026-08-30")

    def test_noon_summary_length_has_hard_ceiling(self):
        model = self._model()
        model["sections"]["international"][0]["summary"] = "长" * 400
        assembled = self._assembled()
        with self.assertRaisesRegex(ValueError, "summary"):
            resolve.resolve_noon(model, assembled, "2026-08-30")

    def test_resolver_backfills_immutable_facts_and_returns_soft_warning(self):
        assembled = self._assembled()
        resolved, warnings = resolve.resolve_noon(self._model(), assembled, "2026-08-30", generated_at="2026-08-30T04:00:00+00:00")

        self.assertEqual(resolved["sections"]["international"][0]["headline"], "International title")
        self.assertEqual(resolved["sections"]["international"][0]["provenance"][0]["links"][0]["url"], "https://reuters.test/c1111111111111111")
        self.assertNotIn("harmless_debug", resolved)
        self.assertTrue(any(item["code"] == "missing_headline_zh" for item in warnings))
        self.assertIsNone(contracts.validate_resolved(resolved))

    def test_model_must_use_singular_known_nonreused_in_section_candidate_ids(self):
        assembled = self._assembled()
        for mutate in (
            lambda model: model["sections"]["international"][0].update({"candidate_id": ["c1111111111111111"]}),
            lambda model: model["sections"]["international"][0].update({"candidate_id": "c9999999999999999"}),
            lambda model: model["sections"]["macro_business"].append(model["sections"]["international"][0].copy()),
            lambda model: model["sections"]["macro_business"].__setitem__(0, {"candidate_id": "c1111111111111111", "summary": "wrong section"}),
        ):
            model = self._model()
            mutate(model)
            with self.assertRaises(ValueError):
                resolve.resolve_noon(model, assembled, "2026-08-30")

    def test_malformed_json_and_unsupported_summary_number_are_hard_failures(self):
        with self.assertRaises(ValueError):
            resolve.parse_model_response("not json")
        model = self._model()
        model["sections"]["ai"][0]["summary"] = "AI 工具带来 9999 个结果。"
        with self.assertRaisesRegex(ValueError, "unsupported number"):
            resolve.resolve_noon(model, self._assembled(), "2026-08-30")

    def test_number_tokens_keep_full_cjk_adjacent_values_without_model_name_suffixes(self):
        self.assertEqual(resolve._numbers("委内瑞拉650亿桶石油"), {"650"})
        self.assertEqual(resolve._numbers("Qwen3.8 27B 模型"), {"27"})
        self.assertEqual(resolve._numbers("上下文为262，144 token"), {"262144"})

    def test_headline_translation_length_is_a_soft_warning(self):
        model = self._model()
        model["sections"]["international"][0]["headline_zh"] = "中文过短"
        resolved, warnings = resolve.resolve_noon(model, self._assembled(), "2026-08-30")
        self.assertEqual(resolved["sections"]["international"][0]["headline_zh"], "中文过短")
        self.assertIn(
            {
                "code": "headline_zh_length",
                "candidate_id": "c1111111111111111",
                "section": "international",
                "chinese_characters": 4,
                "expected": "12-28",
            },
            warnings,
        )


class AgentsCurrentContractTests(unittest.TestCase):
    def _candidate(self, cid, name, description, stars, fresh=False):
        return {
            "candidate_id": cid,
            "title": name,
            "text": description,
            "published_at": None,
            "extra": {"kind": "project", "stars_today": stars, "is_fresh_hot": fresh},
            "provenance": [
                {
                    "channel_id": "github",
                    "channel_label": "GitHub",
                    "links": [{"role": "repository", "label": name, "url": f"https://github.com/{name}"}],
                }
            ],
        }

    def _assembled(self):
        ai = "caaaaaaaaaaaaaaaa"
        alpha = "cbbbbbbbbbbbbbbbb"
        beta = "cccccccccccccccc"
        gamma = "cdddddddddddddddd"
        return {
            "schema_version": 2,
            "report": "agents-report",
            "candidate_registry": {
                ai: {
                    "candidate_id": ai,
                    "title": "AI ecosystem item",
                    "text": "A bounded AI ecosystem signal.",
                    "published_at": None,
                    "extra": {"kind": "ai"},
                    "provenance": [{"channel_id": "aihot", "channel_label": "AIHOT", "links": [{"role": "item", "label": "AIHOT", "url": "https://aihot.test/ai"}]}],
                },
                alpha: self._candidate(alpha, "acme/alpha", "A compact agent runtime.", 42, True),
                beta: self._candidate(beta, "acme/beta", "A useful evaluation toolkit.", 17, False),
                gamma: self._candidate(gamma, "acme/gamma", "A local model utility.", 9, False),
            },
            "sections": {"ai_ecosystem": [ai], "codexradar": [], "open_source": [alpha, beta, gamma]},
            "metadata": {
                "codexradar": {"markdown": "**🧠 CodexRadar 智力效率**\n- 综合效率：稳定\n- 评估样本：producer-owned"},
                "open_source": {
                    "hot_today": [alpha, beta, gamma],
                    "fresh_hot": [alpha],
                    "local_report_categories": [
                        {"title": "Agent 工具", "projects": ["acme/alpha"]},
                        {"title": "评测基础设施", "projects": ["acme/beta", "acme/gamma"]},
                    ],
                    "quality": {"ok": True, "alpha": "accepted"},
                },
            },
        }

    def _model(self):
        return {
            "ai_ecosystem": [{"candidate_id": "caaaaaaaaaaaaaaaa", "summary": "AI 生态出现新的协作信号。"}],
            "open_source_trends": [
                {"summary": "开源工具继续向更轻量的工作流整合。"},
                {"summary": "社区正在加强评测与本地化部署的协同。"},
            ],
            "harmless_debug": "ignored",
        }

    def test_agents_resolver_restores_projects_categories_fresh_and_exact_codex_block(self):
        assembled = self._assembled()
        resolved, warnings = resolve.resolve_agents(self._model(), assembled, "2026-08-30")

        self.assertEqual(resolved["sections"]["codexradar"]["markdown"], assembled["metadata"]["codexradar"]["markdown"])
        self.assertEqual(resolved["sections"]["open_source"]["fresh_hot"][0]["name"], "acme/alpha")
        self.assertEqual(resolved["sections"]["open_source"]["fresh_hot"][0]["url"], "https://github.com/acme/alpha")
        self.assertEqual(resolved["sections"]["open_source"]["categories"][0]["title"], "Agent 工具")
        self.assertEqual(resolved["sections"]["open_source"]["categories"][0]["project"]["name"], "acme/alpha")
        self.assertEqual(resolved["sections"]["open_source"]["trends"], [item["summary"] for item in self._model()["open_source_trends"]])
        self.assertEqual(warnings, [])
        contracts.validate_resolved(resolved)

        markdown = render_report.render_report(resolved)
        self.assertLess(markdown.index("**🤖 AI 生态动态**"), markdown.index("**🧠 CodexRadar 智力效率**"))
        self.assertLess(markdown.index("**🧠 CodexRadar 智力效率**"), markdown.index("**🔥 开源热点趋势**"))
        self.assertIn(assembled["metadata"]["codexradar"]["markdown"], markdown)
        self.assertIn("**✨新热门开源**", markdown)
        self.assertIn("- ① AI 生态出现新的协作信号。", markdown)
        self.assertIn("- ① 开源工具继续向更轻量的工作流整合。", markdown)
        self.assertIn("- [acme/alpha](https://github.com/acme/alpha)「A compact agent runtime.」(+42★/日)", markdown)
        self.assertIn("① Agent 工具", markdown)
        self.assertIn("- 热门项目：✨ [acme/alpha](https://github.com/acme/alpha)「A compact agent runtime.」(+42★/日)", markdown)
        self.assertNotIn("其他项目", markdown)
        self.assertNotIn("\n---\n", markdown)

    def test_category_mapping_must_uniquely_cover_hot_today(self):
        for categories in (
            [{"title": "不完整", "projects": ["acme/alpha"]}],
            [
                {"title": "重复一", "projects": ["acme/alpha", "acme/beta"]},
                {"title": "重复二", "projects": ["acme/beta", "acme/gamma"]},
            ],
        ):
            assembled = self._assembled()
            assembled["metadata"]["open_source"]["local_report_categories"] = categories
            with self.assertRaisesRegex(ValueError, "categor|cover|unique|duplicate"):
                resolve.resolve_agents(self._model(), assembled, "2026-08-30")

    def test_agents_resolver_rejects_non_ok_open_source_quality(self):
        assembled = self._assembled()
        assembled["metadata"]["open_source"]["quality"] = {"ok": False}
        with self.assertRaisesRegex(ValueError, "quality.ok"):
            resolve.resolve_agents(self._model(), assembled, "2026-08-30")

    def test_agents_resolver_rejects_non_github_project_url(self):
        candidate = {
            "candidate_id": "c123456789abc",
            "title": "org/repo",
            "text": "description",
            "extra": {"full_name": "org/repo", "stars_today": 1},
            "provenance": [
                {
                    "channel_id": "radar",
                    "channel_label": "Radar",
                    "links": [{"role": "repository", "label": "repo", "url": "https://example.test/org/repo"}],
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "GitHub"):
            resolve._project_candidate(candidate, False, "candidate")

    def test_agents_trends_are_exactly_two_aggregate_summaries_without_project_or_star_data(self):
        assembled = self._assembled()
        for bad in (
            [{"summary": "acme/alpha 项目很热。"}, {"summary": "另一个趋势。"}],
            [{"summary": "趋势增长 42★。"}, {"summary": "另一个趋势。"}],
            [{"summary": "只有一条趋势。"}],
        ):
            model = self._model()
            model["open_source_trends"] = bad
            with self.assertRaises(ValueError):
                resolve.resolve_agents(model, assembled, "2026-08-30")

    def test_agents_current_schema_rejects_removed_project_sections(self):
        with self.assertRaises(ValueError):
            contracts.validate_resolved({
                "schema_version": 2,
                "report": "agents-report",
                "date": "2026-08-30",
                "sections": {
                    "ai_ecosystem": [],
                    "codexradar": {"markdown": "**🧠 CodexRadar 智力效率**\n- ok"},
                    "open_source": {"trends": ["a", "b"], "fresh_hot": [], "categories": [], "quality": {}, "hot_projects": []},
                },
            })


class PromptContractTests(unittest.TestCase):
    def test_noon_prompt_is_singular_candidate_semantic_json_only(self):
        prompt = (ROOT / "v2" / "prompts" / "noon-news.md").read_text(encoding="utf-8")
        for marker in ("只输出一个 JSON 对象", '"candidate_id"', '"summary"', '"headline_zh"'):
            self.assertIn(marker, prompt)
        for forbidden in ("candidate_ids", "item_refs", "Markdown 链接", "自行生成 URL"):
            self.assertNotIn(forbidden, prompt)
        self.assertIn("每条详情只能选择一个 candidate_id", prompt)
        self.assertIn("12–28", prompt)
        self.assertIn("阿拉伯数字必须逐字复制", prompt)
        self.assertIn("不得换算单位", prompt)
        self.assertIn("引述只使用中文引号", prompt)
        self.assertIn("不得使用半角双引号", prompt)
        self.assertIn("selection_limits", prompt)
        self.assertIn("min", prompt)
        self.assertIn("max", prompt)

    def test_agents_prompt_excludes_program_owned_facts_and_requires_two_trends(self):
        prompt = (ROOT / "v2" / "prompts" / "agents-report.md").read_text(encoding="utf-8")
        for marker in ("只输出一个 JSON 对象", '"ai_ecosystem"', '"open_source_trends"', "必须恰好两条"):
            self.assertIn(marker, prompt)
        for marker in ("不得输出项目名", "不得输出 URL", "不得输出 Star", "不得输出 CodexRadar"):
            self.assertIn(marker, prompt)
        self.assertNotIn("hot_projects", prompt)
        self.assertNotIn("other_projects", prompt)


if __name__ == "__main__":
    unittest.main()
