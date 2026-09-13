import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "prefetch.py"
spec = importlib.util.spec_from_file_location("local_open_source_radar_prefetch", MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load {MODULE_PATH}")
prefetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prefetch)


class PrefetchContractTests(unittest.TestCase):
    def run_main(self, completed):
        output = io.StringIO()
        with patch.object(prefetch.subprocess, "run", return_value=completed), redirect_stdout(output):
            return_code = prefetch.main()
        return return_code, json.loads(output.getvalue())

    def test_collector_timeout_emits_parseable_structured_failure(self):
        timeout = subprocess.TimeoutExpired(["python3", "collector.py"], 240)
        output = io.StringIO()
        with patch.object(prefetch.subprocess, "run", side_effect=timeout), redirect_stdout(output):
            return_code = prefetch.main()

        payload = json.loads(output.getvalue())
        self.assertEqual(0, return_code)
        self.assertEqual(1, payload["schema_version"])
        self.assertFalse(payload["ok"])
        self.assertIn("timed out", payload["error"])
        self.assertEqual([], payload["signals"]["hot_today"])
        self.assertEqual([], payload["signals"]["new_projects"])
        self.assertEqual([], payload["signals"]["fresh_hot"])

    def test_collector_nonzero_emits_structured_failure_instead_of_raw_stderr(self):
        completed = SimpleNamespace(returncode=2, stdout="", stderr="collector failed")

        return_code, payload = self.run_main(completed)

        self.assertEqual(0, return_code)
        self.assertFalse(payload["ok"])
        self.assertEqual(2, payload["returncode"])
        self.assertEqual("collector failed", payload["stderr"])
        self.assertEqual([], payload["signals"]["hot_today"])

    def test_success_forwards_schema_and_semantic_category_definitions(self):
        report = {
            "schema_version": 1,
            "report_date": "2026-08-28",
            "generated_at": "2026-08-28T10:00:00+08:00",
            "diagnostics": {"ranked_count": 1},
            "quality": {"ok": True, "errors": [], "candidate_count": 1},
            "signals": {
                "hot_today": [{"full_name": "Acme/agent", "url": "https://github.com/Acme/agent"}],
                "fresh_hot": [],
                "new_projects": [],
            },
            "categories": {
                "Agents": [{"full_name": "Acme/agent"}],
            },
            "category_definitions": [
                {
                    "id": "agents",
                    "label": "🤖 AI 智能体/工作流",
                    "semantic_scope": "Agent runtimes",
                    "semantic_exclusions": ["end-user apps"],
                }
            ],
            "instructions": "structured source",
        }
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            completed = SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"output_path": str(report_path)}),
                stderr="",
            )

            return_code, payload = self.run_main(completed)

        self.assertEqual(0, return_code)
        self.assertTrue(payload["ok"])
        self.assertEqual(1, payload["schema_version"])
        self.assertNotIn("categories", payload)
        self.assertEqual(report["category_definitions"], payload["category_definitions"])
        self.assertEqual(report["signals"], payload["signals"])


if __name__ == "__main__":
    unittest.main()
