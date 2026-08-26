#!/usr/bin/env python3
"""Convert the legacy agents-radar Markdown payload into a small JSON shape.

The parser intentionally understands only the legacy report boundaries and the
five category headings used by the report.  It does not try to infer missing
rows or repair malformed Markdown: malformed input raises ``ParseError``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence


PROJECT_SECTION = "二、各维度热门项目"
TRENDS_SECTION = "三、趋势信号分析"
COMMUNITY_SECTION = "四、社区关注热点"
CATEGORIES = (
    "🔧 AI 基础工具",
    "🤖 AI 智能体/工作流",
    "📦 AI 应用",
    "🧠 大模型/训练",
    "🔍 RAG/知识库",
)
TABLE_HEADER = ("", "项目", "语言", "Stars（总量 / 今日）", "简要说明")


_MARKDOWN_LINK_RE = re.compile(r"\[([^\]\r\n]+)\]\(([^)\s]+)\)")
_STARS_RE = re.compile(
    r"^([0-9][0-9,]*)"
    r"(?:(?:（\+([0-9][0-9,]*)）)|(?:\(\+([0-9][0-9,]*)\)))?$"
)


class ParseError(ValueError):
    """Raised when the input does not match the supported legacy contract."""


def _find_unique_marker(lines: Sequence[str], marker: str) -> int:
    matches = [index for index, line in enumerate(lines) if line.strip() == marker]
    if len(matches) != 1:
        if not matches:
            raise ParseError(f"missing fixed boundary: {marker}")
        raise ParseError(f"duplicate fixed boundary: {marker}")
    return matches[0]


def _extract_cell(line: str, context: str) -> str:
    stripped = line.strip()
    if not stripped.startswith("|"):
        raise ParseError(f"{context} must be a Markdown table cell line")
    cell = stripped[1:].strip()
    if cell.endswith("|"):
        cell = cell[:-1].rstrip()
    return cell


def _parse_project_link(line: str, context: str) -> tuple[str, str]:
    cell = _extract_cell(line, context)
    match = _MARKDOWN_LINK_RE.fullmatch(cell)
    if match is None:
        raise ParseError(f"{context} must contain exactly one Markdown project link")
    name, url = match.groups()
    if not name.strip() or not url.strip():
        raise ParseError(f"{context} has an empty project name or URL")
    return name.strip(), url.strip()


def _parse_stars(line: str, context: str) -> tuple[str, int | None]:
    cell = _extract_cell(line, context)
    match = _STARS_RE.fullmatch(cell)
    if match is None:
        raise ParseError(f"{context} has invalid Stars value")
    today = match.group(2) or match.group(3)
    stars_today = int(today.replace(",", "")) if today is not None else None
    if stars_today is not None and stars_today > 0:
        return "hot", stars_today
    return "other", None


def _parse_category_rows(category: str, raw_lines: Sequence[str]) -> list[dict[str, Any]]:
    lines = [line for line in raw_lines if line.strip()]
    if not lines:
        raise ParseError(f"category {category!r} has no project rows")

    # The legacy report has a five-line table header.  It is optional here so
    # the parser can consume the same four-line records in a compact fixture,
    # but a partial/malformed header is never silently discarded.
    cells: list[str] = []
    for line in lines[: len(TABLE_HEADER)]:
        try:
            cells.append(_extract_cell(line, f"category {category!r} header"))
        except ParseError:
            break
    if tuple(cells) == TABLE_HEADER:
        lines = lines[len(TABLE_HEADER) :]
    elif cells and cells[0] == "":
        raise ParseError(f"category {category!r} has a malformed table header")

    if not lines:
        raise ParseError(f"category {category!r} has no project rows")
    if len(lines) % 4 != 0:
        raise ParseError(
            f"category {category!r} project records must have exactly four lines"
        )

    projects: list[dict[str, Any]] = []
    for offset in range(0, len(lines), 4):
        number = offset // 4 + 1
        context = f"category {category!r} project {number}"
        name, url = _parse_project_link(lines[offset], f"{context} link")

        language = _extract_cell(lines[offset + 1], f"{context} language")
        if not language:
            raise ParseError(f"{context} language is empty")

        role, stars_today = _parse_stars(lines[offset + 2], f"{context} Stars")

        description = _extract_cell(lines[offset + 3], f"{context} description")
        if not description:
            raise ParseError(f"{context} description is empty")

        project: dict[str, Any] = {
            "name": name,
            "url": url,
            "description": description,
            "category": category,
            "role": role,
        }
        if stars_today is not None:
            project["stars_today"] = stars_today
        projects.append(project)
    return projects


def _parse_projects(lines: Sequence[str], start: int, end: int) -> list[dict[str, Any]]:
    category_positions = [
        (index, line.strip())
        for index, line in enumerate(lines[start + 1 : end], start=start + 1)
        if line.strip() in CATEGORIES
    ]
    expected = list(CATEGORIES)
    actual = [category for _, category in category_positions]
    if actual != expected:
        raise ParseError(
            "category headings must appear exactly once in fixed order; "
            f"expected {expected!r}, got {actual!r}"
        )

    if category_positions[0][0] > start + 1:
        prefix = lines[start + 1 : category_positions[0][0]]
        if any(line.strip() for line in prefix):
            raise ParseError("unexpected content before the first fixed category heading")

    projects: list[dict[str, Any]] = []
    for position, (category_start, category) in enumerate(category_positions):
        chunk_end = (
            category_positions[position + 1][0]
            if position + 1 < len(category_positions)
            else end
        )
        projects.extend(_parse_category_rows(category, lines[category_start + 1 : chunk_end]))
    return projects


def parse_markdown(markdown: str) -> dict[str, Any]:
    """Parse supported legacy Markdown into the fixed output structure."""
    if not isinstance(markdown, str) or not markdown.strip():
        raise ParseError("Markdown evidence must be a non-empty string")

    lines = markdown.splitlines()
    project_start = _find_unique_marker(lines, PROJECT_SECTION)
    trends_start = _find_unique_marker(lines, TRENDS_SECTION)
    community_start = _find_unique_marker(lines, COMMUNITY_SECTION)
    if not project_start < trends_start < community_start:
        raise ParseError("fixed section boundaries are out of order")

    projects = _parse_projects(lines, project_start, trends_start)
    trend_lines = [line.strip() for line in lines[trends_start + 1 : community_start] if line.strip()]
    if not trend_lines:
        raise ParseError("trend section has no trend lines")

    items: list[dict[str, Any]] = [
        {"kind": "trend", "text": trend} for trend in trend_lines[:2]
    ]
    items.extend({"kind": "project", **project} for project in projects)
    return {"items": items}


def _extract_evidence(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise ParseError("input JSON must be an object")

    agents_radar = payload.get("agents_radar")
    if isinstance(agents_radar, dict) and "stdout" in agents_radar:
        stdout = agents_radar["stdout"]
        if not isinstance(stdout, str):
            raise ParseError("agents_radar.stdout must be a string")
        return stdout

    items = payload.get("items")
    if isinstance(items, list) and items:
        first = items[0]
        if isinstance(first, dict) and "evidence" in first:
            evidence = first["evidence"]
            if not isinstance(evidence, str):
                raise ParseError("items[0].evidence must be a string")
            return evidence

    raise ParseError("input must contain agents_radar.stdout or items[0].evidence")


def convert_payload(payload: Any) -> dict[str, Any]:
    """Extract supported evidence from a JSON payload and convert it."""
    return parse_markdown(_extract_evidence(payload))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert legacy agents-radar Markdown evidence to JSON"
    )
    parser.add_argument("--input", required=True, type=Path, help="input JSON file")
    parser.add_argument("--output", required=True, type=Path, help="output JSON file")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        with args.input.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        converted = convert_payload(payload)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as handle:
            json.dump(converted, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except (OSError, json.JSONDecodeError, ParseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
