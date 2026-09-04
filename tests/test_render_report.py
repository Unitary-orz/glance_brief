import unittest

from glance_brief import render_report


class SourceIdentityRenderingTests(unittest.TestCase):
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

    def test_intermediary_identity_is_preserved_for_its_own_host(self):
        discussion_url = "https://news.ycombinator.com/item?id=123"
        rendered = render_report._source_links(
            [
                {
                    "channel_id": "news-aggregator",
                    "channel_label": "NA",
                    "links": [
                        {
                            "role": "article",
                            "label": "Hacker News 热门",
                            "url": discussion_url,
                        }
                    ],
                }
            ],
            "test.provenance",
        )

        self.assertEqual(rendered, f"[NA•Hacker News 热门]({discussion_url})")


if __name__ == "__main__":
    unittest.main()
