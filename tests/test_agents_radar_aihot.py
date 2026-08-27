import importlib.util
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "agents-report" / "scripts" / "agents_radar_prefetch.py"


def load_module():
    spec = importlib.util.spec_from_file_location("agents_radar_prefetch_aihot_test", SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agents_prefetch = load_module()


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.payload


class AgentsRadarAIHOTTests(unittest.TestCase):
    def test_fetches_global_selected_pool_without_fixed_category_filter(self):
        payload = {
            "schemaVersion": 1,
            "items": [
                {
                    "id": "tip-1",
                    "category": "tip",
                    "selected": True,
                    "links": {"aihot": "https://aihot.example/tip-1"},
                    "source": {"name": "AI HOT"},
                }
            ],
            "page": {"count": 1, "hasMore": False, "nextCursor": None},
        }

        with patch.object(
            agents_prefetch, "urlopen", return_value=FakeResponse(payload)
        ) as mocked_urlopen:
            result = agents_prefetch.fetch_aihot()

        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["items"][0]["category"], "tip")
        request = mocked_urlopen.call_args.args[0]
        query = parse_qs(urlparse(request.full_url).query)
        self.assertEqual(query["mode"], ["selected"])
        self.assertEqual(query["window"], ["24h"])
        self.assertEqual(query["by"], ["timeline"])
        self.assertNotIn("category", query)

    def test_run_local_radar_reads_structured_payload(self):
        payload = {
            "ok": True,
            "report_date": "2026-08-27",
            "diagnostics": {"trending_count": 16},
            "quality": {"ok": True, "errors": [], "candidate_count": 30},
            "signals": {
                "hot_today": [{
                    "full_name": "Acme/agent-kit",
                    "url": "https://github.com/Acme/agent-kit",
                }],
                "fresh_hot": [],
                "new_projects": [],
            },
            "local_report_categories": [{
                "name": "① 🤖 Agent / 技能 / 工作流",
                "projects": ["Acme/agent-kit"],
            }],
        }
        completed = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )
        with patch.object(
            agents_prefetch.subprocess, "run", return_value=completed
        ) as mocked_run:
            result = agents_prefetch.run_local_radar()

        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "local-open-source-radar")
        self.assertEqual(
            result["signals"]["hot_today"][0]["full_name"],
            "Acme/agent-kit",
        )
        self.assertEqual(
            result["local_report_categories"],
            [{
                "name": "① 🤖 Agent / 技能 / 工作流",
                "projects": ["Acme/agent-kit"],
            }],
        )
        command = mocked_run.call_args.args[0]
        self.assertTrue(command[1].endswith("local-open-source-radar/read-current.py"))


if __name__ == "__main__":
    unittest.main()
