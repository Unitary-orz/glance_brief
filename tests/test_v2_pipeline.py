from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v2 import adapters, run_v2


class AssemblyAndPayloadTests(unittest.TestCase):
    def _config(self, directory: Path):
        noon_path = directory / "noon.json"
        noon_path.write_text(json.dumps({
            "items": [
                {"title": "International title", "summary": "International evidence", "category": "international", "url": "https://wire.test/1"},
                {"title": "Business title", "summary": "Business evidence", "category": "business", "url": "https://wire.test/2"},
            ]
        }), encoding="utf-8")
        return {
            "schema_version": 2,
            "sources": {
                "wire": {
                    "driver": "json_file", "path": "noon.json", "items_path": "items",
                    "channel_id": "wire", "channel_label": "NS",
                    "map": {
                        "title": "title", "text": "summary",
                        "extra": {"category": "category"},
                        "links": [{"role": "article", "label": "Reuters", "path": "url"}],
                    },
                }
            },
            "reports": {
                "noon-news": {
                    "sections": {
                        "international": [{"source": "wire", "match": {"category": ["international"]}}],
                        "macro_business": [{"source": "wire", "match": {"category": ["business"]}}],
                        "ai": [],
                    }
                }
            },
        }

    def test_required_source_failure_is_hard_gate_after_diagnostics_are_assembled(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            config = self._config(directory)
            config["sources"]["wire"]["required"] = True
            config["sources"]["wire"]["path"] = "missing.json"
            assembled = adapters.assemble_report(config, "noon-news", directory)
            self.assertIn("wire", assembled["source_errors"])
            with self.assertRaisesRegex(ValueError, "required source wire failed"):
                adapters.validate_assembly_health(config, "noon-news", assembled)

    def test_section_minimum_candidates_is_enforced_before_model_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            config = self._config(directory)
            config["reports"]["noon-news"]["minimum_candidates"] = {
                "international": 2,
                "macro_business": 1,
                "ai": 0,
            }
            assembled = adapters.assemble_report(config, "noon-news", directory)
            with self.assertRaisesRegex(ValueError, "international needs at least 2 candidates"):
                adapters.validate_assembly_health(config, "noon-news", assembled)

    def test_command_json_failure_modes_are_recorded_and_isolated(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            cases = [
                (
                    "exit-1",
                    {
                        "driver": "command_json",
                        "command": [sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"],
                        "cwd": str(directory),
                        "map": {},
                    },
                    "exited with 3",
                ),
                (
                    "malformed",
                    {
                        "driver": "command_json",
                        "command": [sys.executable, "-c", "print('not json')"],
                        "cwd": str(directory),
                        "map": {},
                    },
                    "Expecting value",
                ),
            ]
            for _, source, expected in cases:
                with self.assertRaisesRegex(Exception, expected):
                    adapters.load_source("command", source, directory)
            config = self._config(directory)
            config["sources"]["wire"]["driver"] = "command_json"
            config["sources"]["wire"]["command"] = [sys.executable, "-c", "import sys; sys.exit(2)"]
            config["sources"]["wire"]["cwd"] = str(directory)
            assembled = adapters.assemble_report(config, "noon-news", directory)
            self.assertIn("wire", assembled["source_errors"])
            self.assertEqual(assembled["sections"]["international"], [])
            # A non-required failing source must not block assembly of the rest.
            self.assertEqual(assembled["sections"]["macro_business"], [])

    def test_assembly_is_bounded_and_payload_contains_only_lean_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            config = self._config(directory)
            assembled = adapters.assemble_report(config, "noon-news", directory)
            self.assertEqual(len(assembled["candidate_registry"]), 2)
            self.assertEqual(len(assembled["sections"]["international"]), 1)
            self.assertEqual(len(assembled["sections"]["macro_business"]), 1)
            payload = run_v2.build_model_payload("noon-news", assembled)
            payload_text = json.dumps(payload, ensure_ascii=False)
            self.assertIn("candidate_id", payload_text)
            self.assertIn("International title", payload_text)
            self.assertIn("International evidence", payload_text)
            self.assertNotIn("https://wire.test/1", payload_text)
            self.assertNotIn("provenance", payload_text)
            self.assertNotIn("published_at", payload_text)

    def test_candidate_digest_does_not_depend_on_position(self):
        source = {
            "channel_id": "wire", "channel_label": "NS",
            "map": {"title": "title", "text": "text", "links": [{"role": "article", "label": "Reuters", "path": "url"}]},
        }
        first = {"title": "same", "text": "same evidence", "url": "https://wire.test/same"}
        second = dict(first)
        self.assertEqual(
            adapters.normalize_candidate("wire", source, first)["candidate_id"],
            adapters.normalize_candidate("wire", source, second)["candidate_id"],
        )

    def test_command_json_only_receives_allowlisted_environment(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            variable = "GLANCE_V2_TEST_SECRET"
            previous = os.environ.get(variable)
            os.environ[variable] = "must-not-leak"
            try:
                source = {
                    "driver": "command_json",
                    "command": [
                        sys.executable,
                        "-c",
                        "import json,os; print(json.dumps({'secret': os.getenv('GLANCE_V2_TEST_SECRET')}))",
                    ],
                    "cwd": str(directory),
                    "env_allowlist": [],
                    "map": {},
                }
                adapters._validate_source("command", source)
                payload = adapters.load_source("command", source, directory)
                self.assertIsNone(payload["secret"])
            finally:
                if previous is None:
                    os.environ.pop(variable, None)
                else:
                    os.environ[variable] = previous


class OfflinePipelineTests(unittest.TestCase):
    CONFIG = ROOT / "v2" / "config" / "brief.example.json"
    CLI = ROOT / "v2" / "run_v2.py"

    def _assembled(self, report):
        config = json.loads(self.CONFIG.read_text(encoding="utf-8"))
        return adapters.assemble_report(config, report, self.CONFIG.parent)

    def _run(self, report, response, output):
        response_path = output.parent / f"{report}-response.json"
        response_path.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
        return subprocess.run(
            [
                sys.executable,
                str(self.CLI),
                "run",
                "--config",
                str(self.CONFIG),
                "--report",
                report,
                "--output-dir",
                str(output),
                "--model-response",
                str(response_path),
                "--date",
                "2026-08-30",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

    def test_successful_run_writes_manifest_with_input_output_hashes(self):
        assembled = self._assembled("noon-news")
        ids = {key: values[0] for key, values in assembled["sections"].items()}
        model = {
            "top_points": [
                {"candidate_id": ids["international"], "topic": "国际", "fact": "国际合作发布联合说明"},
            ],
            "sections": {
                "international": [{"candidate_id": ids["international"], "summary": "国际合作发布联合说明。"}],
                "macro_business": [],
                "ai": [],
            },
        }
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "noon"
            completed = self._run("noon-news", model, output)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["report"], "noon-news")
            self.assertEqual(manifest["status"], "ok")
            self.assertIn("config_sha256", manifest)
            self.assertIn("assembled_json_sha256", manifest)
            self.assertIn("model-payload_json_sha256", manifest)
            self.assertIn("model-response_raw_txt_sha256", manifest)
            self.assertIn("resolved_json_sha256", manifest)
            self.assertIn("report_md_sha256", manifest)
            for name in ("assembled.json", "model-payload.json", "model-response.raw.txt", "resolved.json", "report.md"):
                self.assertEqual(manifest[f"{name.replace('.', '_')}_sha256"], self._sha256(output / name))

    def _sha256(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_model_output_size_is_hard_limited(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "noon"
            response = output.parent / "response.json"
            response.write_text('{"top_points": [], "sections": {"international": [{"candidate_id": "c' + "0" * 32 + '", "summary": "' + "长" * 2000 + '"}], "macro_business": [], "ai": []}}', encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(self.CLI), "run", "--config", str(self.CONFIG),
                 "--report", "noon-news", "--output-dir", str(output),
                 "--model-response", str(response), "--date", "2026-08-30"],
                cwd=ROOT, text=True, capture_output=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertTrue((output / "failure.json").is_file())
            self.assertFalse((output / "report.md").exists())

    def test_noon_fixture_pipeline_writes_complete_artifacts_and_exact_sources(self):
        assembled = self._assembled("noon-news")
        ids = {key: values[0] for key, values in assembled["sections"].items()}
        model = {
            "top_points": [
                {"candidate_id": ids["international"], "topic": "国际", "fact": "国际合作发布联合说明"},
                {"candidate_id": ids["macro_business"], "topic": "商业", "fact": "企业发布季度经营说明"},
                {"candidate_id": ids["ai"], "topic": "AI", "fact": "智能体工具增加审计能力"},
            ],
            "sections": {
                "international": [{"candidate_id": ids["international"], "summary": "国际合作发布联合说明。", "headline_zh": "国际代表发布海上科研合作联合说明"}],
                "macro_business": [{"candidate_id": ids["macro_business"], "summary": "企业发布季度经营说明。"}],
                "ai": [{"candidate_id": ids["ai"], "summary": "智能体工具增加审计能力。"}],
            },
        }
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "noon"
            completed = self._run("noon-news", model, output)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            for name in (
                "assembled.json", "model-payload.json", "model-prompt.txt",
                "model-response.raw.txt", "model-response.json", "resolved.json",
                "warnings.json", "usage.json", "report.md",
            ):
                self.assertTrue((output / name).is_file(), name)
            markdown = (output / "report.md").read_text(encoding="utf-8")
            self.assertNotIn("\n---\n", markdown)
            self.assertIn("### 分类详情", markdown)
            self.assertIn("[AIHOT](https://example.com/fixtures/ai/item/agent-audit-workflow)", markdown)
            self.assertIn("[Example AI Lab](https://example.com/fixtures/ai/original/agent-audit-workflow)", markdown)
            payload = (output / "model-payload.json").read_text(encoding="utf-8")
            self.assertNotIn("https://", payload)

    def test_agents_fixture_pipeline_preserves_codex_and_program_owned_projects(self):
        assembled = self._assembled("agents-report")
        ai_id = assembled["sections"]["ai_ecosystem"][0]
        model = {
            "ai_ecosystem": [{"candidate_id": ai_id, "summary": "智能体生态增加可审计协作能力。"}],
            "open_source_trends": [
                {"summary": "开源工具继续向可组合工作流整合。"},
                {"summary": "社区基础设施更重视评测与本地部署。"},
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "agents"
            completed = self._run("agents-report", model, output)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            markdown = (output / "report.md").read_text(encoding="utf-8")
            codex = json.loads((ROOT / "v2" / "fixtures" / "codexradar.json").read_text(encoding="utf-8"))["markdown"]
            self.assertIn(codex, markdown)
            self.assertIn("**✨新热门开源**", markdown)
            self.assertIn("[fixture-labs/agent-workflow](https://github.com/fixture-labs/agent-workflow)", markdown)
            self.assertIn("① 🤖 AI 智能体/工作流", markdown)
            self.assertNotIn("其他项目", markdown)
            self.assertNotIn("\n---\n", markdown)
            payload = (output / "model-payload.json").read_text(encoding="utf-8")
            self.assertNotIn(codex, payload)
            self.assertNotIn("stars_today", payload)

    def test_invalid_model_response_keeps_failure_evidence_without_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            response = root / "invalid.txt"
            response.write_text("not json", encoding="utf-8")
            output = root / "invalid-output"
            completed = subprocess.run(
                [
                    sys.executable, str(self.CLI), "run", "--config", str(self.CONFIG),
                    "--report", "noon-news", "--output-dir", str(output),
                    "--model-response", str(response), "--date", "2026-08-30",
                ],
                cwd=ROOT, text=True, capture_output=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertTrue((output / "model-response.raw.txt").is_file())
            self.assertTrue((output / "failure.json").is_file())
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "failed")
            self.assertIn("model-response_raw_txt_sha256", manifest)
            self.assertFalse((output / "report.md").exists())
            self.assertFalse((output / "resolved.json").exists())


if __name__ == "__main__":
    unittest.main()
