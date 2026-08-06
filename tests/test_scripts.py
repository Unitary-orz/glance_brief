import importlib.util
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
AGENTS_SCRIPTS = ROOT / "skills" / "agents-report" / "scripts"
NOON_SCRIPTS = ROOT / "skills" / "noon-news" / "scripts"
sys.path.insert(0, str(AGENTS_SCRIPTS))
sys.path.insert(0, str(NOON_SCRIPTS))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agents_prefetch = load_module(
    "agents_radar_prefetch", AGENTS_SCRIPTS / "agents_radar_prefetch.py"
)
agents_collector = load_module(
    "agents_radar_daily", AGENTS_SCRIPTS / "agents-radar-daily.py"
)
codexradar = load_module(
    "codexradar_efficiency", AGENTS_SCRIPTS / "codexradar_efficiency.py"
)
noon_prefetch = load_module(
    "noon_news_prefetch", NOON_SCRIPTS / "noon_news_prefetch.py"
)


class FixtureTests(unittest.TestCase):
    def load_fixture(self, name):
        with (ROOT / "tests" / "fixtures" / name).open(encoding="utf-8") as handle:
            return json.load(handle)

    def test_fixture_contracts_have_schema_version(self):
        for name in ("aihot-v1.json", "codexradar.json", "noon-prefetch.json"):
            self.assertEqual(self.load_fixture(name)["schema_version"], 1)


    def test_noon_fixture_matches_prefetch_shape(self):
        payload = self.load_fixture("noon-prefetch.json")
        for source in ("news_aggregator", "rss_summary"):
            self.assertIn("returncode", payload[source])
            self.assertIn("stderr", payload[source])
            self.assertIsInstance(payload[source]["items"], list)
        for field in ("count", "since", "take", "endpoint"):
            self.assertIn(field, payload["aihot"])
        self.assertIn("instructions", payload)


class AdapterTests(unittest.TestCase):
    def test_hermes_example_paths_exist_in_full_checkout(self):
        payload = json.loads(
            (ROOT / "adapters/hermes/jobs.example.json").read_text(encoding="utf-8")
        )
        for job in payload["jobs"]:
            self.assertTrue((ROOT / job["script"]).is_file(), job["script"])
            self.assertTrue((ROOT / job["prompt_file"]).is_file(), job["prompt_file"])


class AgentsRadarTests(unittest.TestCase):
    def test_collector_uses_feed_date_from_link(self):
        entry = SimpleNamespace(link="https://example.com/agents-radar/2026-08-06")
        self.assertEqual(agents_collector.extract_entry_date(entry), "2026-08-06")

    def test_collector_strips_html_and_splits_sections(self):
        html = "<h2>Trend</h2><br>one<hr><h2>Projects</h2><br>two"
        text = agents_collector.strip_html(html)
        blocks = agents_collector.split_blocks(text)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(agents_collector.infer_block_title(blocks[0]), "Trend")

    def test_prefetch_selects_content_markers_not_fixed_block_numbers(self):
        raw = """
=== SOURCE: ai-trending | DATE: 2026-08-06 ===
--- BLOCK 1 | TITLE: unrelated ---
noise
--- BLOCK 2 | TITLE: 今日速览 ---
trend overview
--- BLOCK 3 | TITLE: 各维度热门项目 ---
project list
--- BLOCK 4 | TITLE: 趋势信号分析 ---
signal
"""
        result = agents_prefetch.select_trending_body(raw)
        self.assertTrue(result["ok"])
        self.assertIn("trend overview", result["stdout"])
        self.assertIn("project list", result["stdout"])
        self.assertIn("signal", result["stdout"])
        self.assertNotIn("noise", result["stdout"])


class CodexRadarTests(unittest.TestCase):
    def test_render_markdown_contains_ranked_sections(self):
        data = self.load_points()
        rendered = codexradar.render_markdown(data, data, data, data)
        self.assertIn("CodexRadar", rendered)
        self.assertIn("model-a", rendered)
        self.assertIn("IQ", rendered)

    def test_rank_value_respects_quality_gate(self):
        data = self.load_points()
        ranking = {"value_iq_floor": 90, "value_top_n": 3}
        config = {"ranking": {"other_sort": {"model_order": []}}, "effort_order": []}
        ranked = codexradar.rank_value(data, ranking, config)
        self.assertEqual(ranked[0]["model"], "model-a")
        self.assertEqual(len(ranked), 1)

    def test_missing_codexradar_timestamp_is_explicit_warning(self):
        config = {
            "selection": {"explicit": [{"model": "model-a", "efforts": ["high"]}]},
            "effort_order": ["high"],
            "ranking": {"other_sort": {"model_order": ["model-a"]}},
        }
        result = codexradar.build_result(self.load_points(), config, "fixture", None)
        self.assertIn("warning", result)
        self.assertIn("source_updated_at missing", result["warning"])

    def load_points(self):
        payload = self.load_fixture("codexradar.json")
        return codexradar.points_from_snapshot(payload)

    def load_fixture(self, name):
        with (ROOT / "tests" / "fixtures" / name).open(encoding="utf-8") as handle:
            return json.load(handle)


class NoonNewsTests(unittest.TestCase):
    def test_parse_jsonish_handles_json_fenced_output(self):
        payload = noon_prefetch.parse_jsonish('```json\n{"items": [1]}\n```')
        self.assertEqual(payload, {"items": [1]})

    def test_run_source_rejects_malformed_json(self):
        result = noon_prefetch.run_source(
            "malformed", [sys.executable, "-c", "print('not-json')"]
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["items"], [])
        self.assertIn("not JSON", result["error"])

    def test_run_source_rejects_empty_json_output(self):
        result = noon_prefetch.run_source(
            "empty", [sys.executable, "-c", "pass"]
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["items"], [])
        self.assertIn("stdout was empty", result["error"])

    def test_run_source_converts_start_and_timeout_errors(self):
        command = [sys.executable, "-c", "print('[]')"]
        with patch.object(noon_prefetch.subprocess, "run", side_effect=OSError("missing")):
            result = noon_prefetch.run_source("missing-python", command)
        self.assertFalse(result["ok"])
        self.assertEqual(result["items"], [])
        self.assertIn("could not start", result["error"])

        timeout = subprocess.TimeoutExpired(command, 180)
        with patch.object(noon_prefetch.subprocess, "run", side_effect=timeout):
            result = noon_prefetch.run_source("slow-source", command)
        self.assertFalse(result["ok"])
        self.assertEqual(result["items"], [])
        self.assertIn("timed out", result["error"])

    def test_python_with_modules_skips_unavailable_interpreter(self):
        with patch.object(noon_prefetch.subprocess, "run", side_effect=OSError("missing")):
            self.assertEqual(
                noon_prefetch.python_with_modules("not_a_real_module"),
                sys.executable,
            )

    def test_fetch_aihot_converts_curl_start_error(self):
        with patch.object(noon_prefetch, "_curl_available", return_value=True):
            with patch.object(
                noon_prefetch.subprocess,
                "run",
                side_effect=OSError("missing curl"),
            ):
                result = noon_prefetch.fetch_aihot()
        self.assertFalse(result["ok"])
        self.assertEqual(result["items"], [])
        self.assertIn("could not start", result["error"])

    def test_prompt_keeps_source_on_separate_line(self):
        prompt = (ROOT / "skills/noon-news/prompts/news-brief-v2.md").read_text(encoding="utf-8")
        self.assertIn("来源必须是独立行", prompt)
        self.assertIn("来源：[NS](原文链接)", prompt)
        self.assertIn("严格输出 4–5 条编号列表", prompt)
        self.assertIn("主题词为 2–6 个中文字符", prompt)
        self.assertNotIn("事实描述。（来源", prompt)


class OutputContractTests(unittest.TestCase):
    def test_agents_prompt_has_current_sections_and_limits(self):
        prompt = (ROOT / "skills/agents-report/prompts/agents-report-v2.md").read_text(encoding="utf-8")
        for section in ("AI 生态动态", "CodexRadar 智力效率", "开源热点趋势"):
            self.assertIn(section, prompt)
        self.assertIn("不超过 140 字", prompt)
        self.assertIn("热门项目", prompt)
        self.assertIn("其他项目", prompt)

    def test_codex_heading_is_not_a_duplicate_output_line(self):
        prompt = (ROOT / "skills/agents-report/prompts/agents-report-v2.md").read_text(encoding="utf-8")
        structure = prompt.split("## 固定输出结构", 1)[1].split("## AI 生态动态", 1)[0]
        standalone_heading = re.compile(r"^\*\*🧠 CodexRadar 智力效率\*\*$", re.MULTILINE)
        self.assertIsNone(standalone_heading.search(structure))
        self.assertEqual(
            codexradar.render_markdown([], [], [], []).count("**🧠 CodexRadar 智力效率**"),
            1,
        )

    def test_runtime_templates_do_not_contain_real_targets(self):
        private_path_markers = ("/root/." + "hermes", "/root/." + "openclaw")
        for path in (ROOT / "adapters").rglob("*.json"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("oc_", text)
            for marker in private_path_markers:
                self.assertNotIn(marker, text)


if __name__ == "__main__":
    unittest.main()
