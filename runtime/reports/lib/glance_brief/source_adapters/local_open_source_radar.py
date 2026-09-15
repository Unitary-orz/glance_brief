"""Strict reader for the already-published local radar report.

This is a migration bridge until the local radar writes a structured
publication artifact itself.  It preserves producer-authored text and rejects
layout/provenance drift rather than asking a downstream model to rewrite it.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .. import contracts

_PROJECT_RE = re.compile(
    r"\[(?P<name>[^\]]+)\]\((?P<url>https://github\.com/[^)\s]+)\)"
    r"「(?P<description>[^」]*)」\(\+(?P<stars>[\d,]+)★/日\)"
)
_CATEGORY_RE = re.compile(
    r"^\s*(?:[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]\s+\*\*(?P<legacy>.+)\*\*|\*\*[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]\s+(?P<current>.+)\*\*|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]\s+(?P<plain>.+))\s*$"
)


def _between(text: str, start: str, ends: Sequence[str], path: str) -> str:
    start_index = text.find(start)
    if start_index < 0:
        raise contracts.ContractError(f"{path} is missing {start}")
    start_index += len(start)
    end_indexes = [text.find(marker, start_index) for marker in ends]
    end_indexes = [index for index in end_indexes if index >= 0]
    if not end_indexes:
        raise contracts.ContractError(f"{path} has no closing section marker")
    return text[start_index:min(end_indexes)]


def _expected_names(items: Any, path: str) -> list[str]:
    if not isinstance(items, list):
        raise contracts.ContractError(f"{path} must be an array")
    names: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise contracts.ContractError(f"{path}[{index}] must be an object")
        name = item.get("full_name")
        url = item.get("url")
        if not isinstance(name, str) or url != f"https://github.com/{name}":
            raise contracts.ContractError(f"{path}[{index}] has invalid repository provenance")
        names.append(name)
    if len(names) != len(set(names)):
        raise contracts.ContractError(f"{path} contains duplicate projects")
    return names


def _project_rows(section: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for match in _PROJECT_RE.finditer(section):
        name = match.group("name")
        url = match.group("url")
        if url != f"https://github.com/{name}":
            raise contracts.ContractError(f"local radar publication URL does not match {name!r}")
        description = contracts.safe_text(
            match.group("description"),
            f"local radar publication project {name}.description",
        )
        rows.append({"full_name": name, "description": description})
    return rows


def parse_local_radar_report(
    text: str,
    *,
    report_date: str,
    hot_today: Any,
    fresh_hot: Any,
    local_report_categories: Any = None,
) -> dict[str, Any]:
    """Return published trends, categories, and role-specific project rows.

    ``local_report_categories`` is an optional compatibility assertion for the
    old lexical mapping. The standalone radar now publishes semantic
    categories in Markdown, so the Reports can treat that dated publication as
    authoritative while still checking exact project coverage and provenance.
    """
    if not isinstance(text, str):
        raise contracts.ContractError("local radar archive must be text")
    contracts.date(report_date, "local radar report_date")
    report_marker = f"📡 **本地开源雷达｜{report_date}**"
    if text.count(report_marker) != 1:
        raise contracts.ContractError("local radar archive must contain exactly one dated report")
    report = text[text.index(report_marker):]

    hot_names = _expected_names(hot_today, "local radar hot_today")
    fresh_names = _expected_names(fresh_hot, "local radar fresh_hot")
    if not set(fresh_names).issubset(set(hot_names)):
        raise contracts.ContractError("local radar fresh_hot is not a hot_today subset")

    trend_section = _between(
        report,
        "**🔥 今日趋势**",
        ("**✨ 本期新入榜**", "**🚀 今日热门**"),
        "local radar trend section",
    )
    trends = [
        contracts.safe_text(line[2:].strip(), f"local radar trends[{index}]")
        for index, line in enumerate(trend_section.splitlines())
        if line.startswith("- ") and line[2:].strip()
    ]
    if not trends:
        raise contracts.ContractError("local radar publication has no trend items")

    fresh_section = _between(
        report,
        "**✨ 本期新入榜**",
        ("**🚀 今日热门**",),
        "local radar fresh section",
    )
    fresh_rows = _project_rows(fresh_section)
    if [row["full_name"] for row in fresh_rows] != fresh_names:
        raise contracts.ContractError("local radar publication fresh rows do not match fresh_hot")

    hot_section = _between(
        report,
        "**🚀 今日热门**",
        ("**🌱 新项目发现**", "> 本次独立采集"),
        "local radar hot section",
    )
    parsed_categories: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in hot_section.splitlines():
        heading = _CATEGORY_RE.match(line)
        if heading:
            name = heading.group("legacy") or heading.group("current") or heading.group("plain")
            current = {"name": name, "projects": []}
            parsed_categories.append(current)
            continue
        if current is None:
            continue
        current["projects"].extend(_project_rows(line))

    parsed_shape = [
        (category["name"], [project["full_name"] for project in category["projects"]])
        for category in parsed_categories
    ]
    if local_report_categories is not None:
        if not isinstance(local_report_categories, list):
            raise contracts.ContractError("local radar local_report_categories must be an array")
        expected_categories: list[tuple[str, list[str]]] = []
        for index, category in enumerate(local_report_categories):
            if not isinstance(category, Mapping):
                raise contracts.ContractError(f"local radar local_report_categories[{index}] must be an object")
            name = category.get("name", category.get("title"))
            projects = category.get("projects")
            if not isinstance(name, str) or not isinstance(projects, list) or not all(isinstance(item, str) for item in projects):
                raise contracts.ContractError(f"local radar local_report_categories[{index}] is malformed")
            expected_categories.append((name, list(projects)))
        if parsed_shape != expected_categories:
            raise contracts.ContractError("local radar publication categories do not match producer mapping")
    parsed_hot = [name for _category, names in parsed_shape for name in names]
    if len(parsed_hot) != len(set(parsed_hot)) or set(parsed_hot) != set(hot_names):
        raise contracts.ContractError("local radar publication hot rows do not cover hot_today")

    return {
        "trends": trends,
        "fresh_hot": fresh_rows,
        "categories": parsed_categories,
    }


def load_local_radar_publication(
    report_dir: Path,
    *,
    report_date: str,
    hot_today: Any,
    fresh_hot: Any,
    local_report_categories: Any = None,
) -> dict[str, Any]:
    """Load the newest archive that contains the exact dated local report."""
    if not report_dir.is_dir():
        raise contracts.ContractError(f"local radar report directory is missing: {report_dir}")
    marker = f"📡 **本地开源雷达｜{report_date}**"
    matches: list[tuple[Path, str]] = []
    for path in sorted(report_dir.glob("*.md"), reverse=True):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise contracts.ContractError(f"local radar archive is unreadable: {path}: {exc}") from exc
        if marker in text:
            matches.append((path, text))
    if not matches:
        raise contracts.ContractError(f"local radar has no published report for {report_date}")
    _path, text = matches[0]
    return parse_local_radar_report(
        text,
        report_date=report_date,
        hot_today=hot_today,
        fresh_hot=fresh_hot,
        local_report_categories=local_report_categories,
    )


def adapt_payload(
    payload: Mapping[str, Any],
    *,
    report_date: str,
    report_dir: Path,
) -> dict[str, Any]:
    """Enrich a producer snapshot at the source-adapter boundary.

    The report wrapper need not inspect local-radar fields or validate its
    quality.  This adapter owns the legacy Markdown bridge and returns a new
    payload, leaving the producer result untouched.
    """
    radar_value = payload.get("local_radar")
    if not isinstance(radar_value, Mapping):
        raise contracts.ContractError("local radar producer payload is invalid")
    signals = radar_value.get("signals")
    if not isinstance(signals, Mapping):
        raise contracts.ContractError("local radar producer signals are invalid")
    publication = load_local_radar_publication(
        report_dir,
        report_date=report_date,
        hot_today=signals.get("hot_today"),
        fresh_hot=signals.get("fresh_hot"),
    )
    categories = publication.get("categories")
    if not isinstance(categories, list) or not categories:
        raise contracts.ContractError("local radar publication has no categories")
    radar = dict(radar_value)
    radar["local_report_categories"] = [
        {
            "name": category["name"],
            "projects": [project["full_name"] for project in category["projects"]],
        }
        for category in categories
    ]
    radar["publication"] = publication
    result = dict(payload)
    result["local_radar"] = radar
    return result
