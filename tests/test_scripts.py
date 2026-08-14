import importlib.util
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
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
        for field in ("count", "window", "by", "limit", "endpoint"):
            self.assertIn(field, payload["aihot"])
        self.assertIn("instructions", payload)


class AdapterTests(unittest.TestCase):
    def test_hermes_example_paths_exist_in_full_checkout(self):
        payload = json.loads(
            (ROOT / "adapters/hermes/jobs.example.json").read_text(encoding="utf-8")
        )
        manifest = json.loads(
            (ROOT / "install/install-manifest.json").read_text(encoding="utf-8")
        )
        entrypoints = {
            spec["entrypoint"] for spec in manifest["components"].values()
        } | set(manifest["utility_entrypoints"].keys())
        for job in payload["jobs"]:
            # Job scripts are runtime paths relative to $HERMES_HOME/scripts/,
            # not repository paths; the entry point name must be declared in
            # the install manifest.
            self.assertRegex(job["script"], r"^glance-brief/[A-Za-z0-9._-]+\.py$", job["script"])
            self.assertIn(Path(job["script"]).name, entrypoints, job["script"])
            self.assertTrue((ROOT / job["prompt_file"]).is_file(), job["prompt_file"])

    def test_private_skill_configs_are_gitignored(self):
        for relative in (
            "skills/agents-report/config/codexradar_watch.json",
            "skills/agents-report/config/agents_radar_quality.json",
        ):
            result = subprocess.run(
                [
                    "git",
                    "-c",
                    f"safe.directory={ROOT}",
                    "check-ignore",
                    "--no-index",
                    "-q",
                    relative,
                ],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(result.returncode, 0, relative)

    def test_both_runtime_adapters_document_quality_paths(self):
        for relative in (
            "adapters/hermes/INSTALL.md",
            "adapters/openclaw/INSTALL.md",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("AGENTS_RADAR_QUALITY_CONFIG", text, relative)
            self.assertIn("AGENTS_RADAR_QUALITY_MODULE_DIR", text, relative)


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

    def test_collector_preserves_github_anchor_as_markdown(self):
        text = agents_collector.strip_html(
            '<a class="repo" href="https://github.com/example/project">'
            "example/project</a>"
        )
        self.assertEqual(
            text,
            "[example/project](https://github.com/example/project)",
        )

    def test_collector_drops_non_http_anchor_target(self):
        text = agents_collector.strip_html(
            '<a href="javascript:alert(1)">unsafe label</a>'
        )
        self.assertEqual(text, "unsafe label")

    def test_prefetch_defaults_quality_module_to_script_directory(self):
        self.assertEqual(agents_prefetch.QUALITY_MODULE_DIR, AGENTS_SCRIPTS)

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

    def test_rank_value_uses_sublinear_price_penalty(self):
        data = [
            {
                "model": "quality-model",
                "effort": "high",
                "iq": 100.0,
                "price": 4.0,
                "minutes": 10.0,
                "combined_cost": 14.0,
            },
            {
                "model": "cheap-model",
                "effort": "high",
                "iq": 80.0,
                "price": 2.0,
                "minutes": 10.0,
                "combined_cost": 12.0,
            },
        ]
        ranking = {"value_top_n": 2, "value_price_exponent": 0.25}
        config = {"ranking": {"other_sort": {"model_order": []}}, "effort_order": []}
        ranked = codexradar.rank_value(data, ranking, config)
        self.assertEqual(ranked[0]["model"], "quality-model")

    def test_restricted_value_scope_does_not_fallback_to_sol(self):
        data = [
            {
                "model": "gpt-5.6-sol",
                "effort": "high",
                "iq": 100.0,
                "price": 4.0,
                "minutes": 10.0,
                "combined_cost": 14.0,
            }
        ]
        ranking = {
            "value_top_n": 3,
            "value_scope": "non_sol_explicit_watch_configs",
        }
        config = {"ranking": {"other_sort": {"model_order": []}}, "effort_order": []}
        self.assertEqual(codexradar.rank_value(data, ranking, config), [])

    def test_free_value_candidate_remains_strict_json(self):
        data = [
            {
                "model": "free-model",
                "effort": "high",
                "iq": 80.0,
                "price": 0.0,
                "minutes": 10.0,
                "combined_cost": 10.0,
            },
            {
                "model": "paid-model",
                "effort": "high",
                "iq": 100.0,
                "price": 1.0,
                "minutes": 10.0,
                "combined_cost": 11.0,
            },
        ]
        ranking = {"value_top_n": 2, "value_price_exponent": 0.25}
        config = {"ranking": {"other_sort": {"model_order": []}}, "effort_order": []}
        ranked = codexradar.rank_value(data, ranking, config)
        self.assertEqual(ranked[0]["model"], "free-model")
        json.dumps(ranked, allow_nan=False)

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
        self.assertIn("> 来源：[NS•AlJazeera](原文链接)•[BBC](原文链接)", prompt)
        self.assertIn("来源单独一行，用引用块（`> 来源：`）", prompt)
        self.assertIn("正文不显示 URL 明文", prompt)
        self.assertIn("冒号一律替换为 `•`", prompt)
        self.assertIn("`公众号` 统一替换为 `WX`", prompt)
        self.assertIn("最多 2 个渠道", prompt)
        self.assertIn("+N", prompt)
        self.assertIn("同渠道去重", prompt)
        self.assertIn("链接使用脚本原始条目的 `link` 或 `url`", prompt)
        self.assertIn("严格输出 4–5 条编号列表", prompt)
        self.assertIn("主题词为 2–6 个中文字符", prompt)
        self.assertNotIn("事实描述。（来源", prompt)
        self.assertNotIn("[NS](原文链接) · [BBC](原文链接)", prompt)


class OutputContractTests(unittest.TestCase):
    def test_agents_prompt_has_current_sections_and_limits(self):
        prompt = (ROOT / "skills/agents-report/prompts/agents-report-v2.md").read_text(encoding="utf-8")
        for section in ("AI 生态动态", "CodexRadar 智力效率", "开源热点趋势"):
            self.assertIn(section, prompt)
        self.assertIn("不超过 140 字", prompt)
        self.assertIn("热门项目", prompt)
        self.assertIn("其他项目", prompt)

    def test_agents_prompt_uses_available_sources_without_padding(self):
        prompt = (ROOT / "skills/agents-report/prompts/agents-report-v2.md").read_text(encoding="utf-8")
        self.assertIn("1–3 个真实相关来源", prompt)
        self.assertIn("只有一个来源时直接使用一个", prompt)
        self.assertNotIn("🌐 Agents生态趋势", prompt)

    def test_noon_prompt_allows_only_source_supported_forecasts(self):
        prompt = (ROOT / "skills/noon-news/prompts/news-brief-v2.md").read_text(encoding="utf-8")
        self.assertIn("允许原始来源明确给出的预测、预警和条件判断", prompt)
        self.assertIn("禁止模型自行推演", prompt)

    def test_quality_checker_rejects_preface_and_ignores_sentence_as_category(self):
        quality = load_module(
            "open_source_quality",
            AGENTS_SCRIPTS / "open_source_quality.py",
        )
        source = """
“从零复现大模型”类项目（alpha、beta）依旧活跃。
🔧 AI 基础工具（框架、SDK）
| [example/project](https://github.com/example/project)
"""
        inspected = quality.inspect_source_projects(source)
        self.assertEqual(
            [category["name"] for category in inspected["categories"]],
            ["🔧 AI 基础工具（框架、SDK）"],
        )

        report = """
All context confirmed.

📡 **agents-radar 生态报告 | 2026-08-09**

**🔥 开源热点趋势**

🔧 AI 基础工具
- 热门项目：[example/project](https://github.com/example/project)「简介」
- 其他项目：无
"""
        checked = quality.validate_rendered_report(report)
        self.assertFalse(checked["ok"])
        self.assertIn(
            "report_preface_present",
            [warning["code"] for warning in checked["warnings"]],
        )

    def test_quality_parser_accepts_list_projects_and_plain_emoji_category(self):
        quality = load_module(
            "open_source_quality_list_fixture",
            AGENTS_SCRIPTS / "open_source_quality.py",
        )
        source = """
🔧 AI 基础工具
- [example/linked](https://github.com/example/linked)
- example/unlinked
"""
        inspected = quality.inspect_source_projects(source)
        self.assertEqual(inspected["source_project_count"], 2)
        self.assertEqual(inspected["source_linked_project_count"], 1)
        self.assertEqual(inspected["source_unlinked_projects"], ["example/unlinked"])
        self.assertEqual(inspected["categories"][0]["name"], "🔧 AI 基础工具")

    def test_quality_parser_omits_empty_section_heading_category(self):
        quality = load_module(
            "open_source_quality_section_heading",
            AGENTS_SCRIPTS / "open_source_quality.py",
        )
        source = """
🔥 开源热点趋势
🔧 AI 基础工具
| [example/linked](https://github.com/example/linked)
"""
        inspected = quality.inspect_source_projects(source)
        self.assertEqual(
            [category["name"] for category in inspected["categories"]],
            ["🔧 AI 基础工具"],
        )

    def test_quality_config_environment_overrides_example_output_path(self):
        quality = load_module(
            "open_source_quality_env_override",
            AGENTS_SCRIPTS / "open_source_quality.py",
        )
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "quality.json"
            config_path.write_text(
                json.dumps({"cron_output_dir": "/path/to/example"}),
                encoding="utf-8",
            )
            with patch.dict(
                "os.environ",
                {"AGENTS_RADAR_CRON_OUTPUT_DIR": "/runtime/cron/output"},
            ):
                config = quality.load_quality_config(config_path)
        self.assertEqual(config["cron_output_dir"], "/runtime/cron/output")

    def test_quality_checker_requires_configured_project_link_prefix(self):
        quality = load_module(
            "open_source_quality_link_prefix",
            AGENTS_SCRIPTS / "open_source_quality.py",
        )
        report = """
📡 **agents-radar 生态报告 | 2026-08-09**

**🔥 开源热点趋势**

🔧 AI 基础工具
- 热门项目：[example/project](https://example.com/example/project)「简介」
- 其他项目：无
"""
        rules = quality.load_quality_config()
        checked = quality.validate_rendered_report(report, rules)
        self.assertFalse(checked["ok"])
        self.assertIn(
            "rendered_project_links_invalid",
            [warning["code"] for warning in checked["warnings"]],
        )

        custom_rules = dict(rules)
        custom_rules["project_link_prefix"] = "https://git.example/"
        custom_report = report.replace(
            "https://example.com/example/project",
            "https://git.example/example/project",
        )
        custom_checked = quality.validate_rendered_report(
            custom_report,
            custom_rules,
        )
        self.assertTrue(custom_checked["ok"], custom_checked["warnings"])

    def test_quality_checker_rejects_mixed_non_http_project_links(self):
        quality = load_module(
            "open_source_quality_mixed_schemes",
            AGENTS_SCRIPTS / "open_source_quality.py",
        )
        source = """
🔧 AI 基础工具
- [example/valid](https://github.com/example/valid)
- [example/ftp](ftp://github.com/example/ftp)
"""
        inspected = quality.inspect_source_projects(source)
        self.assertFalse(inspected["ok"])
        self.assertEqual(inspected["source_project_count"], 2)
        self.assertEqual(inspected["source_unlinked_projects"], ["example/ftp"])

        report = """
📡 **agents-radar 生态报告 | 2026-08-09**

**🔥 开源热点趋势**

🔧 AI 基础工具
- 热门项目：[example/one](https://github.com/example/one)
- 其他项目：[example/two](https://github.com/example/two)、[example/three](https://github.com/example/three)、[example/ftp](ftp://github.com/example/ftp)
"""
        checked = quality.validate_rendered_report(report)
        self.assertFalse(checked["ok"])
        self.assertIn(
            "rendered_project_links_invalid",
            [warning["code"] for warning in checked["warnings"]],
        )

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
