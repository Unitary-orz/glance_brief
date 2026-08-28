#!/usr/bin/env python3
from __future__ import annotations

import base64
import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

MODULE_PATH = Path(__file__).resolve().parents[1] / "collector.py"
spec = importlib.util.spec_from_file_location("local_open_source_radar", MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load {MODULE_PATH}")
radar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(radar)


TRENDING_HTML = """
<article class="Box-row">
  <h2><a href="/Acme/agent-kit">Acme / agent-kit</a></h2>
  <p class="col-9 color-fg-muted my-1 pr-4">Composable AI agent skills &amp; workflows</p>
  <span itemprop="programmingLanguage">Python</span>
  <a href="/Acme/agent-kit/stargazers"><svg></svg> 1,234</a>
  <a href="/Acme/agent-kit/forks"><svg></svg> 56</a>
  <span>321 stars today</span>
</article>
<article class="Box-row">
  <h2><a href="/Acme/unrelated">Acme / unrelated</a></h2>
  <p class="col-9 color-fg-muted my-1 pr-4">A database migration utility</p>
  <span itemprop="programmingLanguage">Go</span>
  <span>20 stars today</span>
</article>
"""


class ParseTrendingTests(unittest.TestCase):
    def test_parse_trending_extracts_repository_metrics(self):
        repos = radar.parse_trending_html(TRENDING_HTML)
        self.assertEqual(2, len(repos))
        self.assertEqual("Acme/agent-kit", repos[0]["full_name"])
        self.assertEqual("Composable AI agent skills & workflows", repos[0]["description"])
        self.assertEqual("Python", repos[0]["language"])
        self.assertEqual(1234, repos[0]["stars_total"])
        self.assertEqual(321, repos[0]["stars_today"])
        self.assertEqual(56, repos[0]["forks"])
        self.assertEqual(["github-trending"], repos[0]["sources"])


class QueryTests(unittest.TestCase):
    def test_build_search_specs_separates_active_and_new_projects(self):
        config = {
            "topics": ["llm", "ai-agent"],
            "search": {
                "active_days": 7,
                "new_project_days": 30,
                "new_project_min_stars": 20,
                "per_page": 15,
                "exclude_archived": True,
                "exclude_forks": True,
            },
        }
        specs = radar.build_search_specs(config, date(2026, 8, 9))
        self.assertEqual(4, len(specs))
        self.assertEqual("active:llm", specs[0]["source"])
        self.assertIn("topic:llm pushed:>=2026-08-02", specs[0]["query"])
        self.assertIn("archived:false", specs[0]["query"])
        self.assertIn("fork:false", specs[0]["query"])
        self.assertEqual("new:llm", specs[1]["source"])
        self.assertIn("topic:llm created:>=2026-07-10 stars:>=20", specs[1]["query"])


class MergeAndStateTests(unittest.TestCase):
    def test_merge_candidates_combines_sources_and_computes_growth(self):
        trending = [{
            "full_name": "Acme/agent-kit",
            "url": "https://github.com/Acme/agent-kit",
            "description": "Agent framework",
            "language": "Python",
            "stars_total": 150,
            "stars_today": 25,
            "forks": 5,
            "topics": ["ai-agent"],
            "created_at": "2026-08-01T00:00:00Z",
            "pushed_at": "2026-08-09T00:00:00Z",
            "sources": ["github-trending"],
        }]
        searched = [{
            **trending[0],
            "stars_today": 0,
            "sources": ["new:ai-agent"],
        }]
        state = {
            "repositories": {
                "Acme/agent-kit": {
                    "first_seen": "2026-08-08",
                    "last_seen": "2026-08-08",
                    "last_stars": 120,
                    "days_seen": 1,
                }
            }
        }
        merged, next_state = radar.merge_candidates(trending, searched, state, date(2026, 8, 9))
        self.assertEqual(1, len(merged))
        item = merged[0]
        self.assertEqual(["github-trending", "new:ai-agent"], item["sources"])
        self.assertEqual(30, item["stars_delta"])
        self.assertEqual("2026-08-08", item["first_seen"])
        self.assertEqual(2, item["days_seen"])
        self.assertEqual(150, next_state["repositories"]["Acme/agent-kit"]["last_stars"])

    def test_merge_candidates_does_not_increment_days_twice_on_same_date(self):
        item = {
            "full_name": "Acme/agent-kit",
            "url": "https://github.com/Acme/agent-kit",
            "description": "Agent framework",
            "language": "Python",
            "stars_total": 153,
            "stars_today": 25,
            "forks": 5,
            "topics": ["ai-agent"],
            "created_at": "2026-08-01T00:00:00Z",
            "pushed_at": "2026-08-09T00:00:00Z",
            "sources": ["github-trending"],
        }
        state = {"repositories": {"Acme/agent-kit": {
            "first_seen": "2026-08-09", "last_seen": "2026-08-09", "last_stars": 150, "days_seen": 1,
        }}}
        merged, next_state = radar.merge_candidates([item], [], state, date(2026, 8, 9))
        self.assertEqual(1, merged[0]["days_seen"])
        self.assertEqual(0, merged[0]["stars_delta"])
        self.assertEqual(1, next_state["repositories"]["Acme/agent-kit"]["days_seen"])
        self.assertEqual(153, next_state["repositories"]["Acme/agent-kit"]["last_stars"])


    def test_merge_candidates_resets_consecutive_days_after_gap(self):
        item = {
            "full_name": "Acme/agent-kit",
            "url": "https://github.com/Acme/agent-kit",
            "description": "Agent framework",
            "language": "Python",
            "stars_total": 153,
            "stars_today": 0,
            "forks": 5,
            "topics": ["ai-agent"],
            "created_at": "2026-08-01T00:00:00Z",
            "pushed_at": "2026-08-10T00:00:00Z",
            "source": "active:ai-agent",
        }
        state = {"repositories": {"Acme/agent-kit": {
            "first_seen": "2026-08-01",
            "last_seen": "2026-08-05",
            "last_stars": 150,
            "days_seen": 5,
        }}}
        merged, _ = radar.merge_candidates([item], [], state, date(2026, 8, 10))
        self.assertEqual(1, merged[0]["days_seen"])
        self.assertEqual(3, merged[0]["stars_delta"])


class RankingTests(unittest.TestCase):
    def test_rank_candidates_prefers_daily_momentum_and_new_projects(self):
        config = {
            "ranking": {
                "today_star_weight": 1.0,
                "snapshot_delta_weight": 0.8,
                "trending_bonus": 80,
                "new_source_bonus": 120,
                "new_repo_age_days": 30,
                "new_repo_bonus": 100,
                "max_candidates": 20,
            }
        }
        candidates = [
            {"full_name": "Old/large", "stars_total": 100000, "stars_today": 0, "stars_delta": 2,
             "sources": ["active:llm"], "created_at": "2020-01-01T00:00:00Z"},
            {"full_name": "New/fast", "stars_total": 500, "stars_today": 200, "stars_delta": 180,
             "sources": ["github-trending", "new:ai-agent"], "created_at": "2026-08-01T00:00:00Z"},
        ]
        ranked = radar.rank_candidates(candidates, config, date(2026, 8, 9))
        self.assertEqual("New/fast", ranked[0]["full_name"])
        self.assertGreater(ranked[0]["score"], ranked[1]["score"])

    def test_rank_candidates_uses_name_as_stable_final_tiebreaker(self):
        config = {"ranking": {
            "today_star_weight": 1.0, "snapshot_delta_weight": 1.0,
            "trending_bonus": 0, "new_source_bonus": 0,
            "new_repo_age_days": 30, "new_repo_bonus": 0, "max_candidates": 20,
        }}
        candidates = [
            {"full_name": "Zed/repo", "stars_total": 10, "stars_today": 0, "stars_delta": 0, "sources": []},
            {"full_name": "Alpha/repo", "stars_total": 10, "stars_today": 0, "stars_delta": 0, "sources": []},
        ]
        ranked = radar.rank_candidates(candidates, config, date(2026, 8, 9))
        self.assertEqual(["Alpha/repo", "Zed/repo"], [item["full_name"] for item in ranked])


class PathResolutionTests(unittest.TestCase):
    def test_resolve_data_path_keeps_relative_paths_inside_data_root(self):
        data_root = Path("/tmp/local-open-source-radar-data")
        self.assertEqual(
            data_root / "cache",
            radar.resolve_data_path("cache", data_root),
        )
        self.assertEqual(
            Path("/var/cache/local-radar"),
            radar.resolve_data_path("/var/cache/local-radar", data_root),
        )


    def test_categories_are_built_from_hot_today_without_category_limit_truncation(self):
        ranked = [
            {
                "full_name": f"Acme/agent-{index}",
                "url": f"https://github.com/Acme/agent-{index}",
                "description": "agent workflow",
                "topics": [],
                "stars_total": 10,
                "stars_today": 10 - index,
                "stars_delta": 0,
                "sources": ["github-trending"],
            }
            for index in range(3)
        ]
        config = {
            "categories": [{"label": "Agents", "keywords": ["agent"]}],
            "output": {"top_hot": 3, "top_new": 0, "top_fresh_hot": 0, "category_limit": 1},
        }

        output = radar.build_output(ranked, config, date(2026, 8, 12), {})

        self.assertEqual(
            ["Acme/agent-0", "Acme/agent-1", "Acme/agent-2"],
            [item["full_name"] for item in output["categories"]["Agents"]],
        )

    def test_runtime_paths_derive_relative_cache_root_from_explicit_config(self):
        data_root = Path("/tmp/isolated-runtime/data/local-open-source-radar")
        args = SimpleNamespace(
            config=data_root / "config" / "config.json",
            state=data_root / "state" / "state.json",
            output_dir=data_root / "output",
        )

        paths = radar.resolve_runtime_paths(args)

        self.assertEqual(data_root / "cache", radar.resolve_data_path("cache", paths["data_root"]))
        self.assertEqual(data_root / "config" / "config.json", paths["config"])
        self.assertEqual(data_root / "state" / "state.json", paths["state"])
        self.assertEqual(data_root / "output", paths["output_dir"])


class RelevanceTests(unittest.TestCase):
    def test_filter_relevant_uses_topics_and_configured_keywords(self):
        config = {
            "topics": ["llm", "ai-agent"],
            "relevance_keywords": ["ai", "agent", "llm", "machine learning"],
            "relevance_exclude_keywords": ["awesome list"],
        }
        candidates = [
            {"full_name": "Acme/agent-kit", "description": "Agent workflows", "topics": [], "sources": []},
            {"full_name": "Acme/unknown", "description": "Utility", "topics": ["llm"], "sources": []},
            {"full_name": "Acme/awesome-ai", "description": "Awesome list for agent tools", "topics": ["ai-agent"], "sources": []},
            {"full_name": "Acme/db", "description": "Database migrations", "topics": [], "sources": []},
            {"full_name": "Acme/process-tool", "description": "Trace containers and running processes", "topics": [], "sources": []},
        ]
        kept = radar.filter_relevant(candidates, config)
        self.assertEqual(["Acme/agent-kit", "Acme/unknown"], [x["full_name"] for x in kept])

    def test_filter_relevant_normalizes_separators_and_uses_aliases(self):
        config = {
            "topics": [],
            "relevance_keywords": [],
            "relevance_aliases": {
                "coding_agents": ["claude code", "codex", "opencode"],
            },
            "relevance_exclude_keywords": [],
        }
        candidates = [
            {"full_name": "Acme/claude_code", "description": "Use Claude-Code from a terminal", "topics": [], "sources": []},
            {"full_name": "Acme/opencode", "description": "OpenCode workflow", "topics": [], "sources": []},
            {"full_name": "Acme/database", "description": "Database migrations", "topics": [], "sources": []},
        ]
        kept = radar.filter_relevant(candidates, config)
        self.assertEqual(
            ["Acme/claude_code", "Acme/opencode"],
            [item["full_name"] for item in kept],
        )

    def test_filter_relevant_reports_reason_counts(self):
        config = {
            "topics": ["llm"],
            "relevance_keywords": ["agent"],
            "relevance_exclude_keywords": ["awesome list"],
        }
        candidates = [
            {"full_name": "Acme/topic", "description": "Utility", "topics": ["llm"], "sources": []},
            {"full_name": "Acme/keyword", "description": "Agent workflow", "topics": [], "sources": []},
            {"full_name": "Acme/excluded", "description": "Awesome list for agent tools", "topics": [], "sources": []},
            {"full_name": "Acme/unknown", "description": "Database migrations", "topics": [], "sources": []},
        ]
        kept, diagnostics = radar.filter_relevant_with_diagnostics(candidates, config)
        self.assertEqual(["Acme/topic", "Acme/keyword"], [item["full_name"] for item in kept])
        self.assertEqual(
            {
                "kept_topic": 1,
                "kept_keyword": 1,
                "excluded_keyword": 1,
                "rejected_no_signal": 1,
            },
            diagnostics["reason_counts"],
        )


class FreshHotTests(unittest.TestCase):
    def test_load_recent_shown_names_reads_report_sections_but_not_today(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            (output_dir / "local-open-source-radar-2026-08-11.json").write_text(
                json.dumps({"report_date": "2026-08-11", "signals": {
                    "hot_today": [{"full_name": "Seen/old"}],
                    "new_projects": [{"full_name": "Seen/new"}],
                    "fresh_hot": [{"full_name": "Seen/fresh"}],
                    "candidates": [{"full_name": "Internal/not-shown"}],
                }}),
                encoding="utf-8",
            )
            (output_dir / "local-open-source-radar-2026-08-12.json").write_text(
                json.dumps({"report_date": "2026-08-12", "signals": {
                    "hot_today": [{"full_name": "Today/already-written"}]
                }}),
                encoding="utf-8",
            )
            (output_dir / "local-open-source-radar-2026-08-01.json").write_text(
                json.dumps({"report_date": "2026-08-01", "signals": {
                    "hot_today": [{"full_name": "Outside/window"}]
                }}),
                encoding="utf-8",
            )
            (output_dir / "local-open-source-radar-bad.json").write_text("{broken", encoding="utf-8")

            self.assertEqual(
                {"Seen/old", "Seen/new", "Seen/fresh"},
                radar.load_recent_shown_names(output_dir, date(2026, 8, 12), 7),
            )

    def test_select_fresh_hot_keeps_today_order_and_excludes_seen_projects(self):
        hot = [
            {"full_name": "Seen/project"},
            {"full_name": "Fresh/first"},
            {"full_name": "Fresh/second"},
        ]
        result = radar.select_fresh_hot(hot, {"Seen/project"}, 5)
        self.assertEqual(["Fresh/first", "Fresh/second"], [item["full_name"] for item in result])

    def test_build_output_contains_fresh_hot(self):
        ranked = [
            {
                "full_name": f"Seen/project-{index}",
                "url": f"https://github.com/Seen/project-{index}",
                "stars_total": 20 - index,
                "stars_today": 100 - index,
                "stars_delta": 5,
                "sources": ["github-trending"],
            }
            for index in range(5)
        ] + [
            {
                "full_name": "Seen/project-old",
                "url": "https://github.com/Seen/project-old",
                "stars_total": 14,
                "stars_today": 94,
                "stars_delta": 4,
                "sources": ["github-trending"],
            },
            {
                "full_name": "Fresh/project",
                "url": "https://github.com/Fresh/project",
                "stars_total": 10,
                "stars_today": 90,
                "stars_delta": 1,
                "sources": ["github-trending"],
            },
        ]
        config = {"output": {"top_hot": 5, "top_new": 5, "top_fresh_hot": 5}, "categories": []}
        output = radar.build_output(
            ranked,
            config,
            date(2026, 8, 12),
            {},
            prior_seen_names={"Seen/project-old", "Fresh/project"},
        )
        self.assertEqual(
            [f"Seen/project-{index}" for index in range(5)],
            [item["full_name"] for item in output["signals"]["fresh_hot"]],
        )
        self.assertEqual(5, len(output["signals"]["hot_today"]))
        self.assertTrue(
            {
                item["full_name"] for item in output["signals"]["fresh_hot"]
            }.issubset(
                {item["full_name"] for item in output["signals"]["hot_today"]}
            )
        )
        self.assertEqual(
            {"hot_today", "new_projects", "fresh_hot"},
            set(output["signals"]),
        )

    def test_build_output_makes_fresh_hot_a_subset_of_expanded_hot(self):
        ranked = [
            {
                "full_name": name,
                "url": f"https://github.com/{name}",
                "stars_total": 100,
                "stars_today": 100 - index,
                "stars_delta": 5,
                "sources": ["github-trending"],
            }
            for index, name in enumerate([
                "Fresh/in-hot-1",
                "Seen/in-hot",
                "Fresh/in-hot-2",
                "Fresh/outside-hot",
            ])
        ]
        config = {"output": {"top_hot": 3, "top_new": 5, "top_fresh_hot": 5}, "categories": []}
        output = radar.build_output(
            ranked,
            config,
            date(2026, 8, 12),
            {},
            prior_seen_names={"Seen/in-hot"},
        )
        hot_names = {item["full_name"] for item in output["signals"]["hot_today"]}
        fresh_names = [item["full_name"] for item in output["signals"]["fresh_hot"]]
        self.assertEqual(["Fresh/in-hot-1", "Fresh/in-hot-2"], fresh_names)
        self.assertTrue(
            {
                item["full_name"] for item in output["signals"]["fresh_hot"]
            }.issubset(
                {item["full_name"] for item in output["signals"]["hot_today"]}
            )
        )
        self.assertEqual(
            {
                "Fresh/in-hot-1": True,
                "Seen/in-hot": False,
                "Fresh/in-hot-2": True,
            },
            {
                item["full_name"]: item["is_fresh_hot"]
                for item in output["signals"]["hot_today"]
            },
        )
        self.assertNotIn("Fresh/outside-hot", fresh_names)


class OutputValidationTests(unittest.TestCase):
    def test_validate_output_rejects_duplicate_and_mismatched_links(self):
        candidates = [
            {"full_name": "Acme/agent", "url": "https://github.com/Acme/agent", "stars_total": 5, "stars_today": 1},
            {"full_name": "Acme/agent", "url": "https://example.com/wrong", "stars_total": 5, "stars_today": 1},
        ]
        result = radar.validate_candidates(candidates)
        self.assertFalse(result["ok"])
        self.assertIn("duplicate:Acme/agent", result["errors"])
        self.assertIn("invalid_url:Acme/agent", result["errors"])


class TechnicalEvidenceTests(unittest.TestCase):
    def test_build_technical_evidence_extracts_frameworks_routes_and_sources(self):
        config = {
            "technical_analysis": {
                "framework_keywords": {
                    "FastAPI": ["fastapi"],
                    "PyTorch": ["torch", "pytorch"],
                    "Transformers": ["transformers"],
                },
                "route_keywords": {
                    "tool-calling agent": ["tool calling", "agent loop"],
                    "local inference": ["local inference", "on-device"],
                },
                "readme_excerpt_chars": 200,
                "evidence_file_limit": 2,
            }
        }
        item = {
            "full_name": "Acme/agent-kit",
            "url": "https://github.com/Acme/agent-kit",
            "default_branch": "main",
            "language": "Python",
        }
        tree = [
            {"path": "README.md", "type": "blob", "sha": "readme-sha"},
            {"path": "pyproject.toml", "type": "blob", "sha": "manifest-sha"},
            {"path": "src/agent/loop.py", "type": "blob", "sha": "code-sha"},
            {"path": "Dockerfile", "type": "blob", "sha": "docker-sha"},
            "malformed-entry",
        ]
        readme = "FastAPI service with a tool calling agent loop and local inference."
        manifests = {
            "pyproject.toml": 'dependencies = ["torch", "transformers", "fastapi"]',
            "package.json": '{"dependencies": {"fastapi": "latest"}}',
        }

        evidence = radar.build_technical_evidence(
            item, readme, tree, manifests, config, tree_sha="tree-sha"
        )

        self.assertEqual("ok", evidence["status"])
        self.assertEqual("tree-sha", evidence["tree_sha"])
        self.assertEqual(["FastAPI", "PyTorch", "Transformers"], evidence["frameworks"])
        self.assertEqual(["local inference", "tool-calling agent"], evidence["technical_routes"])
        self.assertIn("src/agent/loop.py", evidence["key_paths"])
        self.assertEqual("high", evidence["confidence"])
        self.assertEqual(2, len(evidence["evidence_files"]))
        self.assertEqual(
            "https://github.com/Acme/agent-kit/blob/main/pyproject.toml",
            evidence["evidence_files"][1]["url"],
        )

    def test_enrich_technical_evidence_fetches_blobs_and_reuses_cache(self):
        config = {
            "search": {"timeout_seconds": 19, "attempts": 2},
            "technical_analysis": {
                "enabled": True,
                "timeout_seconds": 4,
                "attempts": 1,
                "max_projects": 5,
                "manifest_filenames": ["pyproject.toml"],
                "max_manifest_files": 2,
                "framework_keywords": {"FastAPI": ["fastapi"]},
                "route_keywords": {"agent": ["agent loop"]},
            },
        }
        item = {
            "full_name": "Acme/agent-kit",
            "url": "https://github.com/Acme/agent-kit",
            "default_branch": "main",
            "pushed_at": "2026-08-10T00:00:00Z",
            "language": "Python",
        }
        tree_payload = {"sha": "tree-sha", "truncated": False, "tree": [
            {"path": "README.md", "type": "blob", "sha": "readme-sha"},
            {"path": "pyproject.toml", "type": "blob", "sha": "manifest-sha"},
        ]}
        blobs = {
            "readme-sha": "FastAPI agent loop",
            "manifest-sha": 'dependencies = ["fastapi"]',
        }
        calls = []

        def requester(url, timeout, token="", attempts=1):
            calls.append((url, timeout, attempts))
            if "/git/trees/" in url:
                return json.dumps(tree_payload)
            sha = url.rsplit("/", 1)[-1]
            return json.dumps({
                "encoding": "base64",
                "content": base64.b64encode(blobs[sha].encode()).decode(),
            })

        with tempfile.TemporaryDirectory() as tmp:
            first = radar.enrich_projects_with_technical_evidence(
                [dict(item)], config, "token", Path(tmp), request_text=requester
            )
            self.assertEqual("ok", first[0]["technical_analysis"]["status"])
            self.assertEqual(["FastAPI"], first[0]["technical_analysis"]["frameworks"])
            self.assertEqual(3, len(calls))
            self.assertTrue(all(timeout == 4 and attempts == 1 for _, timeout, attempts in calls))

            second = radar.enrich_projects_with_technical_evidence(
                [dict(item)], config, "token", Path(tmp),
                request_text=lambda *args, **kwargs: self.fail("cache should avoid network"),
            )
            self.assertEqual(first[0]["technical_analysis"], second[0]["technical_analysis"])

            cache_path = Path(tmp) / "Acme__agent-kit.json"
            poisoned = json.loads(cache_path.read_text())
            poisoned["technical_analysis"]["evidence_files"] = [
                {"path": "README.md", "url": "https://evil.example/one"},
                {"path": "pyproject.toml", "url": "https://evil.example/two"},
                {"path": "package.json", "url": "https://evil.example/three"},
            ]
            cache_path.write_text(json.dumps(poisoned))
            refreshed = radar.enrich_projects_with_technical_evidence(
                [dict(item)], config, "token", Path(tmp), request_text=requester
            )
            self.assertEqual(["FastAPI"], refreshed[0]["technical_analysis"]["frameworks"])
            self.assertLessEqual(
                len(refreshed[0]["technical_analysis"]["evidence_files"]), 2
            )
            self.assertTrue(all(
                evidence["url"].startswith(item["url"] + "/blob/")
                for evidence in refreshed[0]["technical_analysis"]["evidence_files"]
            ))
            self.assertEqual(6, len(calls))

            updated = json.loads(json.dumps(config))
            updated["technical_analysis"]["cache_version"] = 2
            updated["technical_analysis"]["framework_keywords"] = {"Starlette": ["fastapi"]}
            third = radar.enrich_projects_with_technical_evidence(
                [dict(item)], updated, "token", Path(tmp), request_text=requester
            )
            self.assertEqual(["Starlette"], third[0]["technical_analysis"]["frameworks"])
            self.assertEqual(9, len(calls))

    def test_technical_evidence_failure_does_not_drop_project(self):
        config = {
            "search": {"timeout_seconds": 5, "attempts": 1},
            "technical_analysis": {"enabled": True, "max_projects": 5},
        }
        item = {
            "full_name": "Acme/agent-kit",
            "url": "https://github.com/Acme/agent-kit",
            "default_branch": "main",
            "pushed_at": "2026-08-10T00:00:00Z",
            "language": "Python",
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = radar.enrich_projects_with_technical_evidence(
                [item], config, "token", Path(tmp),
                request_text=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
            )
        self.assertEqual("Acme/agent-kit", result[0]["full_name"])
        self.assertEqual("unavailable", result[0]["technical_analysis"]["status"])
        self.assertEqual("low", result[0]["technical_analysis"]["confidence"])


class SourceIntegrityTests(unittest.TestCase):
    def test_api_item_keeps_default_branch_for_technical_evidence(self):
        payload = {
            "full_name": "Acme/agent-kit",
            "html_url": "https://github.com/Acme/agent-kit",
            "description": "Agent framework",
            "language": "Python",
            "stargazers_count": 10,
            "forks_count": 1,
            "topics": ["ai-agent"],
            "created_at": "2026-08-01T00:00:00Z",
            "pushed_at": "2026-08-10T00:00:00Z",
            "default_branch": "develop",
        }
        self.assertEqual("develop", radar._api_item(payload, "new:ai-agent")["default_branch"])

    def test_parse_search_payload_rejects_incomplete_or_malformed_results(self):
        with self.assertRaises(RuntimeError):
            radar.parse_search_payload({"incomplete_results": True, "items": []}, "active:llm")
        with self.assertRaises(RuntimeError):
            radar.parse_search_payload({"incomplete_results": False}, "active:llm")
        with self.assertRaises(RuntimeError):
            radar.parse_search_payload({"incomplete_results": False, "items": {}}, "active:llm")

    def test_validate_source_health_rejects_abnormally_small_collection(self):
        config = {"quality": {"min_trending_count": 2, "min_search_result_count": 3}}
        with self.assertRaises(RuntimeError):
            radar.validate_source_health([{"full_name": "Acme/one"}], [{}, {}, {}], config)
        with self.assertRaises(RuntimeError):
            radar.validate_source_health([{}, {}], [{}, {}], config)


class StateIoTests(unittest.TestCase):
    def test_existing_corrupt_state_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                radar.load_json(path, {"repositories": {}}, strict=True)

    def test_missing_state_can_start_with_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"
            self.assertEqual({"repositories": {}}, radar.load_json(path, {"repositories": {}}, strict=True))

    def test_prune_state_only_drops_entries_older_than_retention(self):
        state = {"repositories": {
            "Acme/current": {"last_seen": "2026-08-09"},
            "Acme/stale": {"last_seen": "2026-04-01"},
            "Acme/unknown": {"last_seen": "invalid"},
        }}
        pruned = radar.prune_state(state, date(2026, 8, 10), retention_days=90)
        self.assertIn("Acme/current", pruned["repositories"])
        self.assertNotIn("Acme/stale", pruned["repositories"])
        self.assertIn("Acme/unknown", pruned["repositories"])

    def test_save_state_writes_atomic_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            radar.save_json_atomic(path, {"repositories": {"Acme/agent-kit": {"last_stars": 1}}})
            self.assertEqual(1, json.loads(path.read_text())["repositories"]["Acme/agent-kit"]["last_stars"])
            self.assertFalse(path.with_suffix(".json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
