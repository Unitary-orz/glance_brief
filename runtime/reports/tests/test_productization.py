"""Offline contract tests for the source-owned reports runtime."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[3]
REPORTS_ROOT = REPO_ROOT / "runtime" / "reports"
CONFIG_PATH = REPO_ROOT / "config" / "brief.reports.example.json"

sys.path.insert(0, str(REPORTS_ROOT / "lib"))

from glance_brief import adapters, contracts, input_adapters, render_report, resolve, source_adapters  # noqa: E402
from glance_brief.source_adapters import generic  # noqa: E402


class ReportsInputAdapterTests(unittest.TestCase):
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
        view = input_adapters.load_source_input(
            "aihot",
            source,
            CONFIG_PATH.parent,
            snapshot_payload=snapshot,
        )
        self.assertIs(view, snapshot)
        self.assertEqual(len(view["aihot"]["items"]), 2)

    def test_snapshot_json_is_the_only_shared_snapshot_driver(self) -> None:
        snapshot = {"items": [{"title": "fixture"}]}
        view = input_adapters.load_source_input(
            "snapshot",
            {"driver": "snapshot_json"},
            CONFIG_PATH.parent,
            snapshot_payload=snapshot,
        )
        self.assertIs(view, snapshot)
        with self.assertRaises(contracts.ContractError):
            input_adapters.load_source_input(
                "legacy",
                {"driver": "report_json"},
                CONFIG_PATH.parent,
                snapshot_payload=snapshot,
            )
        with self.assertRaises(contracts.ContractError):
            input_adapters.load_source_input(
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
        prompt = (REPORTS_ROOT / "lib" / "glance_brief" / "prompts" / "noon-news.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("默认 4–6 字", prompt)
        self.assertIn("只有删去第 7 个字会损失", prompt)
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
        markdown = render_report.render_report(
            resolved,
            section_definitions=noon["section_definitions"],
            report_plan=noon["report_plan"],
        )
        self.assertIn("1. **英伟达百亿入股**：", markdown)

    def test_agents_topic_is_a_trend_point_not_a_category_label(self) -> None:
        prompt = (REPORTS_ROOT / "lib" / "glance_brief" / "prompts" / "agents-report.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("趋势点短结论", prompt)
        self.assertIn("不是板块或分类标签", prompt)
        self.assertIn("英伟达入股AI", prompt)
        self.assertIn("AI安全威胁", prompt)
        self.assertIn("renderer 报 summary 超长时，只压缩报错字段后重试", prompt)

    def test_one_bad_source_isolated_until_the_configured_health_gate(self) -> None:
        config = copy.deepcopy(self.config)
        config["sources"]["aihot"]["items_path"] = "aihot.missing"
        assembled = adapters.assemble_report(config, contracts.NOON_REPORT, CONFIG_PATH.parent)
        self.assertEqual(len(assembled["sections"]["international"]), 1)
        self.assertEqual(len(assembled["sections"]["macro_business"]), 1)
        self.assertIn("aihot", assembled["source_errors"])
        with self.assertRaises(contracts.ContractError):
            adapters.validate_assembly_health(config, contracts.NOON_REPORT, assembled)


class ReportsSourceBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    def test_input_adapters_package_is_the_direct_implementation_boundary(self) -> None:
        self.assertIsInstance(input_adapters.SOURCE_INPUT_ADAPTERS, dict)
        self.assertEqual(
            set(input_adapters.SOURCE_INPUT_ADAPTERS),
            {"json_file", "command_json", "snapshot_json"},
        )
        self.assertFalse(
            (REPORTS_ROOT / "lib" / "glance_brief" / "source_inputs.py").exists()
        )

    def test_source_adapter_registry_owns_special_local_radar_logic(self) -> None:
        adapter = source_adapters.get_source_adapter("open_source_radar")
        self.assertIs(adapter, source_adapters.local_open_source_radar)
        self.assertTrue(callable(adapter.adapt_payload))
        self.assertIsNone(source_adapters.get_source_adapter("aihot"))
        with self.assertRaises(contracts.ContractError):
            source_adapters.adapt_payload(
                "aihot",
                {},
                report_date="2026-09-15",
                report_dir=Path("."),
            )

    def test_generic_source_adapter_is_the_implementation_boundary(self) -> None:
        self.assertTrue(callable(generic.normalize_candidate))
        self.assertFalse(hasattr(adapters, "normalize_candidate"))

        source = {
            "items_path": "items",
            "channel_id": "fixture",
            "channel_label": "Fixture",
            "exclude": {"kind": ["ignore"]},
            "map": {
                "title": "title",
                "text": "summary",
                "extra": {"kind": "kind"},
                "links": [],
            },
            "snapshot": {"status": "status"},
        }
        result = generic.adapt_source(
            "fixture",
            source,
            {
                "items": [
                    {"title": "Keep", "summary": "Evidence", "kind": "keep"},
                    {"title": "Drop", "summary": "Evidence", "kind": "ignore"},
                ],
                "status": {"ok": True},
            },
        )

        self.assertEqual([item["title"] for item in result["items"]], ["Keep"])
        self.assertEqual(result["snapshot"], {"status": {"ok": True}})
        self.assertEqual(result["diagnostics"], {"excluded": 1, "rejections": []})

    def test_source_adapter_registry_dispatches_by_adapter_id(self) -> None:
        self.assertIs(source_adapters.get_adapter("generic"), generic)
        result = source_adapters.adapt_source(
            "fixture",
            {"adapter": "generic", "items_path": "items", "map": {"title": "title", "text": "text", "links": []}},
            {"items": [{"title": "Fixture", "text": "Evidence"}]},
        )
        self.assertEqual(result["items"][0]["title"], "Fixture")

        with self.assertRaisesRegex(contracts.ContractError, "unknown source adapter"):
            source_adapters.adapt_source(
                "fixture",
                {"adapter": "missing", "map": {}},
                {},
            )

    def test_report_source_adapter_is_optional_and_defaults_to_generic(self) -> None:
        config = copy.deepcopy(self.config)
        for source in config["sources"].values():
            source.pop("adapter", None)
        adapters.validate_config(config)
        config["sources"]["aihot"]["adapter"] = "generic"
        adapters.validate_config(config)

    def test_source_adapter_preserves_payload_and_attaches_validated_publication(self) -> None:
        payload = json.loads(
            (REPO_ROOT / "tests" / "fixtures" / "pipeline" / "reports-snapshot.json").read_text(
                encoding="utf-8"
            )
        )
        payload["local_radar"].pop("publication", None)
        publication = """📡 **本地开源雷达｜2026-09-15**

**🔥 今日趋势**
- Agent 工具链持续升温。
- 本地化与协同编排受关注。

**✨ 本期新入榜**
- [fixture-labs/agent-workflow](https://github.com/fixture-labs/agent-workflow)「面向 AI 工作流的工具。」(+42★/日)

**🚀 今日热门**
① **🤖 AI 智能体/工作流**
- [fixture-labs/agent-workflow](https://github.com/fixture-labs/agent-workflow)「多 agent 协同的源码管控。」(+42★/日)
② **🧪 评测与基础设施**
- [fixture-labs/eval-kit](https://github.com/fixture-labs/eval-kit)「用于本地 AI 系统的评测工具。」(+17★/日)
- [fixture-labs/local-router](https://github.com/fixture-labs/local-router)「用于本地模型路由的工具。」(+9★/日)

**🌱 新项目发现**
"""
        with TemporaryDirectory() as temp:
            report_dir = Path(temp)
            (report_dir / "2026-09-15.md").write_text(publication, encoding="utf-8")
            adapted = source_adapters.adapt_payload(
                "open_source_radar",
                payload,
                report_date="2026-09-15",
                report_dir=report_dir,
            )
        self.assertNotIn("publication", payload["local_radar"])
        self.assertEqual(
            adapted["local_radar"]["publication"]["trends"],
            ["Agent 工具链持续升温。", "本地化与协同编排受关注。"],
        )

    def test_agents_entrypoint_uses_source_adapter_registry(self) -> None:
        text = (REPORTS_ROOT / "entrypoints" / "agents.py").read_text(encoding="utf-8")
        self.assertIn("from glance_brief import cli, source_adapters", text)
        self.assertIn("source_adapters.adapt_payload(", text)
        self.assertNotIn("local_radar_publication", text)


class ReportsWrapperBoundaryTests(unittest.TestCase):
    def test_wrappers_have_no_source_registry_or_source_health_policy(self) -> None:
        for name in ("news.py", "agents.py"):
            text = (REPORTS_ROOT / "entrypoints" / name).read_text(encoding="utf-8")
            self.assertNotIn("REQUIRED_SOURCES", text)
            self.assertNotIn("V1_PREFETCH", text)
            self.assertNotIn("news_aggregator", text)
            self.assertNotIn("rss_summary", text)
            self.assertNotIn('payload.get("aihot")', text)
            self.assertNotIn('payload.get("codexradar")', text)

    def test_runtime_metadata_is_deployment_configurable_and_publication_is_explicit(self) -> None:
        for name in ("news.py", "agents.py"):
            text = (REPORTS_ROOT / "entrypoints" / name).read_text(encoding="utf-8")
            prefix = "GLANCE_BRIEF_AGENTS_" if name == "agents.py" else "GLANCE_BRIEF_NEWS_"
            self.assertIn(f"{prefix}MODEL", text)
            self.assertIn(f"{prefix}PROVIDER", text)
            self.assertIn(f"{prefix}REASONING", text)
            self.assertIn('"medium"', text)
        agents = (REPORTS_ROOT / "entrypoints" / "agents.py").read_text(encoding="utf-8")
        self.assertIn("GLANCE_BRIEF_AGENTS_PUBLICATION_DIR", agents)
        self.assertIn("PUBLICATION_DIR is None", agents)
        self.assertNotIn('"local-radar"', agents)


if __name__ == "__main__":
    unittest.main()
