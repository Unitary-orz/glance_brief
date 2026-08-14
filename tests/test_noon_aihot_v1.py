import importlib.util
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "noon-news" / "scripts" / "noon_news_prefetch.py"


def load_module():
    spec = importlib.util.spec_from_file_location("noon_news_prefetch_aihot_v1_test", SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


noon_prefetch = load_module()


class NoonAIHOTV1Tests(unittest.TestCase):
    def test_fetch_uses_v1_timeline_query_and_page_metadata(self):
        payload = {
            "schemaVersion": 1,
            "items": [
                {
                    "id": "item-1",
                    "title": "AI HOT item",
                    "source": {"name": "公众号：Example"},
                    "links": {
                        "aihot": "https://aihot.example/items/item-1",
                        "original": "https://example.com/item-1",
                    },
                    "category": "ai-products",
                }
            ],
            "page": {"count": 1, "hasMore": False, "nextCursor": None},
        }
        completed = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

        with patch.object(noon_prefetch, "_curl_available", return_value=True):
            with patch.object(noon_prefetch.subprocess, "run", return_value=completed) as mocked:
                result = noon_prefetch.fetch_aihot()

        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)
        self.assertFalse(result["has_more"])
        self.assertIsNone(result["next_cursor"])
        self.assertEqual(result["window"], "24h")
        self.assertEqual(result["by"], "timeline")
        self.assertEqual(result["limit"], 20)
        self.assertEqual(result["items"][0]["source"]["name"], "公众号：Example")

        command = mocked.call_args.args[0]
        query = parse_qs(urlparse(command[-1]).query)
        self.assertTrue(command[-1].startswith("https://aihot.virxact.com/api/v1/items?"))
        self.assertEqual(query["mode"], ["selected"])
        self.assertEqual(query["window"], ["24h"])
        self.assertEqual(query["by"], ["timeline"])
        self.assertEqual(query["limit"], ["20"])
        self.assertNotIn("since", query)
        self.assertNotIn("take", query)

    def test_default_config_does_not_point_to_legacy_public_endpoint(self):
        self.assertEqual(
            noon_prefetch.AIHOT_BASE,
            "https://aihot.virxact.com/api/v1/items",
        )
        prompt = (ROOT / "skills/noon-news/prompts/news-brief-v2.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("source.name", prompt)
        self.assertIn("links.original", prompt)
        self.assertNotIn("AIHOT_PUBLIC_BASE", prompt)


if __name__ == "__main__":
    unittest.main()
