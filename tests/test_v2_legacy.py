import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "v2" / "convert_agents_radar.py"
V1_INPUT = ROOT / "v2" / "fixtures" / "legacy" / "v1-agents-report-input.json"
DERIVED_INPUT = ROOT / "v2" / "fixtures" / "legacy" / "derived-agents-radar.json"


class LegacyAgentsRadarConverterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("convert_agents_radar", MODULE_PATH)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load converter from {MODULE_PATH}")
        cls.converter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.converter)
        cls.v1_payload = json.loads(V1_INPUT.read_text(encoding="utf-8"))
        cls.derived_payload = json.loads(DERIVED_INPUT.read_text(encoding="utf-8"))

    def test_v1_fixture_has_fixed_shape_and_expected_counts(self):
        result = self.converter.convert_payload(self.v1_payload)

        self.assertEqual(set(result), {"items"})
        trends = [item for item in result["items"] if item["kind"] == "trend"]
        projects = [item for item in result["items"] if item["kind"] == "project"]
        self.assertEqual(len(trends), 2)
        self.assertTrue(trends[0]["text"].startswith("今日最明确的信号是：Agent 正从单点能力走向组织化。"))
        self.assertTrue(trends[1]["text"].startswith("第二，Graph-native RAG 是今日登榜的新兴技术栈。"))
        self.assertEqual(len(projects), 39)
        self.assertEqual(sum(project["role"] == "hot" for project in projects), 13)
        self.assertEqual(sum(project["role"] == "other" for project in projects), 26)
        by_name = {project["name"]: project for project in projects}
        self.assertEqual(by_name["huggingface/transformers"]["stars_today"], 80)
        self.assertEqual(by_name["PrimeIntellect-ai/prime-agent"]["stars_today"], 1138)
        self.assertNotIn("stars_today", by_name["tensorflow/tensorflow"])

        self.assertEqual(
            [project["category"] for project in projects[:8]],
            ["🔧 AI 基础工具"] * 8,
        )
        self.assertEqual(
            [project["category"] for project in projects[-8:]],
            ["🔍 RAG/知识库"] * 8,
        )
        for project in projects:
            expected = {"kind", "name", "url", "description", "category", "role"}
            if project["role"] == "hot":
                expected.add("stars_today")
            self.assertEqual(set(project), expected)
            self.assertNotIn("language", project)
            self.assertNotIn("stars", project)

    def test_derived_evidence_input_matches_v1_stdout_input(self):
        self.assertEqual(
            self.converter.convert_payload(self.derived_payload),
            self.converter.convert_payload(self.v1_payload),
        )

    def test_malformed_project_four_line_record_fails_loudly(self):
        markdown = self.v1_payload["agents_radar"]["stdout"]
        malformed = markdown.replace(
            " | 模型定义、训练与推理的统一框架；今日仍进入 Trending，生态基石地位稳固。",
            " | ",
            1,
        )
        with self.assertRaisesRegex(self.converter.ParseError, "description"):
            self.converter.parse_markdown(malformed)

    def test_unknown_or_missing_category_fails_loudly(self):
        markdown = self.v1_payload["agents_radar"]["stdout"]
        malformed = markdown.replace("🔍 RAG/知识库", "🧪 未知分类", 1)
        with self.assertRaisesRegex(self.converter.ParseError, "category"):
            self.converter.parse_markdown(malformed)

    def test_cli_reads_input_and_writes_only_contract_json(self):
        with TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "legacy-agents-radar.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--input",
                    str(V1_INPUT),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, "")
            self.assertEqual(completed.stderr, "")
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8")),
                self.converter.convert_payload(self.v1_payload),
            )

    def test_invalid_input_shape_is_not_guessed(self):
        with self.assertRaisesRegex(self.converter.ParseError, "agents_radar.stdout|items\[0\].evidence"):
            self.converter.convert_payload({"items": []})


if __name__ == "__main__":
    unittest.main()
