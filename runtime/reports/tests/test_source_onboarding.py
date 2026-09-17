from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

RUNTIME = Path(__file__).resolve().parents[1]
REPO_ROOT = RUNTIME.parents[1]
sys.path.insert(0, str(RUNTIME / "lib"))

from glance_brief import cli, contracts, producer_contract  # noqa: E402


CONFIG_PATH = REPO_ROOT / "config" / "brief.reports.example.json"


class ProducerContractTests(unittest.TestCase):
    def test_valid_schema_one_envelope_is_accepted(self) -> None:
        payload = {
            "schema_version": 1,
            "new_feed": {"items": []},
        }
        self.assertEqual(producer_contract.validate_payload(payload), payload)

    def test_schema_one_requires_object_namespaces_and_no_mixed_stdout(self) -> None:
        with self.assertRaisesRegex(contracts.ContractError, "schema_version"):
            producer_contract.validate_payload({"new_feed": {"items": []}})
        with self.assertRaisesRegex(contracts.ContractError, "object or array"):
            producer_contract.validate_payload(
                {"schema_version": 1, "new_feed": "debug output"}
            )
        with self.assertRaisesRegex(contracts.ContractError, "valid JSON"):
            producer_contract.parse_stdout('{"schema_version": 1}\ncollector debug')

    def test_schema_one_allows_control_metadata_from_agents_producer(self) -> None:
        payload = {
            "schema_version": 1,
            "ok": True,
            "instructions": "use source facts only",
            "generated_at": "2026-09-17T08:00:00+00:00",
            "local_radar": {"signals": {}},
        }
        self.assertEqual(producer_contract.validate_payload(payload), payload)

    def test_schema_one_allows_structured_instructions_from_news_producer(self) -> None:
        payload = {
            "schema_version": 1,
            "instructions": {"source_first": "use captured source facts only"},
            "news_aggregator": {"items": []},
        }
        self.assertEqual(producer_contract.validate_payload(payload), payload)

    def test_schema_one_rejects_an_empty_envelope(self) -> None:
        with self.assertRaisesRegex(contracts.ContractError, "at least one source namespace"):
            producer_contract.validate_payload({"schema_version": 1})


class SourceOnboardingCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    def _config_and_payload(self, directory: Path) -> tuple[Path, Path]:
        config = copy.deepcopy(self.config)
        config["sources"]["new_feed"] = {
            "driver": "snapshot_json",
            "items_path": "new_feed.items",
            "channel_id": "new-feed",
            "channel_label": "NF",
            "map": {
                "title": "headline",
                "text": ["summary", "headline"],
                "links": [
                    {
                        "role": "article",
                        "label": "New Feed",
                        "path": "url",
                    }
                ],
            },
        }
        config["reports"]["noon-news"]["components"][0]["bindings"].append(
            {"source": "new_feed", "take": 1}
        )
        config_path = directory / "config.json"
        config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        payload_path = directory / "snapshot.json"
        payload_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "new_feed": {
                        "items": [
                            {
                                "headline": "New source headline",
                                "summary": "Evidence from a new source.",
                                "url": "https://example.com/new-source",
                            },
                            {
                                "headline": "Second headline",
                                "summary": "Second evidence.",
                                "url": "https://example.com/second",
                            },
                        ]
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return config_path, payload_path

    def test_source_check_reports_mapping_and_binding_health(self) -> None:
        with TemporaryDirectory() as temp:
            config_path, payload_path = self._config_and_payload(Path(temp))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = cli.main(
                    [
                        "source",
                        "check",
                        "--config",
                        str(config_path),
                        "--source",
                        "new_feed",
                        "--payload",
                        str(payload_path),
                        "--report",
                        "noon-news",
                    ]
                )
            self.assertEqual(exit_code, 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result["raw_items"], 2)
            self.assertEqual(result["accepted_items"], 2)
            self.assertEqual(result["excluded"], 0)
            self.assertEqual(result["rejected"], 0)
            self.assertEqual(result["bindings"][0]["component"], "international")
            self.assertEqual(result["bindings"][0]["selected"], 1)
            self.assertEqual(result["candidates"][0]["title"], "New source headline")
            self.assertEqual(
                result["candidates"][0]["links"][0]["url"],
                "https://example.com/new-source",
            )

    def test_source_preview_is_read_only_and_human_scannable(self) -> None:
        with TemporaryDirectory() as temp:
            config_path, payload_path = self._config_and_payload(Path(temp))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = cli.main(
                    [
                        "source",
                        "preview",
                        "--config",
                        str(config_path),
                        "--source",
                        "new_feed",
                        "--payload",
                        str(payload_path),
                        "--limit",
                        "1",
                    ]
                )
            self.assertEqual(exit_code, 0)
            text = output.getvalue()
            self.assertIn("Source preview: new_feed", text)
            self.assertIn("accepted=2", text)
            self.assertIn("New source headline", text)
            self.assertIn("https://example.com/new-source", text)
            self.assertNotIn("model", text.lower())

    def test_source_check_rejects_unknown_source(self) -> None:
        with TemporaryDirectory() as temp:
            config_path, payload_path = self._config_and_payload(Path(temp))
            output = io.StringIO()
            with contextlib.redirect_stderr(output):
                exit_code = cli.main(
                    [
                        "source",
                        "check",
                        "--config",
                        str(config_path),
                        "--source",
                        "missing",
                        "--payload",
                        str(payload_path),
                    ]
                )
            self.assertEqual(exit_code, 1)
            self.assertIn("unknown source", output.getvalue())


    def test_reports_entrypoints_enforce_the_producer_contract(self) -> None:
        for name in ("agents.py", "news.py"):
            text = (RUNTIME / "entrypoints" / name).read_text(encoding="utf-8")
            self.assertIn("producer_contract.validate_payload", text)


class ConfigSchemaTests(unittest.TestCase):
    def test_reports_config_schema_is_shipped_and_mentions_current_driver(self) -> None:
        schema_path = REPO_ROOT / "config" / "brief.reports.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["properties"]["schema_version"]["const"], 3)
        source_properties = schema["$defs"]["source"]["properties"]
        self.assertIn("snapshot_json", source_properties["driver"]["enum"])
        self.assertNotIn("report_json", source_properties["driver"]["enum"])

    def test_producer_schema_requires_schema_one_and_namespace(self) -> None:
        schema = json.loads(
            (REPO_ROOT / "config" / "producer-output.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(schema["properties"]["schema_version"]["const"], 1)
        self.assertEqual(schema["minProperties"], 2)
        self.assertIn("^(?!(schema_version|ok|error|instructions|generated_at)$).+$", schema["patternProperties"])
        self.assertEqual(
            set(schema["not"]["properties"]),
            {"schema_version", "ok", "error", "instructions", "generated_at"},
        )
        self.assertFalse(schema["not"]["additionalProperties"])

    def test_report_handoffs_forbid_renderer_wrapper_text(self) -> None:
        for name, first_char in (("noon-handoff.md", "📰"), ("agents-handoff.md", "📡")):
            text = (RUNTIME / "cron" / name).read_text(encoding="utf-8")
            self.assertIn("第一个字符必须是 renderer stdout 的第一个字符", text)
            self.assertIn("Renderer succeeded", text)
            self.assertIn(first_char, text)


if __name__ == "__main__":
    unittest.main()
