import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo


MODULE_PATH = Path(__file__).resolve().parents[1] / "read-current.py"


class ReadCurrentTests(unittest.TestCase):
    def test_reads_structured_categories_without_rendered_report_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            environment = os.environ.copy()
            environment.pop("LOCAL_OPEN_SOURCE_RADAR_REPORT_DIR", None)
            environment["LOCAL_OPEN_SOURCE_RADAR_OUTPUT_DIR"] = tmpdir
            with patch.dict(os.environ, environment, clear=True):
                spec = importlib.util.spec_from_file_location("local_open_source_radar_read_current", MODULE_PATH)
                if spec is None or spec.loader is None:
                    raise RuntimeError(f"cannot load {MODULE_PATH}")
                reader = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(reader)
                report = {
                    "schema_version": 1,
                    "report_date": datetime.now(tz=ZoneInfo("Asia/Shanghai")).date().isoformat(),
                    "generated_at": "2026-08-28T10:00:00+08:00",
                    "quality": {"ok": True},
                    "signals": {
                        "hot_today": [{
                            "full_name": "Acme/agent",
                            "url": "https://github.com/Acme/agent",
                        }],
                        "fresh_hot": [],
                        "new_projects": [],
                    },
                    "categories": {
                        "Agents": [{
                            "full_name": "Acme/agent",
                            "url": "https://github.com/Acme/agent",
                        }],
                    },
                }
                output_path = Path(tmpdir) / f"local-open-source-radar-{reader.TODAY}.json"
                output_path.write_text(json.dumps(report), encoding="utf-8")

                output = io.StringIO()
                with redirect_stdout(output):
                    return_code = reader.main()

        payload = json.loads(output.getvalue())
        self.assertEqual(0, return_code)
        self.assertEqual(1, payload["schema_version"])
        self.assertEqual(report["categories"], payload["categories"])
        self.assertEqual(
            [{"name": "Agents", "projects": ["Acme/agent"]}],
            payload["local_report_categories"],
        )


if __name__ == "__main__":
    unittest.main()
