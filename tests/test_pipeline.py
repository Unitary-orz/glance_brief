from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from glance_brief import adapters, cli


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
                    "selection_limits": {
                        "international": {"min": 1, "max": 2},
                        "macro_business": {"min": 1, "max": 2},
                        "ai": {"min": 0, "max": 2},
                    },
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

    def test_failed_render_retry_preserves_prepared_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            config = self._config(directory)
            output = directory / "run"
            output.mkdir()
            prepared = output / "prepared.json"
            prepared.write_text("{}\n", encoding="utf-8")
            response = directory / "model-response.json"
            response.write_text("not json\n", encoding="utf-8")
            config_path = directory / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            args = mock.Mock(
                output_dir=output,
                config=config_path,
                report="noon-news",
                model_response=response,
                date="2026-08-30",
            )
            with self.assertRaisesRegex(ValueError, "malformed model JSON"):
                cli.run_pipeline(args, preserve_artifacts={"prepared.json"})
            self.assertTrue(prepared.is_file())

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
            payload = cli.build_model_payload("noon-news", assembled)
            self.assertEqual(payload["selection_limits"]["international"], {"min": 1, "max": 2})
            payload_text = json.dumps(payload, ensure_ascii=False)
            self.assertIn("candidate_id", payload_text)
            self.assertIn("International title", payload_text)
            self.assertIn("International evidence", payload_text)
            self.assertNotIn("https://wire.test/1", payload_text)
            self.assertNotIn("provenance", payload_text)
            self.assertNotIn("published_at", payload_text)

    def test_configured_text_url_stripping_preserves_candidate_and_trusted_source_link(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            config = self._config(directory)
            source_path = directory / "noon.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            source["items"][0]["summary"] = "International evidence https://unsafe.example/demo with context"
            source_path.write_text(json.dumps(source), encoding="utf-8")
            config["sources"]["wire"]["map"]["strip_urls_from_text"] = True
            config["sources"]["wire"]["map"]["extra"]["description"] = "summary"

            assembled = adapters.assemble_report(config, "noon-news", directory)
            candidate_id = assembled["sections"]["international"][0]
            candidate = assembled["candidate_registry"][candidate_id]
            self.assertEqual(candidate["text"], "International evidence with context")
            self.assertEqual(candidate["extra"]["description"], "International evidence with context")
            self.assertEqual(
                candidate["provenance"][0]["links"][0]["url"],
                "https://wire.test/1",
            )
            payload = cli.build_model_payload("noon-news", assembled)
            self.assertNotIn("unsafe.example", json.dumps(payload, ensure_ascii=False))

    def test_strip_urls_from_text_must_be_boolean(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            config = self._config(directory)
            config["sources"]["wire"]["map"]["strip_urls_from_text"] = "true"
            with self.assertRaisesRegex(ValueError, "strip_urls_from_text must be a boolean"):
                adapters.validate_config(config)

    def test_source_exclude_is_applied_before_binding_take(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            config = self._config(directory)
            source_path = directory / "noon.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            source["items"] = [
                {
                    "title": "Blocked title",
                    "summary": "Blocked evidence",
                    "category": "business",
                    "source": "GitHub Trending",
                    "url": "https://wire.test/blocked",
                },
                {
                    "title": "Allowed title",
                    "summary": "Allowed evidence",
                    "category": "business",
                    "source": "Reuters",
                    "url": "https://wire.test/allowed",
                },
            ]
            source_path.write_text(json.dumps(source), encoding="utf-8")
            config["sources"]["wire"]["exclude"] = {"source": ["GitHub Trending"]}
            config["reports"]["noon-news"]["sections"]["macro_business"] = [
                {"source": "wire", "match": {"category": ["business"]}, "take": 1}
            ]

            adapters.validate_config(config)
            assembled = adapters.assemble_report(config, "noon-news", directory)

            selected = assembled["sections"]["macro_business"]
            self.assertEqual(len(selected), 1)
            candidate = assembled["candidate_registry"][selected[0]]
            self.assertEqual(candidate["title"], "Allowed title")
            self.assertEqual(assembled["source_exclusions"], {"wire": 1})
            self.assertNotIn("https://wire.test/blocked", adapters.source_urls(assembled))

    def test_source_exclude_requires_non_empty_string_sets(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            invalid_values = ({}, {"source": []}, {"source": [""]}, {"source": [1]}, {"": ["blocked"]})
            for exclude in invalid_values:
                config = self._config(directory)
                config["sources"]["wire"]["exclude"] = exclude
                with self.assertRaises(ValueError):
                    adapters.validate_config(config)

    def test_unsafe_candidate_url_is_rejected_without_poisoning_source(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            config = self._config(directory)
            source_path = directory / "noon.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            source["items"].append({
                "title": "Crawler community: https://discord.example/invite",
                "summary": "Join here https://discord.example/invite",
                "category": "business",
                "url": "https://wire.test/unsafe",
            })
            source_path.write_text(json.dumps(source), encoding="utf-8")

            assembled = adapters.assemble_report(config, "noon-news", directory)
            payload = cli.build_model_payload("noon-news", assembled)
            payload_text = json.dumps(payload, ensure_ascii=False)

            self.assertNotIn("discord.example", payload_text)
            self.assertEqual(len(payload["sections"]["macro_business"]), 1)
            self.assertEqual(
                assembled["candidate_rejections"]["wire"],
                [{"index": 2, "error": "candidate title/text must not contain a URL"}],
            )

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
            variable = "GLANCE_BRIEF_TEST_SECRET"
            previous = os.environ.get(variable)
            os.environ[variable] = "must-not-leak"
            try:
                source = {
                    "driver": "command_json",
                    "command": [
                        sys.executable,
                        "-c",
                        "import json,os; print(json.dumps({'secret': os.getenv('GLANCE_BRIEF_TEST_SECRET')}))",
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
    CONFIG = ROOT / "config" / "brief.example.json"
    CLI = ROOT / "glance_brief" / "cli.py"

    def _assembled(self, report):
        config = json.loads(self.CONFIG.read_text(encoding="utf-8"))
        return adapters.assemble_report(config, report, self.CONFIG.parent)

    def _agent_descriptions(self, assembled):
        open_metadata = assembled["metadata"]["open_source"]
        names = [item["full_name"] for item in open_metadata["fresh_hot"]]
        names.extend(
            name
            for category in open_metadata["local_report_categories"]
            for name in category["projects"][:3]
        )
        by_name = {}
        for cid in assembled["sections"]["open_source"]:
            candidate = assembled["candidate_registry"][cid]
            by_name[candidate["extra"]["full_name"]] = cid
        return [
            {"candidate_id": by_name[name], "description_zh": "用于 AI 工作流的工具。"}
            for name in dict.fromkeys(names)
        ]

    def test_agents_payload_exposes_only_program_owned_display_ids(self):
        assembled = self._assembled("agents-report")
        payload = cli.build_model_payload("agents-report", assembled)
        expected = [item["candidate_id"] for item in self._agent_descriptions(assembled)]
        self.assertEqual(payload["open_source_display_ids"], expected)
        self.assertTrue(set(payload["open_source_display_ids"]).issubset(set(assembled["sections"]["open_source"])))
        hidden = set(assembled["sections"]["open_source"]) - set(expected)
        self.assertTrue(hidden.isdisjoint(set(payload["open_source_display_ids"])))
        self.assertEqual(hidden, set())
        payload_text = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("stars_today", payload_text)
        self.assertNotIn("provenance", payload_text)

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
                "macro_business": [{"candidate_id": ids["macro_business"], "summary": "企业发布季度经营说明。"}],
                "ai": [{"candidate_id": ids["ai"], "summary": "智能体工具增加审计能力。"}],
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

    def test_replay_rebuilds_identical_report_without_sources_or_model(self):
        assembled = self._assembled("noon-news")
        ids = {key: values[0] for key, values in assembled["sections"].items()}
        model = {
            "top_points": [{"candidate_id": ids["international"], "topic": "国际", "fact": "国际合作发布联合说明"}],
            "sections": {
                "international": [{"candidate_id": ids["international"], "summary": "国际合作发布联合说明。"}],
                "macro_business": [{"candidate_id": ids["macro_business"], "summary": "企业发布季度经营说明。"}],
                "ai": [{"candidate_id": ids["ai"], "summary": "智能体工具增加审计能力。"}],
            },
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / "original"
            replayed = root / "replayed"
            completed = self._run("noon-news", model, original)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            replay = subprocess.run(
                [sys.executable, str(self.CLI), "replay", "--input-dir", str(original), "--output-dir", str(replayed)],
                cwd=ROOT, text=True, capture_output=True,
            )
            self.assertEqual(replay.returncode, 0, replay.stderr)
            self.assertEqual((replayed / "report.md").read_bytes(), (original / "report.md").read_bytes())
            self.assertEqual((replayed / "resolved.json").read_bytes(), (original / "resolved.json").read_bytes())
            manifest = json.loads((replayed / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["mode"], "replay")
            self.assertEqual(manifest["replay_source_manifest_sha256"], self._sha256(original / "manifest.json"))

    def test_replay_rejects_tampered_snapshot_before_resolution(self):
        assembled = self._assembled("noon-news")
        ids = {key: values[0] for key, values in assembled["sections"].items()}
        model = {
            "top_points": [],
            "sections": {
                "international": [{"candidate_id": ids["international"], "summary": "国际合作发布联合说明。"}],
                "macro_business": [{"candidate_id": ids["macro_business"], "summary": "企业发布季度经营说明。"}],
                "ai": [{"candidate_id": ids["ai"], "summary": "智能体工具增加审计能力。"}],
            },
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / "original"
            replayed = root / "replayed"
            completed = self._run("noon-news", model, original)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            with (original / "assembled.json").open("a", encoding="utf-8") as handle:
                handle.write(" ")
            replay = subprocess.run(
                [sys.executable, str(self.CLI), "replay", "--input-dir", str(original), "--output-dir", str(replayed)],
                cwd=ROOT, text=True, capture_output=True,
            )
            self.assertNotEqual(replay.returncode, 0)
            failure = json.loads((replayed / "failure.json").read_text(encoding="utf-8"))
            self.assertIn("hash mismatch", failure["error"])
            self.assertFalse((replayed / "report.md").exists())
            manifest = json.loads((replayed / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "failed")

    def test_model_response_inside_output_directory_survives_run_startup_cleanup(self):
        assembled = self._assembled("noon-news")
        ids = {key: values[0] for key, values in assembled["sections"].items()}
        model = {
            "top_points": [],
            "sections": {
                "international": [{"candidate_id": ids["international"], "summary": "国际合作发布联合说明。"}],
                "macro_business": [{"candidate_id": ids["macro_business"], "summary": "企业发布季度经营说明。"}],
                "ai": [{"candidate_id": ids["ai"], "summary": "智能体工具增加审计能力。"}],
            },
        }
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "noon"
            output.mkdir(parents=True)
            response = output / "model-response.input.json"
            response.write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(self.CLI), "run", "--config", str(self.CONFIG),
                 "--report", "noon-news", "--output-dir", str(output),
                 "--model-response", str(response), "--date", "2026-08-30"],
                cwd=ROOT, text=True, capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((output / "report.md").is_file())

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
            "ai_ecosystem": [{"candidate_ids": [ai_id], "topic": "审计协作", "summary": "智能体生态增加可审计协作能力。"}],
            "open_source_trends": [
                {"summary": "开源工具继续向可组合工作流整合。"},
                {"summary": "社区基础设施更重视评测与本地部署。"},
            ],
            "open_source_descriptions": self._agent_descriptions(assembled),
        }
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "agents"
            completed = self._run("agents-report", model, output)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            markdown = (output / "report.md").read_text(encoding="utf-8")
            codex = json.loads((ROOT / "tests" / "fixtures" / "pipeline" / "codexradar.json").read_text(encoding="utf-8"))["markdown"]
            self.assertIn(codex, markdown)
            self.assertIn("**✨新热门开源**", markdown)
            self.assertIn("[fixture-labs/agent-workflow](https://github.com/fixture-labs/agent-workflow)", markdown)
            self.assertIn("用于 AI 工作流的工具。", markdown)
            self.assertNotIn("A composable agent workflow toolkit.", markdown)
            self.assertIn("① 🤖 AI 智能体/工作流", markdown)
            self.assertNotIn("其他项目", markdown)
            self.assertNotIn("\n---\n", markdown)
            payload = (output / "model-payload.json").read_text(encoding="utf-8")
            self.assertNotIn(codex, payload)
            self.assertNotIn("stars_today", payload)

    def test_agent_handoff_renders_agents_from_prepared_artifacts_without_reloading_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "agents-handoff"
            output.mkdir()
            stale_response = output / "model-response.input.json"
            stale_response.write_text('{"stale": true}', encoding="utf-8")
            prepare_args = type("Args", (), {
                "config": self.CONFIG,
                "report": "agents-report",
                "output_dir": output,
                "date": "2026-08-31",
                "model": "MiniMax-M3",
                "provider": "minimax-cn",
                "reasoning": "low",
            })()
            prepared_path = cli.prepare_pipeline(prepare_args)
            self.assertEqual(prepared_path, output / "prepared.json")
            self.assertFalse(stale_response.exists())
            for name in ("assembled.json", "model-payload.json", "model-prompt.txt", "prepared.json"):
                self.assertTrue((output / name).is_file(), name)
            self.assertFalse((output / "report.md").exists())

            assembled = json.loads((output / "assembled.json").read_text(encoding="utf-8"))
            ai_id = assembled["sections"]["ai_ecosystem"][0]
            response = output / "model-response.input.json"
            response.write_text(json.dumps({
                "ai_ecosystem": [{"candidate_ids": [ai_id], "topic": "审计协作", "summary": "智能体生态增加可审计协作能力。"}],
                "open_source_trends": [
                    {"summary": "开源工具继续向可组合工作流整合。"},
                    {"summary": "社区基础设施更重视评测与本地部署。"},
                ],
                "open_source_descriptions": self._agent_descriptions(assembled),
            }, ensure_ascii=False), encoding="utf-8")
            render_args = type("Args", (), {
                "config": self.CONFIG,
                "output_dir": output,
                "model_response": response,
            })()
            with mock.patch.object(adapters, "assemble_report", side_effect=AssertionError("sources reloaded")):
                report_path = cli.render_prepared_pipeline(render_args)
            self.assertEqual(report_path, output / "report.md")
            self.assertIn("agents-radar 生态报告", report_path.read_text(encoding="utf-8"))
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "ok")
            self.assertEqual(manifest["mode"], "agent-handoff")

    def test_agent_handoff_rejects_tampered_prepared_assembly(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "agents-handoff"
            prepare_args = type("Args", (), {
                "config": self.CONFIG,
                "report": "agents-report",
                "output_dir": output,
                "date": "2026-08-31",
                "model": "MiniMax-M3",
                "provider": "minimax-cn",
                "reasoning": "low",
            })()
            cli.prepare_pipeline(prepare_args)
            with (output / "assembled.json").open("a", encoding="utf-8") as handle:
                handle.write(" ")
            response = output / "model-response.input.json"
            response.write_text("{}", encoding="utf-8")
            render_args = type("Args", (), {
                "config": self.CONFIG,
                "output_dir": output,
                "model_response": response,
            })()
            with self.assertRaisesRegex(ValueError, "prepared artifact hash mismatch for assembled.json"):
                cli.render_prepared_pipeline(render_args)
            self.assertFalse((output / "report.md").exists())
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "failed")

    def test_agent_handoff_cli_prepare_and_render_prepared(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp) / "run"
            prepare = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "glance_brief",
                    "prepare",
                    "--config",
                    str(self.CONFIG),
                    "--report",
                    "agents-report",
                    "--output-dir",
                    str(run_dir),
                    "--date",
                    "2026-08-31",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(prepare.returncode, 0, prepare.stderr)
            self.assertEqual(Path(prepare.stdout.strip()), run_dir / "prepared.json")

            assembled = json.loads((run_dir / "assembled.json").read_text(encoding="utf-8"))
            ai_id = assembled["sections"]["ai_ecosystem"][0]
            semantic = {
                "ai_ecosystem": [{"candidate_ids": [ai_id], "topic": "版本发布", "summary": "Release candidate is available."}],
                "open_source_trends": [
                    {"summary": "智能体工具持续走向专业工作流。"},
                    {"summary": "本地部署与自动化协作获得更多关注。"},
                ],
                "open_source_descriptions": self._agent_descriptions(assembled),
            }
            response_path = run_dir / "model-response.input.json"
            response_path.write_text(json.dumps(semantic, ensure_ascii=False), encoding="utf-8")
            render = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "glance_brief",
                    "render-prepared",
                    "--config",
                    str(self.CONFIG),
                    "--output-dir",
                    str(run_dir),
                    "--model-response",
                    str(response_path),
                    "--stdout-report",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(render.returncode, 0, render.stderr)
            self.assertEqual(render.stdout, (run_dir / "report.md").read_text(encoding="utf-8"))

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
