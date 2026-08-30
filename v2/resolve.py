"""Resolve lean model selections against the immutable V2 candidate registry."""
from __future__ import annotations

import copy
import datetime as _datetime
import json
import math
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from . import adapters, contracts

_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9.])[-+]?(?:\d{1,3}(?:[,，]\d{3})+|\d+)(?:\.\d+)?%?")
_SUMMARY_MAX_CHARS = 300


def parse_model_response(raw: str | bytes) -> dict[str, Any]:
    """Parse only a JSON object; prose and fenced JSON are deliberately invalid."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if not isinstance(raw, str) or not raw.strip():
        raise contracts.ContractError("model response must be non-empty JSON")
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise contracts.ContractError(f"malformed model JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise contracts.ContractError("model response root must be an object")
    return value


def _generated_at(value: str | None) -> str:
    if value is not None:
        contracts.timestamp(value, "resolved.generated_at")
        return value
    return _datetime.datetime.now(_datetime.timezone.utc).isoformat(timespec="seconds")


def _registry(assembled: Mapping[str, Any], report: str) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    if assembled.get("schema_version") != contracts.SCHEMA_VERSION or assembled.get("report") != report:
        raise contracts.ContractError("assembled report does not match current resolver")
    registry = assembled.get("candidate_registry")
    sections = assembled.get("sections")
    if not isinstance(registry, Mapping) or not isinstance(sections, Mapping):
        raise contracts.ContractError("assembled report must contain candidate_registry and sections")
    return registry, sections


def _safe_model_text(value: Any, path: str) -> str:
    try:
        return contracts.safe_text(value, path)
    except contracts.ContractError:
        raise


def _numbers(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, str):
        found.update(token.replace(",", "").replace("，", "") for token in _NUMBER_RE.findall(value))
    elif isinstance(value, Mapping):
        for child in value.values():
            found.update(_numbers(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_numbers(child))
    return found


def _check_supported_numbers(summary: str, candidate: Mapping[str, Any], path: str) -> None:
    evidence = _numbers({"title": candidate.get("title"), "text": candidate.get("text"), "extra": candidate.get("extra")})
    unsupported = _numbers(summary) - evidence
    if unsupported:
        raise contracts.ContractError(f"{path} contains unsupported number(s): {sorted(unsupported)!r}")


def _check_summary(value: Any, candidate: Mapping[str, Any], path: str) -> str:
    summary = _safe_model_text(value, path)
    if len(summary) > _SUMMARY_MAX_CHARS:
        raise contracts.ContractError(f"{path} must be at most {_SUMMARY_MAX_CHARS} characters")
    _check_supported_numbers(summary, candidate, path)
    return summary


def _candidate(registry: Mapping[str, Any], sections: Mapping[str, Any], section_id: str, value: Any, path: str, used: set[str]) -> tuple[str, Mapping[str, Any]]:
    if not isinstance(value, Mapping):
        raise contracts.ContractError(f"{path} must be an object")
    contracts.reject_legacy_model_keys(value, path)
    candidate_value = value.get("candidate_id")
    if not isinstance(candidate_value, str):
        raise contracts.ContractError(f"{path}.candidate_id must be a singular string")
    cid = contracts.candidate_id(candidate_value, f"{path}.candidate_id")
    if cid not in registry:
        raise contracts.ContractError(f"{path}.candidate_id is unknown")
    section_ids = sections.get(section_id)
    if not isinstance(section_ids, list) or cid not in section_ids:
        raise contracts.ContractError(f"{path}.candidate_id is outside section {section_id}")
    if cid in used:
        raise contracts.ContractError(f"{path}.candidate_id is reused")
    candidate = registry[cid]
    if not isinstance(candidate, Mapping):
        raise contracts.ContractError(f"candidate registry entry {cid!r} is invalid")
    used.add(cid)
    return cid, candidate


def _candidate_provenance(candidate: Mapping[str, Any], path: str) -> list[dict[str, Any]]:
    provenance = copy.deepcopy(candidate.get("provenance", []))
    # Source adapters may intentionally create evidence-only candidates without
    # links.  A selected report item, however, must be source-backed.
    contracts.validate_provenance(provenance, path)
    return provenance


def _noon_model_sections(model: Mapping[str, Any]) -> Mapping[str, Any]:
    sections = model.get("sections")
    if not isinstance(sections, Mapping) or set(sections) != set(contracts.NOON_SECTION_IDS):
        raise contracts.ContractError("model.sections must contain exactly the three current noon sections")
    return sections


def resolve_noon(
    model: Mapping[str, Any] | str | bytes,
    assembled: Mapping[str, Any],
    report_date: str,
    *,
    generated_at: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Resolve a noon semantic object and return ``(resolved, warnings)``."""
    if isinstance(model, (str, bytes)):
        model = parse_model_response(model)
    if not isinstance(model, Mapping):
        raise contracts.ContractError("model response must be an object")
    contracts.reject_legacy_model_keys(model)
    registry, assembled_sections = _registry(assembled, contracts.NOON_REPORT)
    model_sections = _noon_model_sections(model)
    points = model.get("top_points")
    if not isinstance(points, list):
        raise contracts.ContractError("model.top_points must be an array")
    if len(points) > 5:
        raise contracts.ContractError("model.top_points must contain at most five items")
    used: set[str] = set()
    details: dict[str, list[dict[str, Any]]] = {section: [] for section in contracts.NOON_SECTION_IDS}
    warnings: list[dict[str, Any]] = []
    for section_id in contracts.NOON_SECTION_IDS:
        items = model_sections[section_id]
        if not isinstance(items, list):
            raise contracts.ContractError(f"model.sections.{section_id} must be an array")
        for index, value in enumerate(items):
            path = f"model.sections.{section_id}[{index}]"
            cid, candidate = _candidate(registry, assembled_sections, section_id, value, path, used)
            summary = _check_summary(value.get("summary"), candidate, f"{path}.summary")
            title = candidate.get("title")
            text = candidate.get("text")
            if not isinstance(title, str) or not isinstance(text, str):
                raise contracts.ContractError(f"candidate_registry.{cid} has invalid immutable text")
            headline_zh = value.get("headline_zh")
            resolved_detail: dict[str, Any] = {
                "candidate_id": cid,
                "headline": title,
                "summary": summary,
                "published_at": candidate.get("published_at"),
                "provenance": _candidate_provenance(candidate, f"resolved.sections.{section_id}[{index}].provenance"),
            }
            if headline_zh not in (None, ""):
                headline_zh = _safe_model_text(headline_zh, f"{path}.headline_zh")
                chinese_characters = len(re.findall(r"[\u3400-\u9fff]", headline_zh))
                if not 12 <= chinese_characters <= 28:
                    warnings.append(
                        {
                            "code": "headline_zh_length",
                            "candidate_id": cid,
                            "section": section_id,
                            "chinese_characters": chinese_characters,
                            "expected": "12-28",
                        }
                    )
                resolved_detail["headline_zh"] = headline_zh
            elif re.search(r"[A-Za-z]", title) and not re.search(r"[\u3400-\u9fff]", title):
                warnings.append({"code": "missing_headline_zh", "candidate_id": cid, "section": section_id})
            details[section_id].append(resolved_detail)
    selected = set(used)
    resolved_points: list[dict[str, str]] = []
    point_ids: set[str] = set()
    for index, value in enumerate(points):
        path = f"model.top_points[{index}]"
        if not isinstance(value, Mapping):
            raise contracts.ContractError(f"{path} must be an object")
        contracts.reject_legacy_model_keys(value, path)
        cid_value = value.get("candidate_id")
        if not isinstance(cid_value, str):
            raise contracts.ContractError(f"{path}.candidate_id must be a singular string")
        cid = contracts.candidate_id(cid_value, f"{path}.candidate_id")
        if cid not in selected:
            raise contracts.ContractError(f"{path}.candidate_id must reference a selected detail")
        if cid in point_ids:
            raise contracts.ContractError(f"{path}.candidate_id is reused")
        point_ids.add(cid)
        topic = _safe_model_text(value.get("topic"), f"{path}.topic")
        fact = _safe_model_text(value.get("fact"), f"{path}.fact")
        _check_supported_numbers(fact, registry[cid], f"{path}.fact")
        resolved_points.append({"candidate_id": cid, "topic": topic, "fact": fact})
    contracts.date(report_date, "resolved.report_date")
    resolved: dict[str, Any] = {
        "schema_version": contracts.SCHEMA_VERSION,
        "report": contracts.NOON_REPORT,
        "report_date": report_date,
        "generated_at": _generated_at(generated_at),
        "top_points": resolved_points,
        "sections": details,
    }
    contracts.validate_resolved(resolved)
    return resolved, warnings


def resolve_report(
    report_id: str,
    model: Mapping[str, Any] | str | bytes,
    assembled: Mapping[str, Any],
    report_date: str,
    *,
    generated_at: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if report_id == contracts.NOON_REPORT:
        return resolve_noon(model, assembled, report_date, generated_at=generated_at)
    if report_id == contracts.AGENTS_REPORT:
        return resolve_agents(model, assembled, report_date)
    raise contracts.ContractError(f"unsupported report {report_id!r}")


def _project_candidate(candidate: Mapping[str, Any], fresh: bool, path: str) -> dict[str, Any]:
    extra = candidate.get("extra", {})
    if not isinstance(extra, Mapping):
        raise contracts.ContractError(f"{path} candidate extra must be an object")
    name = extra.get("full_name") or extra.get("repo") or candidate.get("title")
    if not isinstance(name, str) or not name.strip():
        raise contracts.ContractError(f"{path} project name is missing from registry")
    description = extra.get("description", candidate.get("text", ""))
    if not isinstance(description, str):
        raise contracts.ContractError(f"{path}.description must be a string")
    stars = extra.get("stars_today", 0)
    if isinstance(stars, bool) or not isinstance(stars, (int, float)) or not math.isfinite(float(stars)):
        raise contracts.ContractError(f"{path}.stars_today must be a finite non-boolean number")
    if not isinstance(stars, int) or stars < 0:
        raise contracts.ContractError(f"{path}.stars_today must be a non-negative integer")
    links = [
        link
        for channel in candidate.get("provenance", [])
        for link in channel.get("links", [])
        if isinstance(link, Mapping)
    ]
    repository = next((link.get("url") for link in links if link.get("role") in {"repository", "repo", "project"}), None)
    if not isinstance(repository, str):
        repository = next((link.get("url") for link in links if isinstance(link.get("url"), str) and "github.com/" in link["url"]), None)
    if not isinstance(repository, str):
        raise contracts.ContractError(f"{path} project has no registry URL")
    contracts.url(repository, f"{path}.url")
    if (urlsplit(repository).hostname or "").casefold() not in {"github.com", "www.github.com"}:
        raise contracts.ContractError(f"{path} project URL must use the GitHub host")
    return {
        "name": name,
        "url": repository,
        "description": description,
        "stars_today": stars,
        "is_fresh_hot": bool(fresh),
    }


def _metric_safety(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_path = f"{path}.{key}"
            if isinstance(child, bool) and re.search(r"score|count|rate|star|metric|quality|value", str(key), re.I):
                raise contracts.ContractError(f"{key_path} metric must not be boolean")
            _metric_safety(child, key_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _metric_safety(child, f"{path}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise contracts.ContractError(f"{path} metric must be finite")


def _category_rows(value: Any, path: str) -> list[tuple[str, list[Any]]]:
    if isinstance(value, Mapping):
        rows: list[tuple[str, list[Any]]] = []
        for title, projects in value.items():
            if not isinstance(title, str) or not title.strip() or not isinstance(projects, list):
                raise contracts.ContractError(f"{path} mapping must map titles to project arrays")
            rows.append((title, projects))
        return rows
    if not isinstance(value, list):
        raise contracts.ContractError(f"{path} must be an array or title mapping")
    rows = []
    for index, row_value in enumerate(value):
        row_path = f"{path}[{index}]"
        if not isinstance(row_value, Mapping):
            raise contracts.ContractError(f"{row_path} must be an object")
        title = row_value.get("title", row_value.get("name"))
        projects = row_value.get("projects", row_value.get("items"))
        if not isinstance(title, str) or not title.strip() or not isinstance(projects, list):
            raise contracts.ContractError(f"{row_path} needs title and projects")
        rows.append((title, projects))
    return rows


def _ref_id(value: Any, by_id: Mapping[str, Mapping[str, Any]], by_name: Mapping[str, str], path: str) -> str:
    if isinstance(value, str):
        if value in by_id:
            return value
        if value in by_name:
            return by_name[value]
    elif isinstance(value, Mapping):
        for key in ("candidate_id", "full_name", "name", "repo"):
            if key in value:
                return _ref_id(value[key], by_id, by_name, path)
    raise contracts.ContractError(f"{path} references an unknown open-source candidate")


def _trend_summary(value: Any, path: str, project_tokens: set[str]) -> str:
    if not isinstance(value, Mapping):
        raise contracts.ContractError(f"{path} must be an object")
    contracts.reject_legacy_model_keys(value, path)
    summary = value.get("summary")
    summary = contracts.safe_text(summary, f"{path}.summary")
    if re.search(r"https?://|\d|★|stars?", summary, re.I):
        raise contracts.ContractError(f"{path}.summary contains URL, Star marker, or numeric data")
    folded = summary.casefold()
    for token in project_tokens:
        if token and token in folded:
            raise contracts.ContractError(f"{path}.summary contains project or organization name {token!r}")
    return summary


def resolve_agents(
    model: Mapping[str, Any] | str | bytes,
    assembled: Mapping[str, Any],
    report_date: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Resolve AI choices while restoring the producer-owned radar facts."""
    if isinstance(model, (str, bytes)):
        model = parse_model_response(model)
    if not isinstance(model, Mapping):
        raise contracts.ContractError("model response must be an object")
    contracts.reject_legacy_model_keys(model)
    registry, assembled_sections = _registry(assembled, contracts.AGENTS_REPORT)
    ai_ids = assembled_sections.get("ai_ecosystem")
    open_ids = assembled_sections.get("open_source")
    if not isinstance(ai_ids, list) or not isinstance(open_ids, list):
        raise contracts.ContractError("assembled agents sections are invalid")
    metadata = assembled.get("metadata", {})
    if not isinstance(metadata, Mapping):
        raise contracts.ContractError("assembled.metadata must be an object")
    codex_metadata = metadata.get("codexradar", {})
    if isinstance(codex_metadata, str):
        codex_markdown = codex_metadata
    elif isinstance(codex_metadata, Mapping):
        codex_markdown = codex_metadata.get("markdown")
    else:
        codex_markdown = None
    contracts.validate_codex_markdown(codex_markdown)
    open_metadata = metadata.get("open_source", {})
    if not isinstance(open_metadata, Mapping):
        raise contracts.ContractError("metadata.open_source must be an object")
    by_id: dict[str, Mapping[str, Any]] = {}
    by_name: dict[str, str] = {}
    for index, cid in enumerate(open_ids):
        if cid not in registry or not isinstance(registry[cid], Mapping):
            raise contracts.ContractError(f"assembled.sections.open_source[{index}] is not in registry")
        candidate = registry[cid]
        by_id[cid] = candidate
        extra = candidate.get("extra", {})
        name = extra.get("full_name") if isinstance(extra, Mapping) else None
        name = name or candidate.get("title")
        if isinstance(name, str):
            by_name[name] = cid
    hot_refs = open_metadata.get("hot_today", open_ids)
    if not isinstance(hot_refs, list):
        raise contracts.ContractError("metadata.open_source.hot_today must be an array")
    hot_ids = [_ref_id(ref, by_id, by_name, f"metadata.open_source.hot_today[{index}]") for index, ref in enumerate(hot_refs)]
    if len(set(hot_ids)) != len(hot_ids):
        raise contracts.ContractError("metadata.open_source.hot_today reuses a candidate")
    fresh_refs = open_metadata.get("fresh_hot", [])
    if not isinstance(fresh_refs, list):
        raise contracts.ContractError("metadata.open_source.fresh_hot must be an array")
    fresh_ids = [_ref_id(ref, by_id, by_name, f"metadata.open_source.fresh_hot[{index}]") for index, ref in enumerate(fresh_refs)]
    if len(set(fresh_ids)) != len(fresh_ids) or not set(fresh_ids).issubset(set(hot_ids)):
        raise contracts.ContractError("fresh_hot must be a unique subset of hot_today")
    fresh_set = set(fresh_ids)
    project_tokens: set[str] = set()
    project_cache: dict[str, dict[str, Any]] = {}
    for cid, candidate in by_id.items():
        project = _project_candidate(candidate, cid in fresh_set, f"candidate_registry.{cid}")
        project_cache[cid] = project
        name = project["name"].casefold()
        project_tokens.add(name)
        if "/" in name:
            project_tokens.update(part for part in name.split("/") if len(part) >= 3)
    categories_value = open_metadata.get("local_report_categories", [])
    parsed_categories = _category_rows(categories_value, "metadata.open_source.local_report_categories")
    resolved_category_ids: list[list[str]] = []
    flattened_category_ids: list[str] = []
    for index, (_title, refs) in enumerate(parsed_categories):
        if not refs:
            raise contracts.ContractError("category mapping projects must be non-empty")
        category_ids = [
            _ref_id(
                ref,
                by_id,
                by_name,
                f"metadata.open_source.local_report_categories[{index}].projects[{ref_index}]",
            )
            for ref_index, ref in enumerate(refs)
        ]
        resolved_category_ids.append(category_ids)
        flattened_category_ids.extend(category_ids)
    if len(flattened_category_ids) != len(set(flattened_category_ids)):
        raise contracts.ContractError("category mapping must contain unique projects without duplicates")
    if set(flattened_category_ids) != set(hot_ids):
        raise contracts.ContractError("category mapping must completely cover hot_today")
    category_rows: list[dict[str, Any]] = []
    for index, (title, _refs) in enumerate(parsed_categories):
        cid = resolved_category_ids[index][0]
        category_rows.append({"title": title, "project": copy.deepcopy(project_cache[cid])})
    quality = copy.deepcopy(open_metadata.get("quality", {}))
    if not isinstance(quality, Mapping):
        raise contracts.ContractError("metadata.open_source.quality must be an object")
    _metric_safety(quality, "metadata.open_source.quality")
    ai_model = model.get("ai_ecosystem")
    if not isinstance(ai_model, list) or len(ai_model) > 3:
        raise contracts.ContractError("model.ai_ecosystem must contain at most three items")
    seen_ai: set[str] = set()
    ai_resolved: list[dict[str, Any]] = []
    for index, item in enumerate(ai_model):
        path = f"model.ai_ecosystem[{index}]"
        cid, candidate = _candidate(registry, assembled_sections, "ai_ecosystem", item, path, seen_ai)
        summary = _check_summary(item.get("summary"), candidate, f"{path}.summary")
        ai_resolved.append({
            "candidate_id": cid,
            "summary": summary,
            "provenance": _candidate_provenance(candidate, f"resolved.sections.ai_ecosystem[{index}].provenance"),
        })
    trends_model = model.get("open_source_trends")
    if not isinstance(trends_model, list) or len(trends_model) != 2:
        raise contracts.ContractError("model.open_source_trends must contain exactly two items")
    trends = [_trend_summary(value, f"model.open_source_trends[{index}]", project_tokens) for index, value in enumerate(trends_model)]
    resolved = {
        "schema_version": contracts.SCHEMA_VERSION,
        "report": contracts.AGENTS_REPORT,
        "date": contracts.date(report_date, "resolved.date"),
        "sections": {
            "ai_ecosystem": ai_resolved,
            "codexradar": {"markdown": codex_markdown},
            "open_source": {
                "trends": trends,
                "fresh_hot": [copy.deepcopy(project_cache[cid]) for cid in fresh_ids],
                "categories": category_rows,
                "quality": quality,
            },
        },
    }
    contracts.validate_resolved(resolved)
    return resolved, []
