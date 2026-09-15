from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPT_PATH = REPO_ROOT / "producers/local-open-source-radar/prompts/report.md"
MAIN_AGENTS_PROMPT_PATH = REPO_ROOT / "runtime/reports/lib/glance_brief/prompts/agents-report.md"
DATA_CONTRACT_PATH = REPO_ROOT / "docs/data-contracts.md"


class SourceContractTests(unittest.TestCase):
    def test_report_prompt_contains_independent_new_entry_and_hot_rules(self):
        self.assertTrue(PROMPT_PATH.is_file(), f"missing source report prompt: {PROMPT_PATH}")
        if not PROMPT_PATH.is_file():
            return
        prompt = PROMPT_PATH.read_text(encoding="utf-8")

        self.assertIn("**✨ 本期新入榜**", prompt)
        self.assertIn("- [owner/repo](原始URL)「一句话中文简介」(+X★/日)", prompt)
        self.assertIn("禁止添加 `最热：`、`热门：`、`新入榜：` 或 `✨ ` 前缀", prompt)
        self.assertIn("最热", prompt)
        self.assertIn("其他", prompt)
        self.assertIn("is_fresh_hot", prompt)
        self.assertIn("✨ [owner/repo](URL)", prompt)
        self.assertIn("category_definitions", prompt)
        self.assertIn("模型输入不会提供任何预计算的项目分类映射", prompt)
        self.assertIn("只有 fresh 项目行末的 `（分类）` 后缀才去掉", prompt)

    def test_report_prompt_is_environment_independent(self):
        self.assertTrue(PROMPT_PATH.is_file(), f"missing source report prompt: {PROMPT_PATH}")
        if not PROMPT_PATH.is_file():
            return
        prompt = PROMPT_PATH.read_text(encoding="utf-8")

        for forbidden in ("Job ID", "schedule", "delivery", "chat ID", "凭据"):
            self.assertNotIn(forbidden, prompt)

    def test_main_agents_prompt_uses_report_plan_contract(self):
        prompt = MAIN_AGENTS_PROMPT_PATH.read_text(encoding="utf-8")

        self.assertIn("component_definitions", prompt)
        self.assertIn("semantic_clusters", prompt)
        self.assertIn("producer_markdown", prompt)
        self.assertNotIn("**✨ 本期新入榜**", prompt)
        self.assertNotIn("local-open-source-radar", prompt)

    def test_data_contract_separates_main_and_independent_reports(self):
        contract = DATA_CONTRACT_PATH.read_text(encoding="utf-8")

        self.assertIn("## local-open-source-radar", contract)
        self.assertIn("## noon-news", contract)
        agents_start = contract.index("## agents-report")
        radar_start = contract.index("## local-open-source-radar")
        noon_start = contract.index("## noon-news")
        agents_contract = contract[agents_start:radar_start]
        radar_contract = contract[radar_start:noon_start]

        self.assertIn("`local_radar`", agents_contract)
        self.assertIn("`signals.hot_today`", agents_contract)
        self.assertIn("完整 ranked pool", radar_contract)
        self.assertIn("full_selection_pool_count", radar_contract)
        self.assertIn("**✨ 本期新入榜**", radar_contract)
        self.assertIn("最热", radar_contract)
        self.assertIn("其他", radar_contract)
        self.assertNotIn("**✨ 本期新入榜**", agents_contract)


if __name__ == "__main__":
    unittest.main()