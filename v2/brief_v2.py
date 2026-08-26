"""Minimal source mapper and fixed-section assembler for glance_brief V2."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

REPORT_SECTIONS = {
    "noon-news": ("international", "domestic", "business", "ai"),
    "agents-report": ("ai_ecosystem", "model_efficiency", "open_source"),
}
CANONICAL_FIELDS = ("title", "text", "url", "publisher", "published_at")
_MISSING = object()


def get_path(value: Any, path: str, default: Any = None) -> Any:
    """Read a dotted object/list path without expression evaluation."""
    current = value
    if not isinstance(path, str) or not path:
        return default
    for part in path.split("."):
        if isinstance(current, Mapping):
            if part not in current:
                return default
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                return default
            current = current[index]
        else:
            return default
    return current


def _paths(value: Any, path: str) -> list[str]:
    if isinstance(path, str) and path:
        return [path]
    if isinstance(path, list) and path and all(isinstance(item, str) and item for item in path):
        return path
    raise ValueError(f"{value} must be a path string or non-empty path array")


def _first(raw: Mapping[str, Any], spec: Any) -> Any:
    for path in _paths("map value", spec):
        value = get_path(raw, path, _MISSING)
        if value is not _MISSING and value is not None and value != "":
            return copy.deepcopy(value)
    return None


def normalize_item(source_id: str, source: Mapping[str, Any], raw: Mapping[str, Any]) -> dict[str, Any]:
    mapping = source["map"]
    item = {field: _first(raw, mapping[field]) if field in mapping else None for field in CANONICAL_FIELDS}
    extra_map = mapping.get("extra", {})
    item["extra"] = {
        name: value
        for name, spec in extra_map.items()
        if (value := _first(raw, spec)) is not None
    }
    for field in CANONICAL_FIELDS:
        value = item[field]
        if value is not None and not isinstance(value, str):
            item[field] = str(value)
    if not item["title"] and not item["text"]:
        raise ValueError("candidate needs title or text")
    provenance = {
        "source_id": source_id,
        "label": source.get("label", source_id),
    }
    if item["publisher"]:
        provenance["publisher"] = item["publisher"]
    if item["url"]:
        provenance["url"] = item["url"]
    item["provenance"] = [provenance]
    return item


def _path_spec(spec: Any, path: str) -> None:
    try:
        _paths(path, spec)
    except ValueError as exc:
        raise ValueError(f"{path} must be a path string or non-empty path array") from exc


def _validate_source(source_id: str, source: Any) -> None:
    if not isinstance(source, Mapping):
        raise ValueError(f"source {source_id!r} must be an object")
    driver = source.get("driver")
    common = {"driver", "items_path", "label", "map", "timeout"}
    driver_fields = {
        "json_file": {"path"},
        "http_json": {"url"},
        "command_json": {"command", "cwd"},
    }
    if driver not in driver_fields:
        raise ValueError(f"source {source_id!r} has unsupported driver {driver!r}")
    allowed = common | driver_fields[driver]
    unknown = set(source) - allowed
    if unknown:
        raise ValueError(f"source {source_id!r} has unknown fields: {sorted(unknown)!r}")
    required = next(iter(driver_fields[driver] - {"cwd"}))
    if required not in source:
        raise ValueError(f"source {source_id!r} requires {required}")
    if driver in {"json_file", "http_json"} and not isinstance(source[required], str):
        raise ValueError(f"source {source_id!r} {required} must be a string")
    if driver == "command_json":
        command = source["command"]
        if not isinstance(command, list) or not command or not all(isinstance(arg, str) and arg for arg in command):
            raise ValueError(f"source {source_id!r} command must be a non-empty argv array")
        if "cwd" in source and not isinstance(source["cwd"], str):
            raise ValueError(f"source {source_id!r} cwd must be a string")
    if "items_path" in source:
        _path_spec(source["items_path"], f"source {source_id!r} items_path")
    if "label" in source and (not isinstance(source["label"], str) or not source["label"]):
        raise ValueError(f"source {source_id!r} label must be a non-empty string")
    if "timeout" in source and (isinstance(source["timeout"], bool) or not isinstance(source["timeout"], (int, float)) or source["timeout"] <= 0):
        raise ValueError(f"source {source_id!r} timeout must be positive")
    mapping = source.get("map")
    if not isinstance(mapping, Mapping):
        raise ValueError(f"source {source_id!r} map must be an object")
    unknown_map = set(mapping) - set(CANONICAL_FIELDS) - {"extra"}
    if unknown_map:
        raise ValueError(f"source {source_id!r} map has unknown fields: {sorted(unknown_map)!r}")
    for field in CANONICAL_FIELDS:
        if field in mapping:
            _path_spec(mapping[field], f"source {source_id!r} map.{field}")
    extra = mapping.get("extra", {})
    if not isinstance(extra, Mapping):
        raise ValueError(f"source {source_id!r} map.extra must be an object")
    for name, spec in extra.items():
        if not isinstance(name, str) or not name:
            raise ValueError(f"source {source_id!r} map.extra keys must be strings")
        _path_spec(spec, f"source {source_id!r} map.extra.{name}")


def _validate_binding(binding: Any, sources: Mapping[str, Any], path: str) -> None:
    if not isinstance(binding, Mapping):
        raise ValueError(f"{path} must be an object")
    unknown = set(binding) - {"source", "match", "take"}
    if unknown:
        raise ValueError(f"{path} has unknown fields: {sorted(unknown)!r}")
    source_id = binding.get("source")
    if source_id not in sources:
        raise ValueError(f"{path} references unknown source {source_id!r}")
    if "take" in binding:
        take = binding["take"]
        if isinstance(take, bool) or not isinstance(take, int) or take <= 0:
            raise ValueError(f"{path}.take must be a positive integer")
    match = binding.get("match", {})
    if not isinstance(match, Mapping):
        raise ValueError(f"{path}.match must be an object")
    for field, values in match.items():
        if not isinstance(field, str) or not field:
            raise ValueError(f"{path}.match keys must be strings")
        if not isinstance(values, list) or not values:
            raise ValueError(f"{path}.match.{field} must be a non-empty array")
        if any(isinstance(value, (dict, list)) for value in values):
            raise ValueError(f"{path}.match.{field} values must be scalars")


def validate_config(config: Any) -> None:
    if not isinstance(config, Mapping):
        raise ValueError("config must be an object")
    if set(config) != {"schema_version", "sources", "reports"}:
        raise ValueError("config must contain only schema_version, sources, and reports")
    if config.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    sources = config.get("sources")
    reports = config.get("reports")
    if not isinstance(sources, Mapping) or not sources:
        raise ValueError("sources must be a non-empty object")
    if not isinstance(reports, Mapping) or not reports:
        raise ValueError("reports must be a non-empty object")
    for source_id, source in sources.items():
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("source IDs must be non-empty strings")
        _validate_source(source_id, source)
    unknown_reports = set(reports) - set(REPORT_SECTIONS)
    if unknown_reports:
        raise ValueError(f"unknown reports: {sorted(unknown_reports)!r}")
    for report_id, report in reports.items():
        if not isinstance(report, Mapping) or set(report) != {"sections"}:
            raise ValueError(f"report {report_id!r} must contain only sections")
        sections = report["sections"]
        expected = set(REPORT_SECTIONS[report_id])
        if not isinstance(sections, Mapping) or set(sections) != expected:
            raise ValueError(f"report {report_id!r} sections must be {sorted(expected)!r}")
        for section_id in REPORT_SECTIONS[report_id]:
            bindings = sections[section_id]
            if not isinstance(bindings, list):
                raise ValueError(f"reports.{report_id}.sections.{section_id} must be an array")
            for index, binding in enumerate(bindings):
                _validate_binding(binding, sources, f"reports.{report_id}.sections.{section_id}[{index}]")


def _resolve(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else base / path


def load_source(source_id: str, source: Mapping[str, Any], config_dir: Path) -> Any:
    driver = source["driver"]
    timeout = float(source.get("timeout", 30))
    if driver == "json_file":
        return json.loads(_resolve(config_dir, source["path"]).read_text(encoding="utf-8"))
    if driver == "http_json":
        request = urllib.request.Request(source["url"], headers={"User-Agent": "glance-brief-v2/1"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    cwd = _resolve(config_dir, source.get("cwd", "."))
    completed = subprocess.run(
        source["command"], cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
        text=True, timeout=timeout, check=False, shell=False,
    )
    if completed.returncode:
        raise ValueError(f"command exited {completed.returncode}: {completed.stderr.strip()}")
    return json.loads(completed.stdout)


def _raw_items(payload: Any, source: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = get_path(payload, source["items_path"], _MISSING) if "items_path" in source else payload
    if not isinstance(value, list):
        raise ValueError("items_path must resolve to an array")
    return [item for item in value if isinstance(item, Mapping)]


def _load_normalized(source_id: str, source: Mapping[str, Any], config_dir: Path) -> list[dict[str, Any]]:
    payload = load_source(source_id, source, config_dir)
    items = []
    for raw in _raw_items(payload, source):
        try:
            items.append(normalize_item(source_id, source, raw))
        except (TypeError, ValueError):
            continue
    return items


def _field(item: Mapping[str, Any], name: str) -> Any:
    return item.get(name, item.get("extra", {}).get(name, _MISSING))


def _matches(item: Mapping[str, Any], match: Mapping[str, list[Any]]) -> bool:
    return all(_field(item, field) in values for field, values in match.items())


def _dedupe(items: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    by_url: dict[str, dict[str, Any]] = {}
    for item in items:
        url = item.get("url")
        if isinstance(url, str) and url:
            if url in by_url:
                known = by_url[url]["provenance"]
                for provenance in item["provenance"]:
                    if provenance not in known:
                        known.append(provenance)
                continue
            by_url[url] = item
        result.append(item)
    return result


def _candidate_id(candidate: Mapping[str, Any]) -> str:
    evidence = {
        field: candidate.get(field)
        for field in (*CANONICAL_FIELDS, "extra", "provenance")
    }
    encoded = json.dumps(
        evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "c" + hashlib.sha256(encoded).hexdigest()[:12]


def assemble_report(config: Mapping[str, Any], report_id: str, config_dir: Path | str) -> dict[str, Any]:
    validate_config(config)
    if report_id not in config["reports"]:
        raise ValueError(f"report {report_id!r} is not configured")
    config_dir = Path(config_dir)
    report = config["reports"][report_id]
    referenced = []
    for section_id in REPORT_SECTIONS[report_id]:
        for binding in report["sections"][section_id]:
            if binding["source"] not in referenced:
                referenced.append(binding["source"])
    loaded: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}
    for source_id in referenced:
        try:
            loaded[source_id] = _load_normalized(source_id, config["sources"][source_id], config_dir)
        except Exception as exc:
            loaded[source_id] = []
            errors[source_id] = str(exc)
    output: dict[str, Any] = {"schema_version": 1, "report": report_id, "sections": {}}
    seen_ids: set[str] = set()
    for section_id in REPORT_SECTIONS[report_id]:
        candidates: list[dict[str, Any]] = []
        for binding in report["sections"][section_id]:
            selected = [copy.deepcopy(item) for item in loaded[binding["source"]] if _matches(item, binding.get("match", {}))]
            if "take" in binding:
                selected = selected[: binding["take"]]
            candidates.extend(selected)
        candidates = _dedupe(candidates)
        unique = []
        for candidate in candidates:
            candidate["candidate_id"] = _candidate_id(candidate)
            if candidate["candidate_id"] in seen_ids:
                continue
            seen_ids.add(candidate["candidate_id"])
            unique.append(candidate)
        output["sections"][section_id] = unique
    if errors:
        output["source_errors"] = errors
    return output


def probe_sources(config: Mapping[str, Any], config_dir: Path | str, source_id: str | None = None) -> tuple[dict[str, Any], int]:
    validate_config(config)
    ids = [source_id] if source_id else list(config["sources"])
    if source_id and source_id not in config["sources"]:
        raise ValueError(f"unknown source {source_id!r}")
    result = {"schema_version": 1, "sources": {}}
    exit_code = 0
    for current in ids:
        try:
            items = _load_normalized(current, config["sources"][current], Path(config_dir))
            result["sources"][current] = {"ok": True, "count": len(items)}
        except Exception as exc:
            result["sources"][current] = {"ok": False, "error": str(exc)}
            exit_code = 1
    return result, exit_code
