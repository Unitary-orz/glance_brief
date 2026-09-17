"""Offline diagnostics for onboarding one configured source.

The diagnostics path never calls a producer, model, or delivery API.  It reads
one captured schema-1 payload and exercises the same source adapter used by the
report assembler.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import adapters, contracts, producer_contract, profiles, source_adapters
from .source_adapters import generic


def load_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise contracts.ContractError(f"payload {path} must contain valid JSON: {exc.msg}") from exc
    return producer_contract.validate_payload(payload, path=f"payload {path}")


def _raw_items(payload: Any, source: Mapping[str, Any]) -> list[Any]:
    value = (
        generic.get_path(payload, source["items_path"], None)
        if "items_path" in source
        else payload
    )
    if not isinstance(value, list):
        location = source.get("items_path", "payload")
        raise contracts.ContractError(f"source items_path {location!r} must resolve to an array")
    return value


def _matches(candidate: Mapping[str, Any], binding: Mapping[str, Any]) -> bool:
    extra = candidate.get("extra", {})
    if not isinstance(extra, Mapping):
        extra = {}
    return all(
        candidate.get(field, extra.get(field)) in values
        for field, values in binding.get("match", {}).items()
    )


def _binding_records(
    config: Mapping[str, Any],
    source_id: str,
    report_id: str | None,
) -> list[dict[str, Any]]:
    reports = config.get("reports", {})
    if not isinstance(reports, Mapping):
        return []
    records: list[dict[str, Any]] = []
    selected_reports = [report_id] if report_id else list(reports)
    for current_report_id in selected_reports:
        report = reports.get(current_report_id)
        if not isinstance(report, Mapping):
            continue
        if config.get("schema_version") == profiles.CONFIG_SCHEMA_VERSION:
            components = report.get("components", [])
            for component in components:
                if not isinstance(component, Mapping):
                    continue
                for binding in component.get("bindings", []):
                    if isinstance(binding, Mapping) and binding.get("source") == source_id:
                        records.append(
                            {
                                "report": current_report_id,
                                "component": component.get("id"),
                                "title": component.get("title"),
                                "binding": dict(binding),
                            }
                        )
        else:
            sections = report.get("sections", {})
            if isinstance(sections, Mapping):
                for component_id, bindings in sections.items():
                    for binding in bindings if isinstance(bindings, list) else []:
                        if isinstance(binding, Mapping) and binding.get("source") == source_id:
                            records.append(
                                {
                                    "report": current_report_id,
                                    "component": component_id,
                                    "title": component_id,
                                    "binding": dict(binding),
                                }
                            )
    return records


def _candidate_preview(candidate: Mapping[str, Any]) -> dict[str, Any]:
    links = [
        {
            "role": link.get("role"),
            "label": link.get("label"),
            "url": link.get("url"),
        }
        for provenance in candidate.get("provenance", [])
        if isinstance(provenance, Mapping)
        for link in provenance.get("links", [])
        if isinstance(link, Mapping)
    ]
    return {
        "candidate_id": candidate.get("candidate_id"),
        "title": candidate.get("title", ""),
        "text": candidate.get("text", ""),
        "links": links,
    }


def check_source(
    config: Mapping[str, Any],
    source_id: str,
    payload: Mapping[str, Any],
    *,
    report_id: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Run the configured source adapter against one offline payload."""
    if limit < 1:
        raise contracts.ContractError("source preview limit must be positive")
    adapters.validate_config(config)
    sources = config.get("sources", {})
    if source_id not in sources:
        raise contracts.ContractError(f"unknown source {source_id!r}")
    if report_id is not None and report_id not in config.get("reports", {}):
        raise contracts.ContractError(f"unknown report {report_id!r}")
    producer_contract.validate_payload(payload, path="source payload")
    source = sources[source_id]
    raw = _raw_items(payload, source)
    adapted = source_adapters.adapt_source(source_id, source, payload)
    items = adapted.get("items", [])
    diagnostics = adapted.get("diagnostics", {})
    if not isinstance(items, list) or not isinstance(diagnostics, Mapping):
        raise contracts.ContractError("source adapter returned an invalid diagnostic result")

    bindings: list[dict[str, Any]] = []
    for record in _binding_records(config, source_id, report_id):
        binding = record["binding"]
        matching = [candidate for candidate in items if _matches(candidate, binding)]
        take = binding.get("take")
        selected = matching[:take] if isinstance(take, int) else matching
        bindings.append(
            {
                "report": record["report"],
                "component": record["component"],
                "title": record["title"],
                "match": binding.get("match", {}),
                "match_count": len(matching),
                "selected": len(selected),
                "take": take,
            }
        )

    return {
        "ok": True,
        "status": "ok" if items else "empty",
        "source_id": source_id,
        "driver": source.get("driver"),
        "adapter": source.get("adapter", "generic"),
        "payload_schema_version": payload.get("schema_version"),
        "raw_items": len(raw),
        "accepted_items": len(items),
        "excluded": diagnostics.get("excluded", 0),
        "rejected": len(diagnostics.get("rejections", [])),
        "rejections": diagnostics.get("rejections", []),
        "bindings": bindings,
        "candidates": [_candidate_preview(item) for item in items[:limit]],
    }


def render_preview(result: Mapping[str, Any]) -> str:
    """Render a compact human-readable source preview."""
    lines = [
        f"Source preview: {result['source_id']}",
        f"driver={result['driver']} adapter={result['adapter']} status={result['status']}",
        (
            f"raw={result['raw_items']} accepted={result['accepted_items']} "
            f"excluded={result['excluded']} rejected={result['rejected']}"
        ),
    ]
    bindings = result.get("bindings", [])
    if bindings:
        lines.append("bindings:")
        for binding in bindings:
            lines.append(
                f"- {binding['report']}/{binding['component']}: "
                f"matched={binding['match_count']} selected={binding['selected']}"
            )
    else:
        lines.append("bindings: none")
    candidates = result.get("candidates", [])
    if candidates:
        lines.append("candidates:")
        for index, candidate in enumerate(candidates, 1):
            lines.append(f"{index}. {candidate['title'] or '(untitled)'}")
            if candidate.get("text"):
                lines.append(f"   {candidate['text']}")
            for link in candidate.get("links", []):
                lines.append(f"   [{link['label']}]({link['url']})")
    else:
        lines.append("candidates: none")
    return "\n".join(lines) + "\n"
