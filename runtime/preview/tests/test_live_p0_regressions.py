import sys
import unittest
from pathlib import Path

RUNTIME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME / "lib"))

from glance_brief import adapters, contracts, render_report, resolve  # noqa: E402


class LiveP0RegressionTests(unittest.TestCase):
    def test_general_source_links_use_the_original_publisher_identity(self):
        direct_url = "https://metr.org/blog/2026-09-02-exploitgym-agent-escapes/"
        rendered = render_report._source_links(
            [
                {
                    "channel_id": "news-aggregator",
                    "channel_label": "NA",
                    "links": [
                        {
                            "role": "article",
                            "label": "Hacker News 热门",
                            "url": direct_url,
                        }
                    ],
                }
            ],
            "test.provenance",
        )

        self.assertEqual(rendered, f"[NA•METR]({direct_url})")

    def test_ai_original_link_uses_publisher_domain_when_label_is_an_intermediary(self):
        url = "https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation"
        provenance = [
            {
                "channel_id": "aihot",
                "channel_label": "AIHOT",
                "links": [
                    {
                        "label": "AIHOT",
                        "role": "item",
                        "url": "https://aihot.virxact.com/items/example",
                    },
                    {
                        "label": "Hacker News 热门（buzzing.cc 中文翻译）",
                        "role": "original",
                        "url": url,
                    },
                ],
            }
        ]

        rendered = render_report._ai_ecosystem_source_links(provenance, "provenance")

        self.assertEqual(rendered, f"[METR]({url})")

    def test_ai_original_link_keeps_hacker_news_for_its_own_discussion_url(self):
        url = "https://news.ycombinator.com/item?id=123"
        provenance = [
            {
                "channel_id": "aihot",
                "channel_label": "AIHOT",
                "links": [{"label": "Hacker News 热门", "role": "original", "url": url}],
            }
        ]

        rendered = render_report._ai_ecosystem_source_links(provenance, "provenance")

        self.assertEqual(rendered, f"[Hacker 热门]({url})")

    def test_url_contract_rejects_markdown_destination_breakout(self):
        malicious = "https://good.example/a)](https://evil.example/x"

        with self.assertRaisesRegex(contracts.ContractError, "Markdown-unsafe delimiter"):
            contracts.url(malicious, "test.url")

    def test_question_headline_is_allowed_when_body_supplies_independent_evidence(self):
        source = {
            "channel_id": "news-aggregator",
            "channel_label": "NA",
            "map": {"title": "title", "text": ["summary", "title"], "links": []},
        }
        raw = {
            "title": "美国地勤未拔油管造成事故？国航回应",
            "summary": "国航回应称飞机在地面保障期间发生设备刮碰，具体原因仍在调查。",
        }

        candidate = adapters.normalize_candidate("news_aggregator", source, raw)

        self.assertEqual(candidate["text"], raw["summary"])

    def test_question_headline_without_body_is_not_rejected_solely_for_question_mark(self):
        source = {
            "channel_id": "news-aggregator",
            "channel_label": "NA",
            "map": {"title": "title", "text": ["summary", "title"], "links": []},
        }
        raw = {
            "title": "国际金价两日大跌160美元，‘乱世买黄金’为何失灵？",
        }

        candidate = adapters.normalize_candidate("news_aggregator", source, raw)

        self.assertEqual(candidate["title"], raw["title"])

    def test_headline_length_counts_visible_names_and_numbers(self):
        headline = "用1024字节打造Python解释器"

        self.assertGreaterEqual(resolve._visible_text_length(headline), 12)
        self.assertLessEqual(resolve._visible_text_length(headline), 28)

    def test_english_cardinal_number_is_valid_translation_evidence(self):
        evidence = {
            "title": "Five dead after cargo plane crash",
            "text": "Five people are dead after a cargo plane overran the runway.",
            "extra": {},
        }

        self.assertEqual(
            resolve._check_summary("货机冲出跑道后造成5人死亡", evidence, "test.fact"),
            "货机冲出跑道后造成5人死亡",
        )
        with self.assertRaisesRegex(contracts.ContractError, "unsupported number"):
            resolve._check_summary("货机冲出跑道后造成6人死亡", evidence, "test.fact")

    def test_unresolved_response_teaser_without_body_is_rejected(self):
        source = {
            "channel_id": "news-aggregator",
            "channel_label": "NA",
            "map": {
                "title": "title",
                "text": ["summary", "title"],
                "links": [],
            },
        }
        raw = {
            "title": "美国地勤“不拔油管扯爆国航油箱”？国航回应",
        }

        with self.assertRaisesRegex(
            contracts.ContractError,
            "question headline needs independent evidence text",
        ):
            adapters.normalize_candidate("news_aggregator", source, raw)


if __name__ == "__main__":
    unittest.main()
