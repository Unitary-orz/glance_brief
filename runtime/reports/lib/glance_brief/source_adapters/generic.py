"""Configuration-driven source adapter.

Generic sources use the configured item path, exclusions, field mappings, and
snapshot mappings.  Source-specific semantics belong in a sibling adapter;
this module deliberately contains no report or renderer policy.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from .. import contracts


_UNRESOLVED_RESPONSE_TEASER_RE = re.compile(
    r"[?？]\s*[^：:，,；;。.!！？?]{0,12}(?:回应|答复|发声|responds?)\s*[。.!！]?$",
    re.IGNORECASE,
)


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


def _specs(spec: Any, path: str) -> list[str]:
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
    text = " ".join(value.split())
    text = text.replace("：", " ").replace(":", " ")
    return " ".join(text.split())


def _strip_urls(value: str) -> str:
    return " ".join(re.sub(r"https?://[^\s<>()]+", "", value, flags=re.I).split())


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
    if mapping.get("strip_urls_from_text") is True:
        text = _strip_urls(text)
    if not title.strip() and not text.strip():
        raise contracts.ContractError("candidate needs title or text")
    if re.search(r"https?://", title, re.I) or re.search(r"https?://", text, re.I):
        raise contracts.ContractError("candidate title/text must not contain a URL")
    if (
        title.strip()
        and " ".join(title.split()) == " ".join(text.split())
        and _UNRESOLVED_RESPONSE_TEASER_RE.search(title)
    ):
        raise contracts.ContractError("question headline needs independent evidence text")
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
    if mapping.get("strip_urls_from_text") is True and isinstance(extra.get("description"), str):
        extra["description"] = _strip_urls(extra["description"])
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
        "title_only": contracts.is_title_only_evidence(title, text),
        "published_at": published,
        "extra": extra,
        "provenance": provenance,
    }
    candidate["candidate_id"] = candidate_id_for(candidate)
    return candidate


def _items(payload: Any, source: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = get_path(payload, source["items_path"], payload) if "items_path" in source else payload
    if not isinstance(value, list):
        raise contracts.ContractError("source items_path must resolve to an array")
    return [item for item in value if isinstance(item, Mapping)]


def _is_excluded(raw: Mapping[str, Any], source: Mapping[str, Any]) -> bool:
    return any(
        get_path(raw, field, None) in values
        for field, values in source.get("exclude", {}).items()
    )


def _snapshot(payload: Any, source: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, spec in source.get("snapshot", {}).items():
        value = get_path(payload, spec, None)
        if value is not None:
            result[name] = copy.deepcopy(value)
    return result


def adapt_source(source_id: str, source: Mapping[str, Any], payload: Any) -> dict[str, Any]:
    """Adapt one generic source into the shared source result shape."""
    normalized: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    excluded = 0
    for index, raw in enumerate(_items(payload, source)):
        if _is_excluded(raw, source):
            excluded += 1
            continue
        try:
            normalized.append(normalize_candidate(source_id, source, raw))
        except contracts.ContractError as exc:
            rejections.append({"index": index, "error": str(exc)})
    return {
        "items": normalized,
        "snapshot": _snapshot(payload, source),
        "diagnostics": {
            "excluded": excluded,
            "rejections": rejections,
        },
    }


__all__ = ["adapt_source", "candidate_id_for", "get_path", "normalize_candidate"]
