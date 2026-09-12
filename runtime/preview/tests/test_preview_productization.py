"""Offline contract tests for the source-owned V2 Preview runtime."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PREVIEW_ROOT = REPO_ROOT / "runtime" / "preview"
CONFIG_PATH = REPO_ROOT / "config" / "brief.preview.example.json"

sys.path.insert(0, str(PREVIEW_ROOT / "lib"))

from glance_brief import adapters, contracts, resolve, source_inputs  # noqa: E402


class PreviewInputAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    def test_report_input_and_all_source_views_use_the_same_snapshot(self) -> None:
        snapshot = adapters.load_report_input(
            self.config["reports"]["noon-news"]["input"],
            CONFIG_PATH.parent,
        )
        self.assertIsInstance(snapshot, dict)
        source = self.config["sources"]["aihot"]
        view = source_inputs.load_source_input(
            "aihot",
            source,
            CONFIG_PATH.parent,
            snapshot_payload=snapshot,
        )
        self.assertIs(view, snapshot)
        self.assertEqual(len(view["aihot"]["items"]), 2)

    def test_report_json_remains_a_compatibility_alias_only(self) -> None:
        snapshot = {"items": [{"title": "fixture"}]}
        view = source_inputs.load_source_input(
            "legacy",
            {"driver": "report_json"},
            CONFIG_PATH.parent,
            snapshot_payload=snapshot,
        )
        self.assertIs(view, snapshot)
        with self.assertRaises(contracts.ContractError):
            source_inputs.load_source_input(
                "missing",
                {"driver": "snapshot_json"},
                CONFIG_PATH.parent,
            )

    def test_noon_and_agents_assemble_from_one_offline_snapshot(self) -> None:
        noon = adapters.assemble_report(self.config, contracts.NOON_REPORT, CONFIG_PATH.parent)
        agents = adapters.assemble_report(self.config, contracts.AGENTS_REPORT, CONFIG_PATH.parent)
        adapters.validate_assembly_health(self.config, contracts.NOON_REPORT, noon)
        adapters.validate_assembly_health(self.config, contracts.AGENTS_REPORT, agents)
        self.assertEqual(len(noon["candidate_registry"]), 5)
        self.assertEqual(len(agents["candidate_registry"]), 7)
        self.assertEqual(noon["source_exclusions"]["news_aggregator"], 1)
        self.assertEqual(
            agents["source_snapshots"]["open_source_radar"]["publication"]["trends"],
            ["Agent 工具链持续升温。", "本地化与协同编排受关注。"],
        )

    def test_noon_topic_prefers_four_to_six_and_warns_at_seven(self) -> None:
        prompt = (PREVIEW_ROOT / "lib" / "glance_brief" / "prompts" / "noon-news.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("4–6 字为首选", prompt)
        self.assertIn("7 字可接受", prompt)
        self.assertIn("8 字仅作兼容上限", prompt)

        noon = adapters.assemble_report(self.config, contracts.NOON_REPORT, CONFIG_PATH.parent)
        model = {"top_points": [], "sections": {}}
        for section_id, candidate_ids in noon["sections"].items():
            details = []
            for candidate_id in candidate_ids:
                candidate = noon["candidate_registry"][candidate_id]
                detail = {
                    "candidate_id": candidate_id,
                    "summary": "预览候选提供一条独立中文事实。",
                }
                title = candidate["title"]
                if not any("\u3400" <= char <= "\u9fff" for char in title):
                    detail["headline_zh"] = "国际合作代表发布联合声明"
                details.append(detail)
            model["sections"][section_id] = details
            candidate_id = candidate_ids[0]
            model["top_points"].append(
                {
                    "candidate_id": candidate_id,
                    "topic": "候选进展",
                    "fact": "该候选支持一项明确的最新进展。",
                }
            )
        model["top_points"][0]["topic"] = "英伟达百亿入股"

        resolved, warnings = resolve.resolve_noon(model, noon, "2026-09-12")

        self.assertEqual(resolved["top_points"][0]["topic"], "英伟达百亿入股")
        topic_warnings = [warning for warning in warnings if warning.get("code") == "top_point_topic_length"]
        self.assertEqual(len(topic_warnings), 1)
        self.assertEqual(topic_warnings[0]["characters"], 7)

    def test_one_bad_source_isolated_until_the_configured_health_gate(self) -> None:
        config = copy.deepcopy(self.config)
        config["sources"]["aihot"]["items_path"] = "aihot.missing"
        assembled = adapters.assemble_report(config, contracts.NOON_REPORT, CONFIG_PATH.parent)
        self.assertEqual(len(assembled["sections"]["international"]), 1)
        self.assertEqual(len(assembled["sections"]["macro_business"]), 1)
        self.assertIn("aihot", assembled["source_errors"])
        with self.assertRaises(contracts.ContractError):
            adapters.validate_assembly_health(config, contracts.NOON_REPORT, assembled)


class PreviewWrapperBoundaryTests(unittest.TestCase):
    def test_wrappers_have_no_source_registry_or_source_health_policy(self) -> None:
        for name in ("noon_preview.py", "agents_preview.py"):
            text = (PREVIEW_ROOT / "entrypoints" / name).read_text(encoding="utf-8")
            self.assertNotIn("REQUIRED_SOURCES", text)
            self.assertNotIn("V1_PREFETCH", text)
            self.assertNotIn("news_aggregator", text)
            self.assertNotIn("rss_summary", text)
            self.assertNotIn('payload.get("aihot")', text)
            self.assertNotIn('payload.get("codexradar")', text)


if __name__ == "__main__":
    unittest.main()
