"""Resolve lean model selections against the immutable candidate registry."""
from __future__ import annotations

import copy
import datetime as _datetime
import json
import math
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from . import adapters, contracts, profiles

_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9.])[-+]?(?:\d{1,3}(?:[,，]\d{3})+|\d+)(?:\.\d+)?%?")
_ENGLISH_MONTHS = {
    "january": "1",
    "february": "2",
    "march": "3",
    "april": "4",
    "may": "5",
    "june": "6",
    "july": "7",
    "august": "8",
    "september": "9",
    "october": "10",
    "november": "11",
    "december": "12",
}
_ENGLISH_MONTH_RE = re.compile(
    r"\b(" + "|".join(sorted(_ENGLISH_MONTHS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_ENGLISH_CARDINALS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
}
_ENGLISH_CARDINAL_RE = re.compile(
    r"\b(" + "|".join(sorted(_ENGLISH_CARDINALS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_CJK_DATE_NUMBER_RE = re.compile(r"([零〇一二三四五六七八九十百千万两]+)(?=[年月日号])")
_CJK_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_CJK_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}
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


def _visible_text_length(value: str) -> int:
    return len(re.sub(r"\s+", "", value))


def _numbers(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, str):
        found.update(token.replace(",", "").replace("，", "") for token in _NUMBER_RE.findall(value))
        found.update(
            _ENGLISH_CARDINALS[match.group(1).casefold()]
            for match in _ENGLISH_CARDINAL_RE.finditer(value)
        )
        found.update(_date_number_tokens(value))
    elif isinstance(value, Mapping):
        for child in value.values():
            found.update(_numbers(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_numbers(child))
    return found


def _cjk_integer(value: str) -> int | None:
    if not value or any(char not in _CJK_DIGITS and char not in _CJK_UNITS for char in value):
        return None
    if not any(char in _CJK_UNITS for char in value):
        digits = "".join(str(_CJK_DIGITS[char]) for char in value)
        return int(digits) if digits else None
    total = 0
    section = 0
    number = 0
    for char in value:
        if char in _CJK_DIGITS:
            number = _CJK_DIGITS[char]
        else:
            unit = _CJK_UNITS[char]
            if unit == 10000:
                total += (section + (number or 0)) * unit
                section = 0
            else:
                section += (number or 1) * unit
            number = 0
    return total + section + number


def _date_number_tokens(value: str) -> set[str]:
    found = {str(_ENGLISH_MONTHS[match.group(1).casefold()]) for match in _ENGLISH_MONTH_RE.finditer(value)}
    for match in _CJK_DATE_NUMBER_RE.finditer(value):
        number = _cjk_integer(match.group(1))
        if number is not None:
            found.add(str(number))
    return found


def _check_supported_numbers(summary: str, evidence: Any, path: str) -> None:
    if isinstance(evidence, Mapping):
        source = {"title": evidence.get("title"), "text": evidence.get("text"), "extra": evidence.get("extra")}
    elif isinstance(evidence, list):
        source = [
            {"title": candidate.get("title"), "text": candidate.get("text"), "extra": candidate.get("extra")}
            for candidate in evidence
            if isinstance(candidate, Mapping)
        ]
    else:
        source = evidence
    found = _numbers(source)
    unsupported = _numbers(summary) - found
    if unsupported:
        raise contracts.ContractError(f"{path} contains unsupported number(s): {sorted(unsupported)!r}")


def _check_summary(value: Any, evidence: Any, path: str, *, max_chars: int = _SUMMARY_MAX_CHARS) -> str:
    summary = _safe_model_text(value, path)
    if len(summary) > max_chars:
        raise contracts.ContractError(f"{path} must be at most {max_chars} characters")
    _check_supported_numbers(summary, evidence, path)
    return summary


def _check_ai_summary(value: Any, candidates: list[Mapping[str, Any]], path: str) -> str:
    summary = _check_summary(value, candidates, path, max_chars=140)
    if re.search(r"\bRSS\b|RSS\s*(?:源|feed)|网页\s*(?:采集|抓取)|(?:web|atom)\s*feed", summary, re.I):
        raise contracts.ContractError(f"{path} contains source-collection implementation detail")
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


def _candidate_group(
    registry: Mapping[str, Any],
    sections: Mapping[str, Any],
    section_id: str,
    value: Any,
    path: str,
    used: set[str],
    *,
    max_count: int = 3,
) -> tuple[list[str], list[Mapping[str, Any]]]:
    if not isinstance(value, Mapping):
        raise contracts.ContractError(f"{path} must be an object")
    contracts.reject_legacy_model_keys(value, path)
    ids = contracts.candidate_ids(
        value.get("candidate_ids"),
        f"{path}.candidate_ids",
        max_count=max_count,
    )
    section_ids = sections.get(section_id)
    if not isinstance(section_ids, list):
        raise contracts.ContractError(f"assembled section {section_id} must be an array")
    candidates: list[Mapping[str, Any]] = []
    for index, cid in enumerate(ids):
        if cid not in registry:
            raise contracts.ContractError(f"{path}.candidate_ids[{index}] is unknown")
        if cid not in section_ids:
            raise contracts.ContractError(f"{path}.candidate_ids[{index}] is outside section {section_id}")
        if cid in used:
            raise contracts.ContractError(f"{path}.candidate_ids reuses {cid!r}")
        candidate = registry[cid]
        if not isinstance(candidate, Mapping):
            raise contracts.ContractError(f"candidate registry entry {cid!r} is invalid")
        candidates.append(candidate)
    used.update(ids)
    return ids, candidates


def _candidate_provenance(candidate: Mapping[str, Any], path: str) -> list[dict[str, Any]]:
    provenance = copy.deepcopy(candidate.get("provenance", []))
    # Source adapters may intentionally create evidence-only candidates without
    # links.  A selected report item, however, must be source-backed.
    contracts.validate_provenance(provenance, path)
    return provenance


def _merge_provenance(candidates: list[Mapping[str, Any]], path: str) -> list[dict[str, Any]]:
    """Merge source channels while preserving every candidate-backed URL once."""
    merged: dict[str, dict[str, Any]] = {}
    seen_urls: dict[str, set[str]] = {}
    for index, candidate in enumerate(candidates):
        provenance = _candidate_provenance(candidate, f"{path}.candidate[{index}]")
        for channel in provenance:
            channel_id = channel["channel_id"]
            if channel_id not in merged:
                merged[channel_id] = {
                    "channel_id": channel_id,
                    "channel_label": channel["channel_label"],
                    "links": [],
                }
                seen_urls[channel_id] = set()
            for link in channel["links"]:
                url = link["url"]
                if url not in seen_urls[channel_id]:
                    merged[channel_id]["links"].append(copy.deepcopy(link))
                    seen_urls[channel_id].add(url)
    result = list(merged.values())
    contracts.validate_provenance(result, path)
    return result


def _noon_model_sections(model: Mapping[str, Any], section_ids: Sequence[str]) -> Mapping[str, Any]:
    sections = model.get("sections")
    if not isinstance(sections, Mapping) or set(sections) != set(section_ids):
        raise contracts.ContractError("model.sections must match configured noon section IDs")
    return sections


def _enforce_selection_limit(assembled: Mapping[str, Any], section_id: str, selected_count: int) -> None:
    raw_definitions = assembled.get("section_definitions")
    section_ids = contracts.validate_section_definitions(
        raw_definitions,
        "assembled.section_definitions",
    )
    if section_id not in section_ids:
        raise contracts.ContractError(f"section {section_id} is not configured")
    definition = next(item for item in raw_definitions if item["id"] == section_id)
    limit = definition["selection_limit"]
    minimum = limit["min"]
    maximum = limit["max"]
    if not minimum <= selected_count <= maximum:
        raise contracts.ContractError(
            f"model.sections.{section_id} violates selection limit {minimum}-{maximum}: got {selected_count}"
        )


def _enforce_total_selection_limit(assembled: Mapping[str, Any], selected_count: int) -> None:
    limit = assembled.get("total_selection_limit")
    if limit is None:
        return
    if not isinstance(limit, Mapping):
        raise contracts.ContractError("assembled.total_selection_limit must be an object")
    maximum = limit.get("max")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 0:
        raise contracts.ContractError("assembled.total_selection_limit.max is invalid")
    if selected_count > maximum:
        raise contracts.ContractError(
            f"model.sections total violates selection limit max {maximum}: got {selected_count}"
        )


def _replace_noon_candidate_ref(
    value: Any,
    reference_map: Mapping[str, str],
    path: str,
) -> Any:
    if not isinstance(value, Mapping) or "candidate_ref" not in value:
        return value
    if "candidate_id" in value:
        raise contracts.ContractError(f"{path} must not contain both candidate_ref and candidate_id")
    reference = contracts.candidate_ref(value.get("candidate_ref"), f"{path}.candidate_ref")
    candidate_id = reference_map.get(reference)
    if candidate_id is None:
        raise contracts.ContractError(f"{path}.candidate_ref is outside the allowed candidate set")
    normalized = dict(value)
    normalized.pop("candidate_ref", None)
    normalized["candidate_id"] = candidate_id
    return normalized


def _normalize_noon_candidate_refs(
    model_sections: Mapping[str, Any],
    points: Any,
    assembled_sections: Mapping[str, list[str]],
    section_ids: tuple[str, ...],
) -> tuple[dict[str, Any], Any]:
    section_reference_maps: dict[str, dict[str, str]] = {}
    all_references: dict[str, str] = {}
    for section_position, section_id in enumerate(section_ids, 1):
        reference_map = {
            contracts.noon_candidate_ref(section_position, candidate_position): candidate_id
            for candidate_position, candidate_id in enumerate(assembled_sections[section_id], 1)
        }
        section_reference_maps[section_id] = reference_map
        all_references.update(reference_map)
    normalized_sections: dict[str, Any] = {}
    for section_id in section_ids:
        items = model_sections[section_id]
        normalized_sections[section_id] = (
            [
                _replace_noon_candidate_ref(
                    value,
                    section_reference_maps[section_id],
                    f"model.sections.{section_id}[{index}]",
                )
                for index, value in enumerate(items)
            ]
            if isinstance(items, list)
            else items
        )
    normalized_points = (
        [
            _replace_noon_candidate_ref(value, all_references, f"model.top_points[{index}]")
            for index, value in enumerate(points)
        ]
        if isinstance(points, list)
        else points
    )
    return normalized_sections, normalized_points


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
    raw_definitions = assembled.get("section_definitions")
    section_ids = contracts.validate_section_definitions(
        raw_definitions,
        "assembled.section_definitions",
    )
    model_sections = _noon_model_sections(model, section_ids)
    registry, assembled_sections = _registry(assembled, contracts.NOON_REPORT)
    points = model.get("top_points")
    model_sections, points = _normalize_noon_candidate_refs(
        model_sections,
        points,
        assembled_sections,
        section_ids,
    )
    if not isinstance(points, list):
        raise contracts.ContractError("model.top_points must be an array")
    top_points_config = assembled.get("top_points", {"max": 5})
    if not isinstance(top_points_config, Mapping):
        raise contracts.ContractError("assembled.top_points must be an object")
    top_points_max = top_points_config.get("max")
    if isinstance(top_points_max, bool) or not isinstance(top_points_max, int) or top_points_max < 0:
        raise contracts.ContractError("assembled.top_points.max is invalid")
    if len(points) > top_points_max:
        raise contracts.ContractError(
            f"model.top_points must contain at most {top_points_max} items"
        )
    top_points_max_per_section = top_points_config.get("max_per_section", 2)
    if (
        isinstance(top_points_max_per_section, bool)
        or not isinstance(top_points_max_per_section, int)
        or top_points_max_per_section < 1
    ):
        raise contracts.ContractError("assembled.top_points.max_per_section is invalid")
    used: set[str] = set()
    selected_section_by_id: dict[str, str] = {}
    details: dict[str, list[dict[str, Any]]] = {section: [] for section in section_ids}
    warnings: list[dict[str, Any]] = []
    for section_id in section_ids:
        items = model_sections[section_id]
        if not isinstance(items, list):
            raise contracts.ContractError(f"model.sections.{section_id} must be an array")
        _enforce_selection_limit(assembled, section_id, len(items))
        for index, value in enumerate(items):
            path = f"model.sections.{section_id}[{index}]"
            cid, candidate = _candidate(registry, assembled_sections, section_id, value, path, used)
            title = candidate.get("title")
            text = candidate.get("text")
            if not isinstance(title, str) or not isinstance(text, str):
                raise contracts.ContractError(f"candidate_registry.{cid} has invalid immutable text")
            title_only = contracts.is_title_only_evidence(title, text)
            headline_zh = value.get("headline_zh")
            resolved_detail: dict[str, Any] = {
                "candidate_id": cid,
                "headline": title,
                "content_mode": "title_only" if title_only else "summary",
                "published_at": candidate.get("published_at"),
                "provenance": _candidate_provenance(candidate, f"resolved.sections.{section_id}[{index}].provenance"),
            }
            if title_only:
                warnings.append(
                    {
                        "code": "title_only_detail",
                        "candidate_id": cid,
                        "section": section_id,
                    }
                )
            else:
                summary = contracts.noon_detail_summary(value.get("summary"), f"{path}.summary")
                _check_supported_numbers(summary, candidate, f"{path}.summary")
                resolved_detail["summary"] = summary
            english_headline = (
                re.search(r"[A-Za-z]", title) is not None
                and re.search(r"[\u3400-\u9fff]", title) is None
            )
            if english_headline:
                if headline_zh in (None, ""):
                    raise contracts.ContractError(
                        f"{path}.headline_zh is required for an English headline"
                    )
                headline_zh = _safe_model_text(headline_zh, f"{path}.headline_zh")
                _check_supported_numbers(headline_zh, candidate, f"{path}.headline_zh")
                visible_characters = _visible_text_length(headline_zh)
                if not 12 <= visible_characters <= 28:
                    warnings.append(
                        {
                            "code": "headline_zh_length",
                            "candidate_id": cid,
                            "section": section_id,
                            "characters": visible_characters,
                            "expected": "12-28",
                        }
                    )
                resolved_detail["headline_zh"] = headline_zh
            details[section_id].append(resolved_detail)
            selected_section_by_id[cid] = section_id
    _enforce_total_selection_limit(assembled, sum(len(items) for items in details.values()))
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
        point_section = selected_section_by_id.get(cid)
        if point_section is None:
            raise contracts.ContractError(f"{path}.candidate_id has no selected section")
        section_point_count = sum(
            1 for existing in resolved_points
            if selected_section_by_id.get(existing["candidate_id"]) == point_section
        )
        if section_point_count >= top_points_max_per_section:
            raise contracts.ContractError(
                f"{path} top_points section {point_section} has at most "
                f"{top_points_max_per_section} items"
            )
        point_ids.add(cid)
        topic = contracts.noon_top_point_topic(value.get("topic"), f"{path}.topic")
        if len(topic) >= 7:
            warnings.append(
                {
                    "code": "top_point_topic_length",
                    "candidate_id": cid,
                    "section": point_section,
                    "characters": len(topic),
                    "preferred": "4-6",
                    "accepted": "4-8",
                }
            )
        fact = contracts.top_point_fact(value.get("fact"), f"{path}.fact")
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
    contracts.validate_resolved(resolved, noon_section_ids=section_ids)
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
        return resolve_agents(model, assembled, report_date, generated_at=generated_at)
    raise contracts.ContractError(f"unsupported report {report_id!r}")


def _project_candidate(
    candidate: Mapping[str, Any],
    fresh: bool,
    path: str,
    *,
    category: str | None = None,
) -> dict[str, Any]:
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
    project = {
        "name": name,
        "url": repository,
        "description": description,
        "stars_today": stars,
        "is_fresh_hot": bool(fresh),
    }
    if fresh:
        if not isinstance(category, str) or not category.strip():
            raise contracts.ContractError(f"{path}.category is required for fresh_hot projects")
        project["category"] = category
    return project


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


def _publication_project_descriptions(
    value: Any,
    expected_ids: Sequence[str],
    by_name: Mapping[str, str],
    path: str,
) -> dict[str, str]:
    if not isinstance(value, list):
        raise contracts.ContractError(f"{path} must be an array")
    result: dict[str, str] = {}
    ordered_ids: list[str] = []
    for index, row in enumerate(value):
        row_path = f"{path}[{index}]"
        if not isinstance(row, Mapping) or set(row) != {"full_name", "description"}:
            raise contracts.ContractError(f"{row_path} must contain full_name and description")
        name = row.get("full_name")
        if not isinstance(name, str) or name not in by_name:
            raise contracts.ContractError(f"{row_path}.full_name is unknown")
        cid = by_name[name]
        if cid in result:
            raise contracts.ContractError(f"{row_path}.full_name is reused")
        ordered_ids.append(cid)
        result[cid] = contracts.safe_text(row.get("description"), f"{row_path}.description")
    if ordered_ids != list(expected_ids):
        raise contracts.ContractError(f"{path} does not match the producer project order")
    return result


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


def displayed_open_source_ids(assembled: Mapping[str, Any]) -> list[str]:
    """Return the program-owned open-source projects that will be rendered."""
    registry, sections = _registry(assembled, contracts.AGENTS_REPORT)
    report_plan = assembled.get("report_plan")
    if report_plan is not None:
        profiles.validate_report_plan(report_plan, contracts.AGENTS_REPORT)
        board = profiles.component_by_kind(report_plan, "project_board")
        board_id = board["id"]
        open_ids = sections.get(board_id)
        source_id = board["bindings"][0]["source"]
        snapshots = assembled.get("source_snapshots", {})
        open_metadata = snapshots.get(source_id, {}) if isinstance(snapshots, Mapping) else {}
    else:
        open_ids = sections.get("open_source")
        metadata = assembled.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise contracts.ContractError("assembled.metadata must be an object")
        open_metadata = metadata.get("open_source", {})
    if not isinstance(open_ids, list):
        raise contracts.ContractError("assembled agents open_source section is invalid")
    by_id: dict[str, Mapping[str, Any]] = {}
    for cid in open_ids:
        if not isinstance(cid, str) or cid not in registry or not isinstance(registry[cid], Mapping):
            raise contracts.ContractError("assembled agents open_source section references an invalid candidate")
        by_id[cid] = registry[cid]
    by_name: dict[str, str] = {}
    for cid, candidate in by_id.items():
        extra = candidate.get("extra", {})
        name = extra.get("full_name") if isinstance(extra, Mapping) else None
        name = name or candidate.get("title")
        if isinstance(name, str):
            by_name[name] = cid
    if not isinstance(open_metadata, Mapping):
        raise contracts.ContractError("metadata.open_source must be an object")
    fresh_refs = open_metadata.get("fresh_hot", [])
    if not isinstance(fresh_refs, list):
        raise contracts.ContractError("metadata.open_source.fresh_hot must be an array")
    categories = _category_rows(
        open_metadata.get("local_report_categories", []),
        "metadata.open_source.local_report_categories",
    )
    result: list[str] = []
    for index, ref in enumerate(fresh_refs):
        cid = _ref_id(ref, by_id, by_name, f"metadata.open_source.fresh_hot[{index}]")
        if cid not in result:
            result.append(cid)
    for index, (_title, refs) in enumerate(categories):
        if not refs:
            raise contracts.ContractError("category mapping projects must be non-empty")
        for ref_index, ref in enumerate(refs[:3]):
            cid = _ref_id(
                ref,
                by_id,
                by_name,
                f"metadata.open_source.local_report_categories[{index}].projects[{ref_index}]",
            )
            if cid not in result:
                result.append(cid)
    return result


def resolve_agents(
    model: Mapping[str, Any] | str | bytes,
    assembled: Mapping[str, Any],
    report_date: str,
    *,
    generated_at: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Resolve AI choices while restoring the producer-owned radar facts."""
    if isinstance(model, (str, bytes)):
        model = parse_model_response(model)
    if not isinstance(model, Mapping):
        raise contracts.ContractError("model response must be an object")
    contracts.reject_legacy_model_keys(model)
    registry, assembled_sections = _registry(assembled, contracts.AGENTS_REPORT)
    report_plan = assembled.get("report_plan")
    if report_plan is not None:
        profiles.validate_report_plan(report_plan, contracts.AGENTS_REPORT)
        cluster_component = profiles.component_by_kind(report_plan, "semantic_clusters")
        codex_component = profiles.component_by_kind(report_plan, "producer_markdown")
        synthesis_component = profiles.component_by_kind(report_plan, "semantic_synthesis")
        board_component = profiles.component_by_kind(report_plan, "project_board")
        ai_section_id = cluster_component["id"]
        trend_section_id = synthesis_component["id"]
        board_section_id = board_component["id"]
        ai_ids = assembled_sections.get(ai_section_id)
        open_ids = assembled_sections.get(board_section_id)
        if not isinstance(ai_ids, list) or not isinstance(open_ids, list):
            raise contracts.ContractError("assembled agents sections do not match Report Plan")
        source_snapshots = assembled.get("source_snapshots")
        if not isinstance(source_snapshots, Mapping):
            raise contracts.ContractError("assembled.source_snapshots must be an object")
        codex_source = codex_component["bindings"][0]["source"]
        codex_metadata = source_snapshots.get(codex_source, {})
        board_source = board_component["bindings"][0]["source"]
        open_metadata = source_snapshots.get(board_source, {})
        if not isinstance(open_metadata, Mapping):
            raise contracts.ContractError("metadata.open_source must be an object")
        publication = open_metadata.get("publication")
        producer_content = isinstance(publication, Mapping)
        if publication is not None and not producer_content:
            raise contracts.ContractError("metadata.open_source.publication must be an object")
        model_sections = model.get("sections")
        expected_model_sections = {ai_section_id} if producer_content else {ai_section_id, trend_section_id}
        if model_sections is None:
            # Read-only compatibility for archived semantic responses. New
            # prompts emit the shared sections envelope exclusively.
            model_sections = {
                ai_section_id: model.get("ai_ecosystem"),
            }
            if not producer_content:
                model_sections[trend_section_id] = model.get("open_source_trends")
        if not isinstance(model_sections, Mapping) or set(model_sections) != expected_model_sections:
            raise contracts.ContractError("model.sections must match the semantic Report Plan components")
        ai_model = model_sections[ai_section_id]
        trends_model = None if producer_content else model_sections[trend_section_id]
        cluster_policy = cluster_component["policy"]
        board_policy = board_component["policy"]
        synthesis_policy = synthesis_component["policy"]
        max_projects_per_category = board_policy["max_projects_per_category"]
        fresh_snapshot_key = board_policy["fresh_snapshot_key"]
        categories_snapshot_key = board_policy["categories_snapshot_key"]
        quality_snapshot_key = board_policy["quality_snapshot_key"]
    else:
        ai_section_id = "ai_ecosystem"
        trend_section_id = "open_source_trends"
        board_section_id = "open_source"
        ai_ids = assembled_sections.get(ai_section_id)
        open_ids = assembled_sections.get(board_section_id)
        if not isinstance(ai_ids, list) or not isinstance(open_ids, list):
            raise contracts.ContractError("assembled agents sections are invalid")
        metadata = assembled.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise contracts.ContractError("assembled.metadata must be an object")
        codex_metadata = metadata.get("codexradar", {})
        open_metadata = metadata.get("open_source", {})
        publication = None
        producer_content = False
        ai_model = model.get("ai_ecosystem")
        trends_model = model.get("open_source_trends")
        cluster_policy = {"max_items": 3, "max_candidates_per_item": 3, "coverage_target": 5}
        synthesis_policy = {"exact_items": 2}
        max_projects_per_category = 3
        fresh_snapshot_key = "fresh_hot"
        categories_snapshot_key = "local_report_categories"
        quality_snapshot_key = "quality"
    if isinstance(codex_metadata, str):
        codex_markdown = codex_metadata
    elif isinstance(codex_metadata, Mapping):
        snapshot_key = (
            codex_component["policy"]["snapshot_key"]
            if report_plan is not None
            else "markdown"
        )
        codex_markdown = codex_metadata.get(snapshot_key)
    else:
        codex_markdown = None
    contracts.validate_codex_markdown(
        codex_markdown,
        expected_title=(codex_component["title"] if report_plan is not None else "CodexRadar 智力效率"),
    )
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
    fresh_refs = open_metadata.get(fresh_snapshot_key, [])
    if not isinstance(fresh_refs, list):
        raise contracts.ContractError("metadata.open_source.fresh_hot must be an array")
    fresh_ids = [_ref_id(ref, by_id, by_name, f"metadata.open_source.fresh_hot[{index}]") for index, ref in enumerate(fresh_refs)]
    if len(set(fresh_ids)) != len(fresh_ids) or not set(fresh_ids).issubset(set(hot_ids)):
        raise contracts.ContractError("fresh_hot must be a unique subset of hot_today")
    fresh_set = set(fresh_ids)

    categories_value = open_metadata.get(categories_snapshot_key, [])
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
    category_by_id = {
        cid: title
        for (title, _refs), category_ids in zip(parsed_categories, resolved_category_ids)
        for cid in category_ids
    }

    project_tokens: set[str] = set()
    project_cache: dict[str, dict[str, Any]] = {}
    for cid, candidate in by_id.items():
        project = _project_candidate(
            candidate,
            cid in fresh_set,
            f"candidate_registry.{cid}",
            category=category_by_id.get(cid),
        )
        project_cache[cid] = project
        name = project["name"].casefold()
        project_tokens.add(name)
        if "/" in name:
            project_tokens.update(part for part in name.split("/") if len(part) >= 3)
    category_rows: list[dict[str, Any]] = []
    displayed_ids = set(displayed_open_source_ids(assembled))
    category_titles: list[str] = []
    for _index, (title, _refs) in enumerate(parsed_categories):
        category_titles.append(title)

    producer_fresh_descriptions: dict[str, str] = {}
    producer_category_descriptions: list[dict[str, str]] = []
    if producer_content:
        if not isinstance(publication, Mapping) or set(publication) != {"trends", "fresh_hot", "categories"}:
            raise contracts.ContractError(
                "metadata.open_source.publication must contain trends, fresh_hot, and categories"
            )
        producer_fresh_descriptions = _publication_project_descriptions(
            publication["fresh_hot"],
            fresh_ids,
            by_name,
            "metadata.open_source.publication.fresh_hot",
        )
        publication_categories = publication["categories"]
        if not isinstance(publication_categories, list) or len(publication_categories) != len(parsed_categories):
            raise contracts.ContractError("metadata.open_source.publication.categories does not match producer categories")
        for index, ((title, _refs), category_ids) in enumerate(zip(parsed_categories, resolved_category_ids)):
            category_path = f"metadata.open_source.publication.categories[{index}]"
            category = publication_categories[index]
            if not isinstance(category, Mapping) or set(category) != {"name", "projects"}:
                raise contracts.ContractError(f"{category_path} must contain name and projects")
            if category.get("name") != title:
                raise contracts.ContractError(f"{category_path}.name does not match producer category")
            producer_category_descriptions.append(
                _publication_project_descriptions(
                    category.get("projects"),
                    category_ids,
                    by_name,
                    f"{category_path}.projects",
                )
            )
    else:
        descriptions_model = model.get("open_source_descriptions")
        if not isinstance(descriptions_model, list):
            raise contracts.ContractError("model.open_source_descriptions must be an array")
        translated_descriptions: dict[str, str] = {}
        for index, value in enumerate(descriptions_model):
            path = f"model.open_source_descriptions[{index}]"
            if not isinstance(value, Mapping):
                raise contracts.ContractError(f"{path} must be an object")
            contracts.reject_legacy_model_keys(value, path)
            unknown = set(value) - {"candidate_id", "description_zh"}
            if unknown:
                raise contracts.ContractError(f"{path} has unknown fields: {sorted(unknown)!r}")
            if set(value) != {"candidate_id", "description_zh"}:
                raise contracts.ContractError(f"{path} must contain candidate_id and description_zh")
            cid_value = value.get("candidate_id")
            cid = contracts.candidate_id(cid_value, f"{path}.candidate_id")
            if cid not in by_id:
                raise contracts.ContractError(f"{path}.candidate_id is unknown")
            if cid not in displayed_ids:
                raise contracts.ContractError(f"{path}.candidate_id is not a displayed project")
            if cid in translated_descriptions:
                raise contracts.ContractError(f"{path}.candidate_id is reused")
            description = contracts.safe_text(value.get("description_zh"), f"{path}.description_zh")
            if len(description) > _SUMMARY_MAX_CHARS:
                raise contracts.ContractError(f"{path}.description_zh must be at most {_SUMMARY_MAX_CHARS} characters")
            if not re.search(r"[\u3400-\u9fff]", description):
                raise contracts.ContractError(f"{path}.description_zh must contain Chinese text")
            _check_supported_numbers(description, by_id[cid], f"{path}.description_zh")
            translated_descriptions[cid] = description
        if set(translated_descriptions) != displayed_ids:
            missing = sorted(displayed_ids - set(translated_descriptions))
            extra = sorted(set(translated_descriptions) - displayed_ids)
            raise contracts.ContractError(
                f"model.open_source_descriptions must cover displayed projects exactly; missing={missing!r}, extra={extra!r}"
            )
        for cid, description in translated_descriptions.items():
            project_cache[cid]["description"] = description

    for index, title in enumerate(category_titles):
        category_ids = resolved_category_ids[index][:max_projects_per_category]
        category_projects = []
        for cid in category_ids:
            category_project = copy.deepcopy(project_cache[cid])
            if producer_content:
                category_project["description"] = producer_category_descriptions[index][cid]
            category_project.pop("category", None)
            category_projects.append(category_project)
        category_rows.append({
            "title": title,
            "projects": category_projects,
        })

    quality = copy.deepcopy(open_metadata.get(quality_snapshot_key, {}))
    if not isinstance(quality, Mapping):
        raise contracts.ContractError("metadata.open_source.quality must be an object")
    _metric_safety(quality, "metadata.open_source.quality")
    max_ai_items = cluster_policy["max_items"]
    if not isinstance(ai_model, list) or len(ai_model) > max_ai_items:
        raise contracts.ContractError(
            f"model.sections.{ai_section_id} must contain at most {max_ai_items} items"
        )
    seen_ai: set[str] = set()
    ai_resolved: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for index, item in enumerate(ai_model):
        path = f"model.sections.{ai_section_id}[{index}]"
        candidate_id_list, candidates = _candidate_group(
            registry,
            assembled_sections,
            ai_section_id,
            item,
            path,
            seen_ai,
            max_count=cluster_policy["max_candidates_per_item"],
        )
        topic = contracts.ecosystem_topic(item.get("topic"), f"{path}.topic")
        summary = _check_ai_summary(item.get("summary"), candidates, f"{path}.summary")
        ai_resolved.append({
            "candidate_ids": candidate_id_list,
            "topic": topic,
            "summary": summary,
            "provenance": _merge_provenance(
                candidates,
                f"resolved.sections.{ai_section_id}[{index}].provenance",
            ),
        })
    configured_coverage = cluster_policy["coverage_target"]
    if configured_coverage and len(ai_ids) >= configured_coverage:
        coverage_target = min(configured_coverage, len(ai_ids))
        if len(seen_ai) < coverage_target:
            warnings.append(
                {
                    "code": "ai_ecosystem_coverage",
                    "available_candidates": len(ai_ids),
                    "selected_candidates": len(seen_ai),
                    "target_candidates": coverage_target,
                }
            )
    exact_trends = synthesis_policy["exact_items"]
    if producer_content:
        publication_trends = publication.get("trends") if isinstance(publication, Mapping) else None
        if not isinstance(publication_trends, list) or len(publication_trends) < exact_trends:
            raise contracts.ContractError(
                f"metadata.open_source.publication.trends needs at least {exact_trends} items"
            )
        trends = [
            contracts.safe_text(value, f"metadata.open_source.publication.trends[{index}]")
            for index, value in enumerate(publication_trends[:exact_trends])
        ]
    else:
        if not isinstance(trends_model, list) or len(trends_model) != exact_trends:
            raise contracts.ContractError(
                f"model.sections.{trend_section_id} must contain exactly {exact_trends} items"
            )
        trends = [
            _trend_summary(value, f"model.sections.{trend_section_id}[{index}]", project_tokens)
            for index, value in enumerate(trends_model)
        ]
    fresh_projects = []
    for cid in fresh_ids:
        fresh_project = copy.deepcopy(project_cache[cid])
        if producer_content:
            fresh_project["description"] = producer_fresh_descriptions[cid]
        fresh_projects.append(fresh_project)
    board_resolved = {
        "fresh_hot": fresh_projects,
        "categories": category_rows,
        "quality": quality,
    }
    if report_plan is not None:
        block_values = {
            cluster_component["id"]: ai_resolved,
            codex_component["id"]: {"markdown": codex_markdown},
            synthesis_component["id"]: trends,
            board_component["id"]: board_resolved,
        }
        resolved = {
            "schema_version": contracts.SCHEMA_VERSION,
            "report": contracts.AGENTS_REPORT,
            "report_date": contracts.date(report_date, "resolved.report_date"),
            "generated_at": _generated_at(generated_at),
            "sections": {
                component["id"]: block_values[component["id"]]
                for component in report_plan["components"]
            },
        }
        contracts.validate_resolved(resolved, report_plan=report_plan)
    else:
        resolved = {
            "schema_version": contracts.SCHEMA_VERSION,
            "report": contracts.AGENTS_REPORT,
            "date": contracts.date(report_date, "resolved.date"),
            "sections": {
                "ai_ecosystem": ai_resolved,
                "codexradar": {"markdown": codex_markdown},
                "open_source": {"trends": trends, **board_resolved},
            },
        }
        contracts.validate_resolved(resolved)
    return resolved, warnings
