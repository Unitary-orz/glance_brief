from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from glance_brief import adapters


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install" / "install.py"


class FormalInstallerTests(unittest.TestCase):
    def _run(self, *args: str, prefix: Path) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONPYCACHEPREFIX"] = str(prefix / "pycache")
        return subprocess.run(
            [sys.executable, str(INSTALLER), *args, "--prefix", str(prefix)],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def _write_runtime_config(self, home: Path) -> Path:
        source = ROOT / "config" / "brief.example.json"
        config = json.loads(source.read_text(encoding="utf-8"))
        for spec in config["sources"].values():
            if spec["driver"] == "json_file":
                spec["path"] = str((source.parent / spec["path"]).resolve())
        target = home / "data" / "glance-brief" / "config" / "brief.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return target

    def _agent_descriptions(self, assembled):
        open_metadata = assembled["metadata"]["open_source"]
        names = [item["full_name"] for item in open_metadata["fresh_hot"]]
        names.extend(category["projects"][0] for category in open_metadata["local_report_categories"])
        by_name = {}
        for cid in assembled["sections"]["open_source"]:
            candidate = assembled["candidate_registry"][cid]
            by_name[candidate["extra"]["full_name"]] = cid
        return [
            {"candidate_id": by_name[name], "description_zh": "用于 AI 工作流的工具。"}
            for name in dict.fromkeys(names)
        ]

    def test_verify_requires_runtime_config_before_job_is_runnable(self):
        with TemporaryDirectory() as temp:
            home = Path(temp)
            installed = self._run(
                "install", "--runtime", "hermes",
                "--components", "agents-report,noon-news", prefix=home,
            )
            self.assertEqual(installed.returncode, 0, installed.stderr)
            (home / "cron").mkdir(parents=True)
            (home / "cron" / "jobs.json").write_text(
                json.dumps({"jobs": [{"script": "glance-brief/noon-news.py"}]}),
                encoding="utf-8",
            )
            verified = self._run("verify", "--runtime", "hermes", prefix=home)
            self.assertEqual(verified.returncode, 1, verified.stdout + verified.stderr)
            checks = {item["check"]: item for item in json.loads(verified.stdout)["checks"]}
            self.assertIn("runtime-config", checks)
            self.assertFalse(checks["runtime-config"]["ok"])
            self.assertIn("brief.json", checks["runtime-config"]["detail"])

    def test_verify_checks_only_the_installed_component_entrypoints(self):
        with TemporaryDirectory() as temp:
            home = Path(temp)
            installed = self._run(
                "install", "--runtime", "hermes", "--components", "noon-news", prefix=home,
            )
            self.assertEqual(installed.returncode, 0, installed.stderr)
            self._write_runtime_config(home)
            (home / "cron").mkdir(parents=True)
            (home / "cron" / "jobs.json").write_text(
                json.dumps({"jobs": [{"script": "glance-brief/noon-news.py"}]}),
                encoding="utf-8",
            )
            verified = self._run("verify", "--runtime", "hermes", prefix=home)
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            check_names = {item["check"] for item in json.loads(verified.stdout)["checks"]}
            self.assertIn("entrypoint:glance-brief.py", check_names)
            self.assertIn("entrypoint:noon-news.py", check_names)
            self.assertNotIn("entrypoint:agents-report.py", check_names)
            self.assertNotIn("entrypoint:agents-quality-check.py", check_names)
            self.assertNotIn("entrypoint:codexradar.py", check_names)

    def test_doctor_requires_runtime_config(self):
        with TemporaryDirectory() as temp:
            home = Path(temp)
            installed = self._run(
                "install", "--runtime", "hermes", "--components", "noon-news", prefix=home,
            )
            self.assertEqual(installed.returncode, 0, installed.stderr)
            doctor = self._run("doctor", "--runtime", "hermes", prefix=home)
            self.assertEqual(doctor.returncode, 1, doctor.stdout + doctor.stderr)
            result = json.loads(doctor.stdout)
            self.assertEqual(result["components"]["runtime"]["runtime-config"]["status"], "error")
            self.assertIn("brief.json", result["components"]["runtime"]["runtime-config"]["detail"])

    def test_doctor_does_not_expect_model_fields_on_no_agent_jobs(self):
        with TemporaryDirectory() as temp:
            home = Path(temp)
            installed = self._run(
                "install", "--runtime", "hermes", "--components", "noon-news", prefix=home,
            )
            self.assertEqual(installed.returncode, 0, installed.stderr)
            self._write_runtime_config(home)
            (home / "cron").mkdir(parents=True)
            (home / "cron" / "jobs.json").write_text(
                json.dumps({"jobs": [{
                    "id": "fixture-noon",
                    "name": "noon-news",
                    "script": "glance-brief/noon-news.py",
                    "no_agent": True,
                    "deliver": "origin",
                }]}),
                encoding="utf-8",
            )
            doctor = self._run("doctor", "--runtime", "hermes", prefix=home)
            self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
            runtime_checks = json.loads(doctor.stdout)["components"]["runtime"]
            self.assertFalse(any(name.startswith("model:") for name in runtime_checks), runtime_checks)

    def test_both_components_install_shared_core_and_installed_cli_runs(self):
        with TemporaryDirectory() as temp:
            home = Path(temp)
            installed = self._run(
                "install",
                "--runtime",
                "hermes",
                "--components",
                "agents-report,noon-news",
                prefix=home,
            )
            self.assertEqual(installed.returncode, 0, installed.stderr)
            result = json.loads(installed.stdout)
            self.assertTrue(result["ok"])
            self.assertEqual(result["project_version"], "0.3.0")
            self.assertEqual(len(result["jobs_to_create"]), 2)
            for job in result["jobs_to_create"]:
                self.assertTrue(job["no_agent"])
                self.assertNotIn("prompt", job)

            scripts = home / "scripts" / "glance-brief"
            data = home / "data" / "glance-brief"
            core = scripts / "lib" / "glance_brief"
            for relative in (
                "__init__.py",
                "__main__.py",
                "cli.py",
                "adapters.py",
                "contracts.py",
                "resolve.py",
                "render_report.py",
                "prompts/agents-report.md",
                "prompts/noon-news.md",
            ):
                self.assertTrue((core / relative).is_file(), relative)
            self.assertTrue((scripts / "glance-brief.py").is_file())
            self.assertTrue((data / "config" / "brief.example.json").is_file())

            manifest = json.loads(
                (data / "install-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["project_version"], "0.3.0")
            self.assertEqual(manifest["core_entrypoint"], "glance-brief.py")
            owned = {item["path"] for item in manifest["owned_files"]}
            self.assertIn("lib/glance_brief/cli.py", owned)
            self.assertIn("lib/glance_brief/prompts/noon-news.md", owned)
            self.assertIn("glance-brief.py", owned)

            cli = subprocess.run(
                [
                    sys.executable,
                    str(scripts / "glance-brief.py"),
                    "check",
                    "--config",
                    str(ROOT / "config" / "brief.example.json"),
                ],
                cwd=ROOT,
                env={**os.environ, "PYTHONPYCACHEPREFIX": str(home / "pycache-cli")},
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(cli.returncode, 0, cli.stderr)
            self.assertEqual(cli.stdout.strip(), "configuration ok")

            jobs = {
                "jobs": [
                    {"id": "fixture-agents", "name": "agents-report", "script": "glance-brief/agents-report.py"},
                    {"id": "fixture-noon", "name": "noon-news", "script": "glance-brief/noon-news.py"},
                ]
            }
            (home / "cron").mkdir(parents=True)
            (home / "cron" / "jobs.json").write_text(
                json.dumps(jobs), encoding="utf-8"
            )
            self._write_runtime_config(home)
            verified = self._run("verify", "--runtime", "hermes", prefix=home)
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            self.assertTrue(json.loads(verified.stdout)["ok"])

    def test_installed_report_entrypoints_render_both_reports_through_shared_core(self):
        config_path = ROOT / "config" / "brief.example.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        noon_assembled = adapters.assemble_report(config, "noon-news", config_path.parent)
        noon_ids = {key: values[0] for key, values in noon_assembled["sections"].items()}
        agents_assembled = adapters.assemble_report(config, "agents-report", config_path.parent)
        ai_id = agents_assembled["sections"]["ai_ecosystem"][0]
        responses = {
            "noon-news": {
                "top_points": [
                    {"candidate_id": noon_ids["international"], "topic": "国际", "fact": "国际合作发布联合说明"}
                ],
                "sections": {
                    "international": [{"candidate_id": noon_ids["international"], "summary": "国际合作发布联合说明。"}],
                    "macro_business": [{"candidate_id": noon_ids["macro_business"], "summary": "企业发布季度经营说明。"}],
                    "ai": [{"candidate_id": noon_ids["ai"], "summary": "智能体工具增加审计能力。"}],
                },
            },
            "agents-report": {
                "ai_ecosystem": [{"candidate_ids": [ai_id], "topic": "审计协作", "summary": "智能体生态增加可审计协作能力。"}],
                "open_source_descriptions": self._agent_descriptions(agents_assembled),
                "open_source_trends": [
                    {"summary": "开源工具继续向可组合工作流整合。"},
                    {"summary": "社区基础设施更重视评测与本地部署。"},
                ],
            },
        }
        expected_titles = {
            "noon-news": "📰 今日热点简报",
            "agents-report": "📡 **agents-radar 生态报告 | 2026-08-30**",
        }

        with TemporaryDirectory() as temp:
            home = Path(temp)
            installed = self._run(
                "install", "--runtime", "hermes",
                "--components", "agents-report,noon-news", prefix=home,
            )
            self.assertEqual(installed.returncode, 0, installed.stderr)
            scripts = home / "scripts" / "glance-brief"
            for report, response in responses.items():
                response_path = home / f"{report}-response.json"
                response_path.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
                output = home / "runs" / report
                env = {
                    **os.environ,
                    "PYTHONPYCACHEPREFIX": str(home / "pycache-entrypoints"),
                    "HERMES_HOME": str(home),
                    "GLANCE_BRIEF_CONFIG": str(config_path),
                    "GLANCE_BRIEF_MODEL_RESPONSE": str(response_path),
                    "GLANCE_BRIEF_OUTPUT_DIR": str(output),
                    "GLANCE_BRIEF_DATE": "2026-08-30",
                }
                completed = subprocess.run(
                    [sys.executable, str(scripts / f"{report}.py")],
                    cwd=ROOT,
                    env=env,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertTrue(completed.stdout.startswith(expected_titles[report]), completed.stdout)
                self.assertNotIn(str(output / "report.md"), completed.stdout)
                self.assertTrue((output / "report.md").is_file())

    def test_installed_hermes_adapter_invokes_one_model_process_then_core(self):
        config_path = ROOT / "config" / "brief.example.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        assembled = adapters.assemble_report(config, "noon-news", config_path.parent)
        ids = {key: values[0] for key, values in assembled["sections"].items()}
        response = {
            "top_points": [
                {"candidate_id": ids["international"], "topic": "国际", "fact": "国际合作发布联合说明"}
            ],
            "sections": {
                "international": [{"candidate_id": ids["international"], "summary": "国际合作发布联合说明。"}],
                "macro_business": [{"candidate_id": ids["macro_business"], "summary": "企业发布季度经营说明。"}],
                "ai": [{"candidate_id": ids["ai"], "summary": "智能体工具增加审计能力。"}],
            },
        }
        with TemporaryDirectory() as temp:
            home = Path(temp)
            installed = self._run(
                "install", "--runtime", "hermes", "--components", "noon-news", prefix=home,
            )
            self.assertEqual(installed.returncode, 0, installed.stderr)
            fake_hermes = home / "fake-hermes"
            fake_hermes.write_text(
                f"#!{sys.executable}\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "Path(os.environ['FAKE_HERMES_ARGV']).write_text(json.dumps(sys.argv[1:]), encoding='utf-8')\n"
                "sys.stdout.write(os.environ['FAKE_HERMES_RESPONSE'])\n",
                encoding="utf-8",
            )
            fake_hermes.chmod(0o755)
            argv_path = home / "fake-hermes-argv.json"
            output = home / "runs" / "noon-news"
            env = {
                **os.environ,
                "PYTHONPYCACHEPREFIX": str(home / "pycache-model-adapter"),
                "HERMES_HOME": str(home),
                "GLANCE_BRIEF_CONFIG": str(config_path),
                "GLANCE_BRIEF_HERMES": str(fake_hermes),
                "GLANCE_BRIEF_MODEL": "fixture-model",
                "GLANCE_BRIEF_PROVIDER": "fixture-provider",
                "GLANCE_BRIEF_REASONING": "low",
                "GLANCE_BRIEF_OUTPUT_DIR": str(output),
                "GLANCE_BRIEF_DATE": "2026-08-30",
                "FAKE_HERMES_ARGV": str(argv_path),
                "FAKE_HERMES_RESPONSE": json.dumps(response, ensure_ascii=False),
            }
            completed = subprocess.run(
                [sys.executable, str(home / "scripts" / "glance-brief" / "noon-news.py")],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(completed.stdout.startswith("📰 今日热点简报"), completed.stdout)
            model_argv = json.loads(argv_path.read_text(encoding="utf-8"))
            self.assertEqual(model_argv[0], "chat")
            self.assertEqual(model_argv.count("-q"), 1)
            prompt = model_argv[model_argv.index("-q") + 1]
            self.assertNotIn("https://", prompt)
            self.assertNotIn("http://", prompt)
            self.assertEqual(model_argv[model_argv.index("--model") + 1], "fixture-model")
            self.assertEqual(model_argv[model_argv.index("--provider") + 1], "fixture-provider")
            usage = json.loads((output / "usage.json").read_text(encoding="utf-8"))
            self.assertEqual(usage["mode"], "hermes-runtime-adapter")
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "ok")
            self.assertEqual(manifest["model"], "fixture-model")
            self.assertEqual(manifest["provider"], "fixture-provider")

    def test_dry_run_lists_core_without_writing(self):
        with TemporaryDirectory() as temp:
            home = Path(temp)
            completed = self._run(
                "install",
                "--runtime",
                "hermes",
                "--components",
                "agents-report,noon-news",
                "--dry-run",
                prefix=home,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            core_targets = result["changes"]["core_files"]
            self.assertTrue(any(path.endswith("lib/glance_brief/cli.py") for path in core_targets))
            self.assertTrue(any(path.endswith("lib/glance_brief/prompts/noon-news.md") for path in core_targets))
            self.assertFalse((home / "scripts").exists())


if __name__ == "__main__":
    unittest.main()
