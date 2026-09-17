from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "render.py"
spec = importlib.util.spec_from_file_location("local_open_source_radar_render", MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load {MODULE_PATH}")
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)


CATEGORY_DEFINITIONS = [
    {
        "id": "agents",
        "label": "🤖 AI 智能体/工作流",
        "semantic_scope": "agent tooling",
        "semantic_exclusions": [],
    },
    {
        "id": "applications",
        "label": "📦 AI 应用",
        "semantic_scope": "end-user applications",
        "semantic_exclusions": [],
    },
]


class RenderContractTests(unittest.TestCase):
    def snapshot(self):
        return {
            "schema_version": 1,
            "report_date": "2026-09-17",
            "generated_at": "2026-09-17T09:50:48+08:00",
            "diagnostics": {
                "trending_count": 2,
                "search_result_count": 4,
                "merged_count": 4,
                "relevant_count": 3,
                "ranked_count": 3,
                "technical_success_count": 0,
                "technical_requested_count": 0,
            },
            "quality": {"ok": True, "errors": [], "candidate_count": 3},
            "category_definitions": CATEGORY_DEFINITIONS,
            "signals": {
                "hot_today": [
                    {
                        "full_name": "Acme/agent",
                        "url": "https://github.com/Acme/agent",
                        "stars_today": 10,
                        "is_fresh_hot": True,
                    },
                    {
                        "full_name": "Acme/app",
                        "url": "https://github.com/Acme/app",
                        "stars_today": 5,
                        "is_fresh_hot": False,
                    },
                ],
                "fresh_hot": [
                    {
                        "full_name": "Acme/agent",
                        "url": "https://github.com/Acme/agent",
                        "stars_today": 10,
                        "is_fresh_hot": True,
                    }
                ],
                "new_projects": [],
            },
            "instructions": "source-owned facts",
        }

    def test_renderer_owns_category_layout_and_trusted_project_facts(self):
        semantic = {
            "schema_version": 1,
            "trends": ["Agent 工具链持续升温。"],
            "categories": [
                {"category_id": "agents", "projects": ["Acme/agent"]},
                {"category_id": "applications", "projects": ["Acme/app"]},
            ],
            "hot": [
                {"full_name": "Acme/agent", "summary": "面向 Agent 的工作流工具", "short_summary": "Agent 工作流工具"},
                {"full_name": "Acme/app", "summary": "面向用户的 AI 应用", "short_summary": "面向用户的 AI 应用"},
            ],
            "fresh": [
                {
                    "full_name": "Acme/agent",
                    "summary": "面向 Agent 的工作流工具",
                    "category_id": "agents",
                }
            ],
            "new_projects": [],
        }

        output = render.render_report(self.snapshot(), semantic)

        self.assertIn("**① 🤖 AI 智能体/工作流**", output)
        self.assertIn("**② 📦 AI 应用**", output)
        self.assertIn("- 最热：✨ [Acme/agent](https://github.com/Acme/agent)", output)
        self.assertIn("(+10★/日)", output)
        self.assertIn("(+5★/日)", output)
        self.assertNotIn("Acme/agent](https://example.com", output)
        self.assertIn("（AI 智能体/工作流）", output)
        self.assertIn("- [Acme/agent](https://github.com/Acme/agent)「面向 Agent 的工作流工具」", output)
        self.assertNotIn("\n- ✨ [Acme/agent]", output)

    def test_renderer_uses_continuous_category_numbers(self):
        snapshot = self.snapshot()
        snapshot["signals"]["fresh_hot"] = []
        snapshot["category_definitions"] = [
            {"id": "empty", "label": "🧪 Empty", "semantic_scope": "", "semantic_exclusions": []},
            *CATEGORY_DEFINITIONS,
        ]
        semantic = {
            "schema_version": 1,
            "trends": ["趋势"],
            "categories": [
                {"category_id": "agents", "projects": ["Acme/agent"]},
                {"category_id": "applications", "projects": ["Acme/app"]},
            ],
            "hot": [
                {"full_name": "Acme/agent", "summary": "工具", "short_summary": "工具"},
                {"full_name": "Acme/app", "summary": "应用", "short_summary": "应用"},
            ],
            "fresh": [],
            "new_projects": [],
        }
        output = render.render_report(snapshot, semantic)
        self.assertIn("**① 🤖 AI 智能体/工作流**", output)
        self.assertIn("**② 📦 AI 应用**", output)
        self.assertNotIn("**② 🤖 AI 智能体/工作流**", output)

    def test_renderer_rejects_incomplete_category_coverage(self):
        semantic = {
            "schema_version": 1,
            "trends": ["趋势"],
            "categories": [{"category_id": "agents", "projects": ["Acme/agent"]}],
            "hot": [
                {"full_name": "Acme/agent", "summary": "工具", "short_summary": "工具"},
                {"full_name": "Acme/app", "summary": "应用", "short_summary": "应用"},
            ],
            "fresh": [],
            "new_projects": [],
        }

        with self.assertRaises(render.RenderContractError):
            render.render_report(self.snapshot(), semantic)


if __name__ == "__main__":
    unittest.main()
