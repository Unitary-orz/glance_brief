from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo


MODULE_PATH = Path(__file__).resolve().parents[1] / "handoff.py"
spec = importlib.util.spec_from_file_location("local_open_source_radar_handoff", MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load {MODULE_PATH}")
handoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handoff)


class HandoffTests(unittest.TestCase):
    def test_prepare_writes_immutable_source_and_run_contract(self):
        payload = {
            "schema_version": 1,
            "ok": True,
            "report_date": datetime.now(handoff.TZ).date().isoformat(),
            "generated_at": "2026-09-17T09:50:48+08:00",
            "diagnostics": {},
            "quality": {"ok": True},
            "signals": {"hot_today": [], "fresh_hot": [], "new_projects": []},
            "category_definitions": [],
            "instructions": "",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(handoff, "DATA_ROOT", Path(tmpdir)), patch.object(
                handoff, "_run_prefetch", return_value=payload
            ):
                prepared = handoff.prepare()
                run_dir = Path(prepared["run_dir"])
                source = json.loads(Path(prepared["source_input"]).read_text(encoding="utf-8"))
                saved = json.loads((run_dir / "prepared.json").read_text(encoding="utf-8"))
                self.assertTrue((run_dir / "source-input.json").is_file())

        self.assertEqual(payload, source)
        self.assertEqual(prepared, saved)
        self.assertIn("--render-run", prepared["render_command"])
        self.assertTrue(prepared["source_input_sha256"])


if __name__ == "__main__":
    unittest.main()
