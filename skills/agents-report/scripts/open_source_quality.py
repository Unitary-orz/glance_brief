#!/usr/bin/env python3
"""Quality checks for the agents-radar open-source project section.

The collector receives the upstream Markdown after RSS HTML stripping, while the
final cron response is Markdown formatted by an LLM.  This module checks both
representations without making network requests or changing report content.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from collections import OrderedDict
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = Path(
    os.environ.get(
        "AGENTS_RADAR_QUALITY_CONFIG",
        str(
            Path(__file__).resolve().parents[1]
            / "config"
            / "agents_radar_quality.json"
        ),
    )
)

MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
GITHUB_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
PROJECT_BULLET_RE = re.compile(
    r"^\s*-\s*(?P<label>热门项目|其他项目)\s*[：:]\s*(?P<body>.*)$"
)
RENDERED_CATEGORY_RE = re.compile(r"^[①②③④⑤⑥⑦⑧⑨⑩]\s+\S")


def load_quality_config(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Load quality rules from JSON, with a conservative fallback if absent."""
    config_path = Path(path) if path else DEFAULT_CONFIG
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}

    try:
        max_other = int(raw.get("other_projects_max", 4))
    except (TypeError, ValueError):
        max_other = 4
    if max_other < 1:
        max_other = 4

    env_output_dir = os.environ.get("AGENTS_RADAR_CRON_OUTPUT_DIR", "").strip()
    project_link_prefix = str(
        raw.get("project_link_prefix", "https://github.com/")
    ).strip()
    if not project_link_prefix:
        project_link_prefix = "https://github.com/"

    return {
        "other_projects_max": max_other,
        "cron_job_id": str(raw.get("cron_job_id", "")),
        "cron_output_dir": env_output_dir or str(raw.get("cron_output_dir", "")),
        "project_link_prefix": project_link_prefix.rstrip("/") + "/",
        "config_path": str(config_path),
    }


def _category_heading(line: str) -> bool:
    """Recognize the upstream category headings, without fixing category names."""
    stripped = line.strip()
    return (
        not stripped.startswith("|")
        and bool(stripped)
        and unicodedata.category(stripped[0]).startswith("S")
        and not stripped.endswith(("。", "！", "？", ".", "!", "?"))
        and not stripped.startswith(("---", "===", "今日", "数据来源"))
    )


def _valid_project_link(label: str, url: str, prefix: str) -> bool:
    """Return whether a Markdown link points to the configured repository host."""
    label = label.strip()
    if not GITHUB_REPO_RE.fullmatch(label):
        return False
    normalized_prefix = prefix.rstrip("/") + "/"
    if not url.lower().startswith(normalized_prefix.lower()):
        return False
    remainder = url[len(normalized_prefix) :].split("?", 1)[0].split("#", 1)[0]
    parts = [part for part in remainder.strip("/").split("/") if part]
    if len(parts) < 2:
        return False
    linked_repo = f"{parts[0]}/{parts[1]}".removesuffix(".git")
    return linked_repo.lower() == label.lower().removesuffix(".git")


def _extract_project_rows(
    line: str,
    project_link_prefix: str,
) -> list[tuple[str, str | None]]:
    """Extract project rows from upstream table cells or Markdown list items."""
    stripped = line.strip()
    if stripped.startswith("|"):
        cell = stripped[1:].strip()
        if cell.endswith("|"):
            cell = cell[:-1].rstrip()
    else:
        list_item = re.match(r"^[-*]\s+(.*)$", stripped)
        if not list_item:
            return []
        cell = list_item.group(1).strip()
    if not cell or cell == "项目" or set(cell) <= {"-", ":", "|", " "}:
        return []

    rows: list[tuple[str, str | None]] = []
    for label, url in MARKDOWN_LINK_RE.findall(cell):
        label = label.strip()
        url = url.strip()
        if GITHUB_REPO_RE.fullmatch(label):
            rows.append(
                (
                    label,
                    url if _valid_project_link(label, url, project_link_prefix) else None,
                )
            )
    if rows:
        return rows

    plain = GITHUB_REPO_RE.fullmatch(cell)
    if plain:
        return [(cell, None)]

    return []


def inspect_source_projects(text: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Inspect project links and category counts in collector output."""
    rules = config or load_quality_config()
    categories: OrderedDict[str, dict[str, Any]] = OrderedDict()
    rows: list[dict[str, Any]] = []
    current_category = "未识别分类"

    for line_number, line in enumerate(text.splitlines(), start=1):
        if _category_heading(line):
            current_category = line.strip()
            continue

        extracted_rows = _extract_project_rows(
            line,
            rules["project_link_prefix"],
        )
        if not extracted_rows:
            continue

        for name, url in extracted_rows:
            category = categories.setdefault(
                current_category,
                {"project_count": 0, "linked_project_count": 0, "unlinked_projects": []},
            )
            category["project_count"] += 1
            if url:
                category["linked_project_count"] += 1
            else:
                category["unlinked_projects"].append(name)
            rows.append(
                {
                    "name": name,
                    "url": url,
                    "category": current_category,
                    "line": line_number,
                }
            )

    linked = [row for row in rows if row["url"]]
    unlinked = [row for row in rows if not row["url"]]
    warnings: list[dict[str, Any]] = []

    if not rows:
        warnings.append(
            {
                "code": "source_project_rows_missing",
                "message": "未识别到开源项目行，无法检查项目链接。",
            }
        )
    elif unlinked:
        warnings.append(
            {
                "code": "source_project_links_missing",
                "message": "来源项目链接缺失：" + "、".join(row["name"] for row in unlinked),
                "projects": [row["name"] for row in unlinked],
            }
        )

    category_output = []
    for name, category in categories.items():
        category_output.append(
            {
                "name": name,
                "project_count": category["project_count"],
                "linked_project_count": category["linked_project_count"],
                "unlinked_projects": category["unlinked_projects"],
            }
        )

    return {
        "ok": not warnings,
        "source_project_count": len(rows),
        "source_linked_project_count": len(linked),
        "source_unlinked_project_count": len(unlinked),
        "source_unlinked_projects": [row["name"] for row in unlinked],
        "categories": category_output,
        "other_projects_max": rules["other_projects_max"],
        "warnings": warnings,
        "config_path": rules["config_path"],
    }


def _split_apparent_items(body: str) -> int:
    """Count visible items on an ``其他项目`` line for threshold checking."""
    body = body.strip()
    if not body or body in {"无", "—", "-"}:
        return 0

    # The configured output format uses 「简介」 once per project.
    descriptions = body.count("「")
    if descriptions:
        return descriptions

    links = MARKDOWN_LINK_RE.findall(body)
    if links:
        return len(links)

    parts = [part.strip() for part in re.split(r"[、；;]", body) if part.strip()]
    return len(parts) or 1


def validate_rendered_report(
    text: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a final Markdown report produced by the cron agent."""
    rules = config or load_quality_config()
    # Hermes cron audit files contain the original prompt and script output before
    # the actual delivered Markdown.  Validate only the response when present;
    # direct Feishu/Markdown files have no marker and are handled as-is.
    response_marker = re.search(r"(?m)^## Response\s*$", text)
    if response_marker:
        text = text[response_marker.end() :]

    warnings: list[dict[str, Any]] = []
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if not re.match(r"^📡\s*\*\*agents-radar 生态报告\s*\|", first_line):
        warnings.append(
            {
                "code": "report_preface_present",
                "message": "最终报告必须直接以 agents-radar 标题开头，不能包含前言或执行说明。",
            }
        )

    heading = re.search(r"(?m)^\*\*🔥\s*开源热点趋势\*\*\s*$", text)
    if not heading:
        warnings.append(
            {
                "code": "open_source_section_missing",
                "message": "未找到「🔥 开源热点趋势」板块。",
            }
        )
        return {
            "ok": False,
            "warnings": warnings,
            "project_line_count": 0,
            "other_project_lines": [],
            "other_projects_max": rules["other_projects_max"],
            "config_path": rules["config_path"],
        }

    section = text[heading.end() :]
    separator = re.search(r"(?m)^---\s*$", section)
    if separator:
        section = section[: separator.start()]

    current_category = "未识别分类"
    project_lines: list[dict[str, Any]] = []
    other_lines: list[dict[str, Any]] = []
    hot_line_counts: dict[str, int] = {}

    for line_number, line in enumerate(section.splitlines(), start=1):
        stripped = line.strip()
        if RENDERED_CATEGORY_RE.match(stripped):
            current_category = stripped
            continue

        if "新项目发现" in stripped or "🆕 新发现" in stripped:
            warnings.append(
                {
                    "code": "new_discovery_section_forbidden",
                    "line": line_number,
                    "message": "主报告不得生成“新项目发现”或“🆕 新发现”区域。",
                }
            )

        match = PROJECT_BULLET_RE.match(line)
        if match:
            label = match.group("label")
            body = match.group("body").strip()
            all_links = MARKDOWN_LINK_RE.findall(body)
            links = [
                (link_label, url)
                for link_label, url in all_links
                if _valid_project_link(
                    link_label,
                    url,
                    rules["project_link_prefix"],
                )
            ]
            invalid_links = [
                {"label": link_label, "url": url}
                for link_label, url in all_links
                if not _valid_project_link(
                    link_label,
                    url,
                    rules["project_link_prefix"],
                )
            ]
            apparent_count = 0 if body in {"", "无", "—", "-"} else (
                1 if label == "热门项目" else _split_apparent_items(body)
            )
            item = {
                "category": current_category,
                "label": label,
                "body": body,
                "line": line_number,
                "link_count": len(links),
                "invalid_links": invalid_links,
                "apparent_item_count": apparent_count,
            }
            project_lines.append(item)

            if label == "热门项目":
                hot_line_counts[current_category] = hot_line_counts.get(current_category, 0) + 1
                if hot_line_counts[current_category] > 1:
                    warnings.append(
                        {
                            "code": "category_hot_projects_too_many",
                            "category": current_category,
                            "line": line_number,
                            "message": f"{current_category} 只能保留一个热门项目。",
                        }
                    )

            if invalid_links:
                warnings.append(
                    {
                        "code": "rendered_project_links_invalid",
                        "category": current_category,
                        "line": line_number,
                        "links": invalid_links,
                        "message": (
                            f"{current_category} 的{label}包含不符合 "
                            f"{rules['project_link_prefix']} 契约的项目链接。"
                        ),
                    }
                )

            if apparent_count and len(links) < apparent_count:
                warnings.append(
                    {
                        "code": "rendered_project_links_missing",
                        "category": current_category,
                        "line": line_number,
                        "message": (
                            f"{current_category} 的{label}缺少项目链接 "
                            f"（可见项目 {apparent_count} 个，Markdown 链接 {len(links)} 个）。"
                        ),
                    }
                )

            if label == "其他项目":
                other_lines.append(item)
                warnings.append(
                    {
                        "code": "other_project_section_forbidden",
                        "category": current_category,
                        "line": line_number,
                        "message": "主报告不得生成“其他项目”行。",
                    }
                )
                if apparent_count > rules["other_projects_max"]:
                    warnings.append(
                        {
                            "code": "other_projects_too_many",
                            "category": current_category,
                            "line": line_number,
                            "count": apparent_count,
                            "max": rules["other_projects_max"],
                            "message": (
                                f"{current_category} 的其他项目有 {apparent_count} 个，"
                                f"超过上限 {rules['other_projects_max']} 个。"
                            ),
                        }
                    )
            continue

        if (
            stripped
            and not stripped.startswith(("-", "**", "📡", "---", "①", "②"))
            and not stripped.startswith("这是")
        ):
            current_category = stripped

    return {
        "ok": not warnings,
        "warnings": warnings,
        "project_line_count": len(project_lines),
        "project_lines": project_lines,
        "other_project_lines": other_lines,
        "other_projects_max": rules["other_projects_max"],
        "config_path": rules["config_path"],
    }


def format_warnings(result: dict[str, Any]) -> str:
    """Render a short human-readable warning for terminal/cron use."""
    if result.get("ok"):
        return "✅ agents-radar 开源项目板块检查通过"

    lines = ["⚠️ agents-radar 开源项目板块需要修正"]
    for warning in result.get("warnings", []):
        lines.append(f"- {warning.get('message', warning.get('code', '未知问题'))}")
    return "\n".join(lines)
