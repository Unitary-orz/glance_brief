"""Source loading and provenance-preserving adapters for glance_brief v0.3.0."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from . import contracts

REPORT_SECTIONS = {
    contracts.NOON_REPORT: contracts.NOON_SECTION_IDS,
    contracts.AGENTS_REPORT: contracts.AGENTS_SECTION_IDS,
}
_SOURCE_FIELDS = {
    "driver",
    "path",
    "command",
    "cwd",
    "items_path",
    "channel_id",
    "channel_label",
    "map",
    "timeout",
    "snapshot",
    "required",
    "env_allowlist",
}
_MAP_FIELDS = {"title", "text", "published_at", "extra", "links"}
_SNAPSHOT_FIELDS = {"fresh_hot", "local_report_categories", "quality", "markdown", "new_projects"}


def get_path(value: Any, path: str, default: Any = None) -> Any:
    """Read a dotted object/list path; no expressions or template evaluation."""
    if not isinstance(path, str) or not path:
        return default
    current = value
    for part in path.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return default
    return current


def _specs(spec: Any, path: str) -> list[Any]:
    if isinstance(spec, str) and spec:
        return [spec]
    if isinstance(spec, list) and spec:
        if not all(isinstance(item, str) and item for item in spec):
            raise contracts.ContractError(f"{path} must contain non-empty path strings")
        return list(spec)
    raise contracts.ContractError(f"{path} must be a path string or non-empty path array")


def _pick(raw: Mapping[str, Any], spec: Any, path: str, default: Any = None) -> Any:
    for candidate_path in _specs(spec, path):
        value = get_path(raw, candidate_path, None)
        if value is not None and value != "":
            return copy.deepcopy(value)
    return default


def _label(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise contracts.ContractError(f"{path} must be a non-empty string")
    # A colon is hierarchical punctuation in a platform/account label, not a
    # separator between independent links.  Preserve words and use spaces.
    text = " ".join(value.split())
    text = text.replace("：", " ").replace(":", " ")
    return " ".join(text.split())


def candidate_id_for(candidate: Mapping[str, Any]) -> str:
    """Return an order-independent content digest for a canonical candidate."""
    evidence = {
        key: candidate.get(key)
        for key in ("title", "text", "published_at", "extra", "provenance")
    }
    encoded = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "c" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _link_entries(raw: Mapping[str, Any], source: Mapping[str, Any], mapping: Mapping[str, Any]) -> list[dict[str, str]]:
    links_spec = mapping.get("links", [])
    if not isinstance(links_spec, list):
        raise contracts.ContractError("map.links must be an array")
    links: list[dict[str, str]] = []
    for index, spec in enumerate(links_spec):
        path = f"map.links[{index}]"
        if not isinstance(spec, Mapping):
            raise contracts.ContractError(f"{path} must be an object")
        unknown = set(spec) - {"role", "label", "label_path", "path"}
        if unknown:
            raise contracts.ContractError(f"{path} has unknown fields: {sorted(unknown)!r}")
        role = spec.get("role")
        link_path = spec.get("path")
        if not isinstance(role, str) or not role:
            raise contracts.ContractError(f"{path}.role must be a non-empty string")
        if not isinstance(link_path, str) or not link_path:
            raise contracts.ContractError(f"{path}.path must be a non-empty path")
        url_value = get_path(raw, link_path, None)
        if url_value in (None, ""):
            continue
        if not isinstance(url_value, str):
            raise contracts.ContractError(f"{path}.path must resolve to a URL string")
        contracts.url(url_value, f"candidate.provenance.links[{index}].url")
        if "label" in spec:
            label_value = spec["label"]
        elif "label_path" in spec:
            label_value = get_path(raw, spec["label_path"], None)
        else:
            label_value = source.get("channel_label", source.get("channel_id", "source"))
        links.append({"role": role, "label": _label(label_value, f"{path}.label"), "url": url_value})
    return links


def normalize_candidate(source_id: str, source: Mapping[str, Any], raw: Mapping[str, Any]) -> dict[str, Any]:
    """Map one producer row to the canonical candidate registry shape."""
    if not isinstance(raw, Mapping):
        raise contracts.ContractError("source item must be an object")
    mapping = source.get("map")
    if not isinstance(mapping, Mapping):
        raise contracts.ContractError("source map must be an object")
    title = _pick(raw, mapping.get("title"), "map.title", "") if "title" in mapping else ""
    text = _pick(raw, mapping.get("text"), "map.text", "") if "text" in mapping else ""
    if title is None:
        title = ""
    if text is None:
        text = ""
    if not isinstance(title, str) or not isinstance(text, str):
        raise contracts.ContractError("candidate title and text must be strings")
    if not title.strip() and not text.strip():
        raise contracts.ContractError("candidate needs title or text")
    if re.search(r"https?://", title, re.I) or re.search(r"https?://", text, re.I):
        raise contracts.ContractError("candidate title/text must not contain a URL")
    published = _pick(raw, mapping["published_at"], "map.published_at") if "published_at" in mapping else None
    if published is not None and not isinstance(published, str):
        raise contracts.ContractError("candidate published_at must be a string")
    if published is not None:
        try:
            contracts.timestamp(published, "candidate.published_at")
        except contracts.ContractError:
            published = None
    extra: dict[str, Any] = {}
    extra_spec = mapping.get("extra", {})
    if not isinstance(extra_spec, Mapping):
        raise contracts.ContractError("map.extra must be an object")
    for name, spec in extra_spec.items():
        if not isinstance(name, str) or not name:
            raise contracts.ContractError("map.extra keys must be non-empty strings")
        value = _pick(raw, spec, f"map.extra.{name}")
        if value is not None:
            extra[name] = value
    channel_id = source.get("channel_id", source_id)
    channel_label = source.get("channel_label", source_id)
    if not isinstance(channel_id, str) or not channel_id:
        raise contracts.ContractError("source channel_id must be a non-empty string")
    channel_label = _label(channel_label, "source.channel_label")
    links = _link_entries(raw, source, mapping)
    provenance: list[dict[str, Any]] = []
    if links:
        provenance.append({"channel_id": channel_id, "channel_label": channel_label, "links": links})
    candidate: dict[str, Any] = {
        "title": title,
        "text": text,
        "published_at": published,
        "extra": extra,
        "provenance": provenance,
    }
    candidate["candidate_id"] = candidate_id_for(candidate)
    return candidate


def _validate_source(source_id: str, source: Any) -> None:
    if not isinstance(source, Mapping):
        raise contracts.ContractError(f"sources.{source_id} must be an object")
    unknown = set(source) - _SOURCE_FIELDS
    if unknown:
        raise contracts.ContractError(f"sources.{source_id} has unknown fields: {sorted(unknown)!r}")
    driver = source.get("driver")
    if driver not in {"json_file", "command_json"}:
        raise contracts.ContractError(f"sources.{source_id}.driver must be json_file or command_json")
    if driver == "json_file" and not isinstance(source.get("path"), str):
        raise contracts.ContractError(f"sources.{source_id}.path must be a string")
    if driver == "command_json":
        command = source.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(arg, str) and arg for arg in command):
            raise contracts.ContractError(f"sources.{source_id}.command must be a non-empty argv array")
        if "cwd" in source and not isinstance(source["cwd"], str):
            raise contracts.ContractError(f"sources.{source_id}.cwd must be a string")
        allowlist = source.get("env_allowlist", [])
        if not isinstance(allowlist, list) or any(
            not isinstance(name, str) or not name or "=" in name for name in allowlist
        ):
            raise contracts.ContractError(f"sources.{source_id}.env_allowlist must be an array of environment names")
        if len(set(allowlist)) != len(allowlist):
            raise contracts.ContractError(f"sources.{source_id}.env_allowlist must not contain duplicates")
    if "items_path" in source:
        _specs(source["items_path"], f"sources.{source_id}.items_path")
    for name in ("channel_id", "channel_label"):
        if name in source and (not isinstance(source[name], str) or not source[name]):
            raise contracts.ContractError(f"sources.{source_id}.{name} must be a non-empty string")
    if "timeout" in source:
        timeout = source["timeout"]
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise contracts.ContractError(f"sources.{source_id}.timeout must be positive")
    if "required" in source and not isinstance(source["required"], bool):
        raise contracts.ContractError(f"sources.{source_id}.required must be a boolean")
    mapping = source.get("map")
    if not isinstance(mapping, Mapping):
        raise contracts.ContractError(f"sources.{source_id}.map must be an object")
    unknown_map = set(mapping) - _MAP_FIELDS
    if unknown_map:
        raise contracts.ContractError(f"sources.{source_id}.map has unknown fields: {sorted(unknown_map)!r}")
    for name in ("title", "text", "published_at"):
        if name in mapping:
            _specs(mapping[name], f"sources.{source_id}.map.{name}")
    extra = mapping.get("extra", {})
    if not isinstance(extra, Mapping):
        raise contracts.ContractError(f"sources.{source_id}.map.extra must be an object")
    for name, spec in extra.items():
        if not isinstance(name, str) or not name:
            raise contracts.ContractError(f"sources.{source_id}.map.extra keys must be strings")
        _specs(spec, f"sources.{source_id}.map.extra.{name}")
    links = mapping.get("links", [])
    if not isinstance(links, list):
        raise contracts.ContractError(f"sources.{source_id}.map.links must be an array")
    for index, spec in enumerate(links):
        path = f"sources.{source_id}.map.links[{index}]"
        if not isinstance(spec, Mapping):
            raise contracts.ContractError(f"{path} must be an object")
        if set(spec) - {"role", "label", "label_path", "path"}:
            raise contracts.ContractError(f"{path} has unknown fields")
        if not isinstance(spec.get("role"), str) or not spec["role"]:
            raise contracts.ContractError(f"{path}.role must be a non-empty string")
        if not isinstance(spec.get("path"), str) or not spec["path"]:
            raise contracts.ContractError(f"{path}.path must be a non-empty string")
        if "label" not in spec and "label_path" not in spec:
            raise contracts.ContractError(f"{path} needs label or label_path")
        if "label" in spec and (not isinstance(spec["label"], str) or not spec["label"]):
            raise contracts.ContractError(f"{path}.label must be a non-empty string")
        if "label_path" in spec and (not isinstance(spec["label_path"], str) or not spec["label_path"]):
            raise contracts.ContractError(f"{path}.label_path must be a non-empty string")
    snapshot = source.get("snapshot", {})
    if not isinstance(snapshot, Mapping):
        raise contracts.ContractError(f"sources.{source_id}.snapshot must be an object")
    if set(snapshot) - _SNAPSHOT_FIELDS:
        raise contracts.ContractError(f"sources.{source_id}.snapshot has unknown fields")
    for name, spec in snapshot.items():
        _specs(spec, f"sources.{source_id}.snapshot.{name}")


def _validate_binding(binding: Any, sources: Mapping[str, Any], path: str) -> None:
    if not isinstance(binding, Mapping):
        raise contracts.ContractError(f"{path} must be an object")
    if set(binding) - {"source", "match", "take"}:
        raise contracts.ContractError(f"{path} has unknown fields")
    source_id = binding.get("source")
    if source_id not in sources:
        raise contracts.ContractError(f"{path}.source references unknown source")
    if "take" in binding and (isinstance(binding["take"], bool) or not isinstance(binding["take"], int) or binding["take"] <= 0):
        raise contracts.ContractError(f"{path}.take must be a positive integer")
    match = binding.get("match", {})
    if not isinstance(match, Mapping):
        raise contracts.ContractError(f"{path}.match must be an object")
    for field, values in match.items():
        if not isinstance(field, str) or not field:
            raise contracts.ContractError(f"{path}.match keys must be strings")
        if not isinstance(values, list) or not values or any(isinstance(item, (dict, list)) for item in values):
            raise contracts.ContractError(f"{path}.match.{field} must be a non-empty scalar array")


def validate_config(config: Any) -> None:
    if not isinstance(config, Mapping):
        raise contracts.ContractError("config must be an object")
    if set(config) != {"schema_version", "sources", "reports"}:
        raise contracts.ContractError("config must contain only schema_version, sources, and reports")
    if config.get("schema_version") != 2:
        raise contracts.ContractError("config.schema_version must be 2")
    sources = config.get("sources")
    reports = config.get("reports")
    if not isinstance(sources, Mapping) or not sources:
        raise contracts.ContractError("config.sources must be a non-empty object")
    if not isinstance(reports, Mapping) or not reports:
        raise contracts.ContractError("config.reports must be a non-empty object")
    for source_id, source in sources.items():
        if not isinstance(source_id, str) or not source_id:
            raise contracts.ContractError("source IDs must be non-empty strings")
        _validate_source(source_id, source)
    if set(reports) - set(REPORT_SECTIONS):
        raise contracts.ContractError("config.reports contains an unsupported report")
    for report_id, report in reports.items():
        if not isinstance(report, Mapping):
            raise contracts.ContractError(f"reports.{report_id} must be an object")
        if set(report) - {"sections", "metadata", "minimum_candidates", "selection_limits"}:
            raise contracts.ContractError(f"reports.{report_id} has unknown fields")
        sections = report.get("sections")
        if not isinstance(sections, Mapping) or set(sections) != set(REPORT_SECTIONS[report_id]):
            raise contracts.ContractError(f"reports.{report_id}.sections must use current section IDs")
        for section_id in REPORT_SECTIONS[report_id]:
            bindings = sections[section_id]
            if not isinstance(bindings, list):
                raise contracts.ContractError(f"reports.{report_id}.sections.{section_id} must be an array")
            for index, binding in enumerate(bindings):
                _validate_binding(binding, sources, f"reports.{report_id}.sections.{section_id}[{index}]")
        minimums = report.get("minimum_candidates", {})
        if not isinstance(minimums, Mapping) or set(minimums) - set(REPORT_SECTIONS[report_id]):
            raise contracts.ContractError(f"reports.{report_id}.minimum_candidates must use current section IDs")
        for section_id, minimum in minimums.items():
            if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 0:
                raise contracts.ContractError(
                    f"reports.{report_id}.minimum_candidates.{section_id} must be a non-negative integer"
                )
        selection_limits = report.get("selection_limits", {})
        if selection_limits and report_id != contracts.NOON_REPORT:
            raise contracts.ContractError("selection_limits is only supported for noon-news")
        if not isinstance(selection_limits, Mapping) or set(selection_limits) - set(REPORT_SECTIONS[report_id]):
            raise contracts.ContractError(f"reports.{report_id}.selection_limits must use current section IDs")
        for section_id, limit in selection_limits.items():
            if not isinstance(limit, Mapping) or set(limit) != {"min", "max"}:
                raise contracts.ContractError(
                    f"reports.{report_id}.selection_limits.{section_id} must contain min and max"
                )
            minimum = limit["min"]
            maximum = limit["max"]
            if (
                isinstance(minimum, bool)
                or not isinstance(minimum, int)
                or isinstance(maximum, bool)
                or not isinstance(maximum, int)
                or minimum < 0
                or maximum < minimum
            ):
                raise contracts.ContractError(
                    f"reports.{report_id}.selection_limits.{section_id} must satisfy 0 <= min <= max"
                )
        metadata = report.get("metadata", {})
        if not isinstance(metadata, Mapping) or set(metadata) - {"codexradar", "open_source"}:
            raise contracts.ContractError(f"reports.{report_id}.metadata has unknown fields")
        for name, reference in metadata.items():
            if not isinstance(reference, Mapping) or set(reference) != {"source"} or reference["source"] not in sources:
                raise contracts.ContractError(f"reports.{report_id}.metadata.{name} must reference a source")


def _resolve_path(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else base / path


def load_source(source_id: str, source: Mapping[str, Any], config_dir: Path) -> Any:
    driver = source["driver"]
    timeout = float(source.get("timeout", 30))
    if driver == "json_file":
        return json.loads(_resolve_path(config_dir, source["path"]).read_text(encoding="utf-8"))
    cwd = _resolve_path(config_dir, source.get("cwd", "."))
    environment_names = {"PATH", "HOME", "LANG", "LC_ALL", "TZ"}
    environment_names.update(source.get("env_allowlist", []))
    environment = {name: os.environ[name] for name in environment_names if name in os.environ}
    completed = subprocess.run(
        source["command"], cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
        text=True, timeout=timeout, check=False, shell=False, env=environment,
    )
    if completed.returncode:
        raise RuntimeError(f"source {source_id} exited with {completed.returncode}: {completed.stderr.strip()}")
    return json.loads(completed.stdout)


def _items(payload: Any, source: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = get_path(payload, source["items_path"], payload) if "items_path" in source else payload
    if not isinstance(value, list):
        raise contracts.ContractError("source items_path must resolve to an array")
    return [item for item in value if isinstance(item, Mapping)]


def _snapshot(payload: Any, source: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, spec in source.get("snapshot", {}).items():
        value = get_path(payload, spec, None)
        if value is not None:
            result[name] = copy.deepcopy(value)
    return result


def _candidate_urls(candidate: Mapping[str, Any]) -> set[str]:
    return {
        link.get("url")
        for channel in candidate.get("provenance", [])
        for link in channel.get("links", [])
        if isinstance(link, Mapping) and isinstance(link.get("url"), str)
    }


def _merge_candidates(first: dict[str, Any], second: Mapping[str, Any]) -> None:
    channels = first.setdefault("provenance", [])
    known = {(channel.get("channel_id"), link.get("url")) for channel in channels for link in channel.get("links", [])}
    for channel in second.get("provenance", []):
        target = next((item for item in channels if item.get("channel_id") == channel.get("channel_id")), None)
        if target is None:
            channels.append(copy.deepcopy(channel))
            continue
        for link in channel.get("links", []):
            key = (channel.get("channel_id"), link.get("url"))
            if key not in known:
                target.setdefault("links", []).append(copy.deepcopy(link))
                known.add(key)


def assemble_report(config: Mapping[str, Any], report_id: str, config_dir: Path | str) -> dict[str, Any]:
    """Load each configured source once and return a bounded candidate registry."""
    validate_config(config)
    if report_id not in config["reports"]:
        raise contracts.ContractError(f"report {report_id!r} is not configured")
    config_dir = Path(config_dir)
    report = config["reports"][report_id]
    referenced: list[str] = []
    for bindings in report["sections"].values():
        for binding in bindings:
            if binding["source"] not in referenced:
                referenced.append(binding["source"])
    for reference in report.get("metadata", {}).values():
        if reference["source"] not in referenced:
            referenced.append(reference["source"])
    loaded: dict[str, list[dict[str, Any]]] = {}
    snapshots: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    rejections: dict[str, list[dict[str, Any]]] = {}
    for source_id in referenced:
        source = config["sources"][source_id]
        try:
            payload = load_source(source_id, source, config_dir)
            snapshots[source_id] = _snapshot(payload, source)
            normalized: list[dict[str, Any]] = []
            source_rejections: list[dict[str, Any]] = []
            for index, raw in enumerate(_items(payload, source)):
                try:
                    normalized.append(normalize_candidate(source_id, source, raw))
                except contracts.ContractError as exc:
                    source_rejections.append({"index": index, "error": str(exc)})
            loaded[source_id] = normalized
            if source_rejections:
                rejections[source_id] = source_rejections
        except Exception as exc:
            loaded[source_id] = []
            snapshots[source_id] = {}
            errors[source_id] = str(exc)
    registry: OrderedDict[str, dict[str, Any]] = OrderedDict()
    sections: dict[str, list[str]] = {}
    for section_id in REPORT_SECTIONS[report_id]:
        section_ids: list[str] = []
        by_url: dict[str, str] = {}
        for binding in report["sections"][section_id]:
            source_candidates = loaded.get(binding["source"], [])
            selected: list[dict[str, Any]] = []
            for candidate in source_candidates:
                if all(candidate.get(field, candidate.get("extra", {}).get(field)) in values for field, values in binding.get("match", {}).items()):
                    selected.append(copy.deepcopy(candidate))
            if "take" in binding:
                selected = selected[: binding["take"]]
            for candidate in selected:
                existing_id = next((by_url[url] for url in _candidate_urls(candidate) if url in by_url), None)
                if existing_id is not None:
                    _merge_candidates(registry[existing_id], candidate)
                    if existing_id not in section_ids:
                        section_ids.append(existing_id)
                    continue
                candidate_id = candidate["candidate_id"]
                # A duplicate content digest can arise from two bindings.  Keep
                # one immutable registry object and merge only provenance.
                if candidate_id in registry:
                    _merge_candidates(registry[candidate_id], candidate)
                else:
                    registry[candidate_id] = candidate
                for url_value in _candidate_urls(candidate):
                    by_url[url_value] = candidate_id
                if candidate_id not in section_ids:
                    section_ids.append(candidate_id)
        sections[section_id] = section_ids
    metadata: dict[str, Any] = {}
    for name, reference in report.get("metadata", {}).items():
        metadata[name] = snapshots.get(reference["source"], {})
    result: dict[str, Any] = {
        "schema_version": contracts.SCHEMA_VERSION,
        "report": report_id,
        "candidate_registry": dict(registry),
        "sections": sections,
        "metadata": metadata,
    }
    if report.get("selection_limits"):
        result["selection_limits"] = copy.deepcopy(report["selection_limits"])
    if errors:
        result["source_errors"] = errors
    if rejections:
        result["candidate_rejections"] = rejections
    return result


def validate_assembly_health(config: Mapping[str, Any], report_id: str, assembled: Mapping[str, Any]) -> None:
    """Fail before model invocation when a required producer did not load."""
    validate_config(config)
    if assembled.get("report") != report_id:
        raise contracts.ContractError("assembled report does not match health policy")
    errors = assembled.get("source_errors", {})
    if not isinstance(errors, Mapping):
        raise contracts.ContractError("assembled.source_errors must be an object")
    for source_id, error in errors.items():
        source = config["sources"].get(source_id)
        if isinstance(source, Mapping) and source.get("required") is True:
            raise contracts.ContractError(f"required source {source_id} failed: {error}")
    sections = assembled.get("sections")
    if not isinstance(sections, Mapping):
        raise contracts.ContractError("assembled.sections must be an object")
    for section_id, minimum in config["reports"][report_id].get("minimum_candidates", {}).items():
        candidates = sections.get(section_id)
        if not isinstance(candidates, list):
            raise contracts.ContractError(f"assembled section {section_id} must be an array")
        if len(candidates) < minimum:
            raise contracts.ContractError(
                f"section {section_id} needs at least {minimum} candidates; got {len(candidates)}"
            )
    for section_id, limit in config["reports"][report_id].get("selection_limits", {}).items():
        candidates = sections.get(section_id)
        minimum = limit["min"]
        if not isinstance(candidates, list) or len(candidates) < minimum:
            count = len(candidates) if isinstance(candidates, list) else 0
            raise contracts.ContractError(
                f"section {section_id} cannot satisfy selection minimum {minimum}; got {count} candidates"
            )


def source_urls(assembled: Mapping[str, Any]) -> set[str]:
    registry = assembled.get("candidate_registry", {})
    if not isinstance(registry, Mapping):
        return set()
    return {
        url_value
        for candidate in registry.values()
        if isinstance(candidate, Mapping)
        for url_value in _candidate_urls(candidate)
    }
