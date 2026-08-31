from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FormalReleaseLayoutTests(unittest.TestCase):
    def test_formal_package_replaces_experimental_tree_for_both_reports(self):
        self.assertFalse((ROOT / "v2").exists())
        package = ROOT / "glance_brief"
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
            self.assertTrue((package / relative).is_file(), relative)

        config_path = ROOT / "config" / "brief.example.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(set(config["reports"]), {"agents-report", "noon-news"})

    def test_repository_version_package_and_cli_are_v030(self):
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(version, "0.3.0")
        package_init = (ROOT / "glance_brief" / "__init__.py").read_text(encoding="utf-8")
        self.assertIn('__version__ = "0.3.0"', package_init)
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('version = "0.3.0"', pyproject)
        self.assertIn('glance-brief = "glance_brief.cli:main"', pyproject)

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "glance_brief",
                "check",
                "--config",
                str(ROOT / "config" / "brief.example.json"),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "configuration ok")

    def test_skill_prompts_are_stable_named_mirrors_of_core_contracts(self):
        pairs = (
            (
                ROOT / "glance_brief" / "prompts" / "agents-report.md",
                ROOT / "skills" / "agents-report" / "prompts" / "agents-report.md",
            ),
            (
                ROOT / "glance_brief" / "prompts" / "noon-news.md",
                ROOT / "skills" / "noon-news" / "prompts" / "news-brief.md",
            ),
        )
        for core, skill in pairs:
            self.assertTrue(core.is_file(), core)
            self.assertTrue(skill.is_file(), skill)
            self.assertEqual(core.read_bytes(), skill.read_bytes(), skill)

    def test_ci_enforces_formal_release_gates(self):
        workflow = (ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
        for required in (
            "python -m unittest discover",
            "tests/release_gate.py",
            "python -m pip wheel",
            "python -m glance_brief check",
            "glance-brief --help",
            "git diff --check",
        ):
            self.assertIn(required, workflow)

    def test_core_is_runtime_independent(self):
        core_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((ROOT / "glance_brief").glob("*.py"))
        )
        self.assertNotIn("def invoke_hermes", core_text)
        self.assertNotIn("hermes chat", core_text.lower())
        self.assertNotIn('"--provider"', core_text)

    def test_active_tree_has_no_experimental_v2_names_or_references(self):
        excluded_parts = {".git", "__pycache__", "legacy"}
        bad_paths = []
        bad_text = []
        markers = ("v2/", "run_v2", "test_v2", "from v2", "import v2", "-v2.md")
        for path in ROOT.rglob("*"):
            if path == Path(__file__).resolve() or any(part in excluded_parts for part in path.parts):
                continue
            if "v2" in path.name.lower():
                bad_paths.append(str(path.relative_to(ROOT)))
            if path.is_file() and path.suffix in {".py", ".md", ".json", ".toml", ".yml", ".yaml"}:
                text = path.read_text(encoding="utf-8")
                for marker in markers:
                    if marker in text:
                        bad_text.append(f"{path.relative_to(ROOT)}: {marker}")
        self.assertEqual(bad_paths, [])
        self.assertEqual(bad_text, [])

    def test_installer_manifest_installs_shared_core_for_both_components(self):
        manifest = json.loads(
            (ROOT / "install" / "install-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["project_version"], "0.3.0")
        self.assertEqual(manifest["core"]["source"], "glance_brief")
        self.assertEqual(set(manifest["components"]), {"agents-report", "noon-news"})
        self.assertEqual(
            {spec["prompt"] for spec in manifest["components"].values()},
            {
                "skills/agents-report/prompts/agents-report.md",
                "skills/noon-news/prompts/news-brief.md",
            },
        )


if __name__ == "__main__":
    unittest.main()
