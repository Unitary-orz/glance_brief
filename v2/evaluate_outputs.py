#!/usr/bin/env python3
"""Deterministic, mechanical checks for V1/V2 Markdown reports.

This module intentionally does not attempt to judge relevance, factuality,
semantic deduplication, or writing quality.  It only measures properties that
can be observed directly in the rendered Markdown.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


# This deliberately handles the ordinary inline Markdown link form.  Link
# labels are not part of the metrics, but keeping the expression focused on
# the destination makes duplicate URL counting unambiguous.
_MARKDOWN_LINK_RE = re.compile(
    r"(?<!!)\[[^\]\n]*\]\(\s*(?:<([^>\n]*)>|([^\s)\n]+))"
)
_NUMBERED_ITEM_RE = re.compile(r"^\s*\d+[.)、]\s+\S")
_SOURCE_LINE_RE = re.compile(r"^\s*>\s*来源\s*[：:]", re.IGNORECASE)
_PROJECT_LINE_RE = re.compile(r"^\s*-\s*(热门项目|其他项目)\s*[：:]")
_TREND_ITEM_RE = re.compile(r"^\s*-\s*[①②③④⑤⑥⑦⑧⑨⑩]\s+\S")

_NOON_MARKERS = (
    "📰 今日热点简报",
    "### 今日要点",
    "### 分类详情",
    "**① 国际要闻**",
    "**② 国内要闻**",
    "**③ 宏观与商业**",
    "**④ AI 主线**",
)

_AGENTS_SECTION_MARKERS = (
    "**🤖 AI 生态动态**",
    "**🧠 CodexRadar 智力效率**",
    "**🔥 开源热点趋势**",
)
_AGENTS_TITLE_RE = re.compile(
    r"^📡\s*\*\*agents-radar\s+生态报告\s*\|[^*]+\*\*\s*$"
)


def _markdown_links(markdown: str) -> list[str]:
    """Return inline Markdown link destinations in source order.

    Images are excluded because ``![alt](...)`` is not a Markdown hyperlink.
    The expression also accepts angle-bracket destinations and strips neither
    URL content nor URL case: duplicate URLs are exact-string duplicates.
    """

    urls: list[str] = []
    for match in _MARKDOWN_LINK_RE.finditer(markdown):
        destination = match.group(1) if match.group(1) is not None else match.group(2)
        if destination:
            urls.append(destination)
    return urls


def _ordered_unique(values: list[str]) -> list[str]:
    """Return values once each while preserving their first-seen order."""

    return list(dict.fromkeys(values))


def _line_index(markdown: str, marker: str) -> int | None:
    """Return the line index of the first line containing ``marker``."""

    for index, line in enumerate(markdown.splitlines()):
        if marker in line:
            return index
    return None


def _markers_in_order(markdown: str, markers: tuple[str, ...]) -> tuple[int, list[str]]:
    """Count required markers and check that their first occurrences are ordered."""

    lines = markdown.splitlines()
    positions: list[int] = []
    present: list[str] = []
    for marker in markers:
        position = next((i for i, line in enumerate(lines) if marker in line), None)
        if position is not None:
            positions.append(position)
            present.append(marker)
    ordered = len(present) == len(markers) and positions == sorted(positions)
    return len(present), present if ordered else present


def _section_lines(markdown: str, start_marker: str, end_marker: str | None = None) -> list[str]:
    """Return lines after one marker and before the next marker, if present."""

    lines = markdown.splitlines()
    start = next((i for i, line in enumerate(lines) if start_marker in line), None)
    if start is None:
        return []
    end = len(lines)
    if end_marker is not None:
        end = next(
            (i for i in range(start + 1, len(lines)) if end_marker in lines[i]),
            len(lines),
        )
    return lines[start + 1 : end]


def _common_metrics(markdown: str) -> dict[str, Any]:
    """Measure Markdown properties independent of the report contract."""

    urls = _markdown_links(markdown)
    counts = Counter(urls)
    unique_urls = _ordered_unique(urls)
    duplicate_urls = [url for url in unique_urls if counts[url] > 1]

    return {
        "char_count": len(markdown),
        "non_empty_line_count": sum(1 for line in markdown.splitlines() if line.strip()),
        "links": urls,
        "link_count": len(urls),
        "unique_urls": unique_urls,
        "unique_link_count": len(unique_urls),
        "duplicate_urls": duplicate_urls,
        # This is the number of repeated occurrences, not merely the number
        # of URL values that repeat: [a](u), [b](u), [c](u) has two.
        "duplicate_link_count": len(urls) - len(unique_urls),
    }


def _noon_metrics(markdown: str) -> dict[str, Any]:
    """Measure the fixed noon-news skeleton and its observable list fields."""

    lines = markdown.splitlines()
    marker_count, present = _markers_in_order(markdown, _NOON_MARKERS)
    positions = [
        next((i for i, line in enumerate(lines) if marker in line), None)
        for marker in _NOON_MARKERS
    ]
    ordered = (
        all(position is not None for position in positions)
        and positions == sorted(position for position in positions if position is not None)
    )

    top_lines = _section_lines(markdown, "### 今日要点", "### 分类详情")
    source_line_count = sum(1 for line in lines if _SOURCE_LINE_RE.match(line))

    return {
        "contract_complete": marker_count == len(_NOON_MARKERS) and ordered,
        "contract_marker_count": marker_count,
        "source_line_count": source_line_count,
        "top_point_count": sum(1 for line in top_lines if _NUMBERED_ITEM_RE.match(line)),
    }


def _agents_metrics(markdown: str) -> dict[str, Any]:
    """Measure the fixed agents-report skeleton without semantic judgments."""

    lines = markdown.splitlines()
    first_non_empty = next((line.strip() for line in lines if line.strip()), "")
    title_present = bool(_AGENTS_TITLE_RE.fullmatch(first_non_empty))
    section_marker_count = sum(
        1 for marker in _AGENTS_SECTION_MARKERS if any(marker in line for line in lines)
    )
    separator_count = sum(1 for line in lines if line.strip() == "---")

    trend_lines = _section_lines(markdown, "**🔥 开源热点趋势**")
    # The trend prose comes before the first ordinary category heading.  A
    # project row is not a trend row, even though both are Markdown bullets.
    trend_line_count = 0
    for line in trend_lines:
        if _PROJECT_LINE_RE.match(line):
            break
        if _TREND_ITEM_RE.match(line):
            trend_line_count += 1

    project_lines = [line for line in trend_lines if _PROJECT_LINE_RE.match(line)]
    hot_project_line_count = sum(
        1 for line in project_lines if re.match(r"^\s*-\s*热门项目\s*[：:]", line)
    )
    other_project_line_count = sum(
        1 for line in project_lines if re.match(r"^\s*-\s*其他项目\s*[：:]", line)
    )

    return {
        "contract_complete": (
            title_present
            and section_marker_count == len(_AGENTS_SECTION_MARKERS)
            and separator_count == 2
            and trend_line_count == 2
        ),
        "contract_marker_count": int(title_present) + section_marker_count,
        "separator_count": separator_count,
        "trend_line_count": trend_line_count,
        "project_line_count": len(project_lines),
        "hot_project_line_count": hot_project_line_count,
        "other_project_line_count": other_project_line_count,
    }


def markdown_metrics(markdown: str, report: str) -> dict[str, Any]:
    """Return deterministic metrics for one rendered Markdown report.

    ``report`` selects the fixed contract checks.  Unknown report names still
    receive the generic Markdown metrics and a false ``contract_complete``;
    this keeps the evaluator useful for comparisons without silently treating
    an unrecognised contract as valid.
    """

    if not isinstance(markdown, str):
        raise TypeError("markdown must be a string")

    metrics = _common_metrics(markdown)
    if report == "noon-news":
        metrics.update(_noon_metrics(markdown))
    elif report == "agents-report":
        metrics.update(_agents_metrics(markdown))
    else:
        metrics.update({"contract_complete": False, "contract_marker_count": 0})
    return metrics


def _numeric_scalars(metrics: dict[str, Any]) -> dict[str, int | float]:
    """Select scalar numeric values, deliberately excluding booleans."""

    return {
        key: value
        for key, value in metrics.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }


def compare_outputs(v1: str, v2: str, report: str) -> dict[str, Any]:
    """Evaluate two Markdown outputs and calculate mechanical V2-minus-V1 deltas."""

    v1_metrics = markdown_metrics(v1, report)
    v2_metrics = markdown_metrics(v2, report)
    v1_numeric = _numeric_scalars(v1_metrics)
    v2_numeric = _numeric_scalars(v2_metrics)
    delta = {
        key: v2_numeric[key] - v1_numeric[key]
        for key in v1_numeric
        if key in v2_numeric
    }
    return {
        "report": report,
        "v1": v1_metrics,
        "v2": v2_metrics,
        "delta": delta,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare deterministic Markdown metrics for V1 and V2 outputs."
    )
    parser.add_argument("--report", required=True, help="report contract: noon-news or agents-report")
    parser.add_argument("--v1", required=True, type=Path, help="path to the V1 Markdown file")
    parser.add_argument("--v2", required=True, type=Path, help="path to the V2 Markdown file")
    parser.add_argument("--output", type=Path, help="also write the JSON result to this path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        v1 = args.v1.read_text(encoding="utf-8")
        v2 = args.v2.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"cannot read Markdown input: {exc}") from exc

    result = compare_outputs(v1, v2, args.report)
    encoded = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded + "\n", encoding="utf-8")
        except OSError as exc:
            raise SystemExit(f"cannot write JSON output: {exc}") from exc
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
