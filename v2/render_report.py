"""Deterministic Markdown renderer for the independent V2 reports.

The model produces only semantic data.  This module owns the visible Markdown
skeleton, including headings, labels, numbering, separators, and metric
formatting.  It deliberately does not import the V2 assembler or any runtime
code so it can be used as a small standalone command-line program.
"""

from __future__ import annotations

import argparse
import datetime as _datetime
import json
import math
import re
import sys
from collections import OrderedDict
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


_NOON_SECTIONS = ("international", "domestic", "business", "ai")
_NOON_SECTION_TITLES = {
    "international": "① 国际要闻",
    "domestic": "② 国内要闻",
    "business": "③ 宏观与商业",
    "ai": "④ AI 主线",
}

_AGENTS_SECTIONS = ("ai_ecosystem", "model_efficiency", "open_source")

_METRIC_GROUPS = (
    ("intelligence_top2", "① 智力Top2", 2),
    ("balanced_top2", "② 均衡Top2", 2),
    ("value_top3", "③ 性价比Top3", 3),
    ("other", "④ 其他", None),
)

# These characters can otherwise turn a semantic value into Markdown syntax.
# Escaping them keeps the model's text as text without allowing it to create a
# heading, emphasis span, link, image, code span, or table cell.
_PLAIN_MARKDOWN_CHARS = frozenset("\\`*_[]<>#!|~")
_STRUCTURAL_LINES = frozenset({"---", "***", "___"})
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_LATIN_RE = re.compile(r"[A-Za-z]")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")


class _Missing:
    pass


_MISSING = _Missing()


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be an object")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be an array")
    return value


def _field(obj: Mapping[str, Any], name: str, path: str) -> Any:
    value = obj.get(name, _MISSING)
    if value is _MISSING:
        raise ValueError(f"{path}.{name} is required")
    return value


def _only_keys(
    obj: Mapping[str, Any],
    allowed: frozenset[str],
    path: str,
) -> None:
    unknown = set(obj) - allowed
    if unknown:
        names = ", ".join(sorted(str(key) for key in unknown))
        raise ValueError(f"{path} has unknown fields: {names}")


def _checked_text(value: Any, path: str, *, allow_empty: bool = False) -> str:
    """Validate and Markdown-escape a model-controlled plain-text value."""

    if not isinstance(value, str):
        raise ValueError(f"{path} must be a string")
    if not allow_empty and not value.strip():
        raise ValueError(f"{path} must not be empty")

    # A newline is never data in this semantic protocol: accepting one would
    # let a model add a list item, heading, or separator to the fixed output.
    for character in value:
        codepoint = ord(character)
        if character in "\r\n":
            raise ValueError(f"{path} must not contain newlines")
        if codepoint < 0x20 or codepoint == 0x7F:
            raise ValueError(f"{path} contains a control character")

    if value.strip() in _STRUCTURAL_LINES:
        raise ValueError(f"{path} contains a Markdown structural marker")

    # A newline is not required for every Markdown injection.  For example,
    # a category name beginning with ``- `` would become a new list item on
    # the renderer-owned line.  Reject block starters instead of guessing
    # whether a caller intended literal text.
    if re.match(r"^\s*(?:[-+*]|\d+[.)]|>|#{1,6})\s", value):
        raise ValueError(f"{path} starts with Markdown block syntax")

    return "".join(
        ("\\" + character) if character in _PLAIN_MARKDOWN_CHARS else character
        for character in value
    )


def _checked_code_text(value: Any, path: str) -> str:
    """Validate text inserted inside a single-backtick code span."""

    if not isinstance(value, str):
        raise ValueError(f"{path} must be a string")
    if not value.strip():
        raise ValueError(f"{path} must not be empty")
    if any(character in value for character in ("`", "\\", "\r", "\n")):
        raise ValueError(f"{path} contains unsafe code-span characters")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ValueError(f"{path} contains a control character")
    return value


def _optional_text(value: Any, path: str) -> str:
    if value is None:
        return ""
    return _checked_text(value, path, allow_empty=True)


def _checked_url(value: Any, path: str) -> str:
    """Validate an HTTP(S) URL and escape Markdown destination delimiters."""

    if not isinstance(value, str):
        raise ValueError(f"{path} URL must be a string")
    if not value:
        raise ValueError(f"{path} URL must not be empty")
    if any(character in value for character in "\r\n\\"):
        raise ValueError(f"{path} URL contains an unsafe character")
    if any(character.isspace() for character in value):
        raise ValueError(f"{path} URL must not contain whitespace")

    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
    except ValueError as exc:
        raise ValueError(f"{path} URL is invalid") from exc

    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or not hostname:
        raise ValueError(f"{path} URL must use http or https")

    # A closing parenthesis can terminate the Markdown destination before the
    # URL ends.  Backslash escaping is understood by Markdown and leaves the
    # target URL usable when it contains an otherwise legal parenthesis.
    return value.replace(")", r"\)")


def _source_links(
    value: Any,
    path: str,
    *,
    limit: int | None = 2,
    joiner: str = "•",
    add_omitted_count: bool = True,
    group_channels: bool = False,
) -> str:
    sources = _list(value, path)
    if not sources:
        raise ValueError(f"{path} must contain at least one source")

    normalized: list[tuple[str, str, str, str]] = []
    for index, source_value in enumerate(sources):
        source_path = f"{path}[{index}]"
        source = _mapping(source_value, source_path)
        _only_keys(
            source,
            frozenset({"source_id", "label", "publisher", "url"}),
            source_path,
        )
        label = _field(source, "label", source_path)
        label_text = _checked_text(label, f"{source_path}.label")
        if "source_id" in source:
            _checked_text(source["source_id"], f"{source_path}.source_id")
        publisher = source.get("publisher")
        publisher_text = ""
        if publisher is not None:
            if not isinstance(publisher, str):
                raise ValueError(f"{source_path}.publisher must be a string")
            publisher = re.sub(
                r"(?:\s*(?:（[^）]*）|\([^)]*\)))+\s*$", "", publisher.strip()
            )
            publisher_text = _checked_text(
                publisher, f"{source_path}.publisher", allow_empty=True
            )
        label_text = label_text.replace("：", "•").replace(":", "•")
        publisher_text = publisher_text.replace("：", "•").replace(":", "•")
        publisher_text = publisher_text.replace("公众号", "WX")
        url = _checked_url(_field(source, "url", source_path), f"{source_path}.url")
        normalized.append((label_text, publisher_text, url, source_path))

    rendered: list[str] = []
    omitted = 0
    if group_channels:
        groups: OrderedDict[str, list[tuple[str, str]]] = OrderedDict()
        for label_text, publisher_text, url, _ in normalized:
            groups.setdefault(label_text, []).append((publisher_text, url))
        selected_groups = list(groups.items()) if limit is None else list(groups.items())[:limit]
        if limit is not None:
            omitted = max(0, len(groups) - limit)
        for label_text, entries in selected_groups:
            for entry_index, (publisher_text, url) in enumerate(entries):
                if entry_index == 0:
                    link_text = label_text
                    if publisher_text and publisher_text != label_text and publisher_text not in label_text:
                        link_text += f"•{publisher_text}"
                else:
                    link_text = publisher_text or label_text
                rendered.append(f"[{link_text}]({url})")
    else:
        for index, (label_text, publisher_text, url, _) in enumerate(normalized):
            link_text = label_text
            if publisher_text and publisher_text != label_text and publisher_text not in label_text:
                link_text += f"•{publisher_text}"
            if limit is None or index < limit:
                rendered.append(f"[{link_text}]({url})")
        if limit is not None:
            omitted = max(0, len(normalized) - limit)

    result = joiner.join(rendered) if rendered else "无"
    if add_omitted_count and omitted:
        result += f" +{omitted}"
    return result


def _validate_sections(semantic: Mapping[str, Any], expected: tuple[str, ...]) -> Mapping[str, Any]:
    sections_value = semantic.get("sections", _MISSING)
    if sections_value is _MISSING:
        raise ValueError("sections is required")
    sections = _mapping(sections_value, "sections")
    actual = set(sections)
    required = set(expected)
    if actual != required:
        missing = sorted(required - actual)
        unknown = sorted(actual - required)
        details: list[str] = []
        if missing:
            details.append("missing: " + ", ".join(missing))
        if unknown:
            details.append("unknown: " + ", ".join(unknown))
        suffix = f" ({'; '.join(details)})" if details else ""
        raise ValueError(f"sections must contain exactly the fixed section IDs{suffix}")
    return sections


def _validate_report_name(semantic: Any) -> Mapping[str, Any]:
    if not isinstance(semantic, Mapping):
        raise ValueError("semantic input must be an object")
    report = semantic.get("report", _MISSING)
    if report is _MISSING:
        raise ValueError("report is required")
    if not isinstance(report, str):
        raise ValueError("report must be a string")
    if report not in {"noon-news", "agents-report"}:
        raise ValueError("report must be noon-news or agents-report")
    if report == "noon-news":
        if "semantic_protocol" in semantic:
            _only_keys(
                semantic,
                frozenset({"semantic_protocol", "report", "report_date", "generated_at", "top_points", "sections"}),
                "semantic",
            )
            if semantic.get("semantic_protocol") != "glance_brief.noon-news.v2":
                raise ValueError("noon-news semantic_protocol must be glance_brief.noon-news.v2")
            _date(semantic.get("report_date", _MISSING))
            _checked_text(semantic.get("generated_at"), "generated_at")
        else:
            # Keep the standalone renderer able to inspect pre-protocol V2
            # snapshots. The pipeline itself only writes the strict contract.
            _only_keys(semantic, frozenset({"report", "top_points", "sections"}), "semantic")
    else:
        _only_keys(semantic, frozenset({"report", "date", "sections"}), "semantic")
    return semantic


def _render_noon(semantic: Mapping[str, Any]) -> str:
    sections = _validate_sections(semantic, _NOON_SECTIONS)
    strict = semantic.get("semantic_protocol") == "glance_brief.noon-news.v2"

    top_points_value = semantic.get("top_points", _MISSING)
    if top_points_value is _MISSING:
        raise ValueError("top_points is required")
    top_points = _list(top_points_value, "top_points")

    lines = ["📰 今日热点简报", "", "### 今日要点"]
    for index, point_value in enumerate(top_points, start=1):
        point_path = f"top_points[{index - 1}]"
        point = _mapping(point_value, point_path)
        _only_keys(point, frozenset({"item_ids", "topic", "fact"}), point_path)
        if "item_ids" in point:
            item_ids = _list(point["item_ids"], f"{point_path}.item_ids")
            if not item_ids or any(not isinstance(item_id, str) or not item_id for item_id in item_ids):
                raise ValueError(f"{point_path}.item_ids must contain non-empty strings")
        topic = _checked_text(_field(point, "topic", point_path), f"{point_path}.topic")
        fact = _checked_text(_field(point, "fact", point_path), f"{point_path}.fact")
        lines.append(f"{index}. {topic}：{fact}")

    lines.extend(["", "### 分类详情", ""])
    for section_index, section_id in enumerate(_NOON_SECTIONS):
        items = _list(sections[section_id], f"sections.{section_id}")
        lines.append(f"**{_NOON_SECTION_TITLES[section_id]}**")
        for item_index, item_value in enumerate(items):
            item_path = f"sections.{section_id}[{item_index}]"
            item = _mapping(item_value, item_path)
            _only_keys(
                item,
                frozenset({"item_id", "candidate_ids", "headline", "headline_zh", "title", "summary", "why_it_matters", "sources", "published_at", "evidence_level"}),
                item_path,
            )
            if strict:
                for required in ("item_id", "candidate_ids", "headline", "summary", "sources"):
                    if required not in item:
                        raise ValueError(f"{item_path}.{required} is required by the semantic protocol")
                if not isinstance(item["item_id"], str) or not item["item_id"]:
                    raise ValueError(f"{item_path}.item_id must be a non-empty string")
                candidate_ids = _list(item["candidate_ids"], f"{item_path}.candidate_ids")
                if not candidate_ids or any(not isinstance(value, str) or not value for value in candidate_ids):
                    raise ValueError(f"{item_path}.candidate_ids must contain non-empty strings")
                if "evidence_level" in item and item["evidence_level"] not in {"direct", "attributed", "uncertain"}:
                    raise ValueError(f"{item_path}.evidence_level is invalid")
            title_value = item.get("headline", item.get("title", _MISSING))
            title = _checked_text(title_value, f"{item_path}.headline")
            headline_zh = _optional_text(item.get("headline_zh"), f"{item_path}.headline_zh")
            summary = _checked_text(
                _field(item, "summary", item_path), f"{item_path}.summary"
            )
            sources = _source_links(
                _field(item, "sources", item_path),
                f"{item_path}.sources",
                group_channels=True,
            )
            title_line = f"- **{title}**"
            if headline_zh and _LATIN_RE.search(title) and not _CJK_RE.search(title):
                title_line += f"（{headline_zh}）"
            lines.extend(["", title_line, f"  {summary}", f"  > 来源：{sources}"])
        if section_index != len(_NOON_SECTIONS) - 1:
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _number(value: Any, path: str, *, places: int) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number")
    if not math.isfinite(float(value)):
        raise ValueError(f"{path} must be finite")
    if float(value) < 0:
        raise ValueError(f"{path} must not be negative")
    return f"{float(value):.{places}f}"


def _metric_text(items_value: Any, path: str, *, joiner: str) -> str:
    items = _list(items_value, path)
    rendered: list[str] = []
    for index, item_value in enumerate(items):
        item_path = f"{path}[{index}]"
        item = _mapping(item_value, item_path)
        _only_keys(
            item,
            frozenset({"model", "effort", "iq", "minutes", "price_usd"}),
            item_path,
        )
        model = _checked_code_text(
            _field(item, "model", item_path), f"{item_path}.model"
        )
        effort = _checked_code_text(
            _field(item, "effort", item_path), f"{item_path}.effort"
        )
        iq = _number(_field(item, "iq", item_path), f"{item_path}.iq", places=1)
        minutes = _number(
            _field(item, "minutes", item_path), f"{item_path}.minutes", places=1
        )
        price = _number(
            _field(item, "price_usd", item_path),
            f"{item_path}.price_usd",
            places=2,
        )
        rendered.append(
            f"`{model} {effort}`（IQ {iq} · {minutes}m · ${price}）"
        )
    return joiner.join(rendered) if rendered else "无"


def _date(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    if not _DATE_RE.fullmatch(value):
        raise ValueError("date must use YYYY-MM-DD format")
    try:
        _datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("date is invalid") from exc
    return value


def _render_agents(semantic: Mapping[str, Any]) -> str:
    sections = _validate_sections(semantic, _AGENTS_SECTIONS)
    date = _date(semantic.get("date", _MISSING))

    ai_items = _list(sections["ai_ecosystem"], "sections.ai_ecosystem")
    lines = [
        f"📡 **agents-radar 生态报告 | {date}**",
        "",
        "**🤖 AI 生态动态**",
        "",
    ]
    for index, item_value in enumerate(ai_items):
        item_path = f"sections.ai_ecosystem[{index}]"
        item = _mapping(item_value, item_path)
        _only_keys(item, frozenset({"summary", "sources"}), item_path)
        summary = _checked_text(_field(item, "summary", item_path), f"{item_path}.summary")
        sources = _list(_field(item, "sources", item_path), f"{item_path}.sources")
        # Validate sources even when a future renderer policy chooses not to
        # display an empty citation list.
        citation = _source_links(
            sources,
            f"{item_path}.sources",
            limit=None,
            joiner=" · ",
            add_omitted_count=False,
        )
        # The fixed report contract uses circled numerals, not model-provided
        # numbering.  Keep the mapping explicit because format() has no
        # circled-number conversion for arbitrary integers.
        circled = ("①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩")
        marker = circled[index] if index < len(circled) else str(index + 1)
        line = f"- {marker} {summary}"
        if citation != "无":
            line += f"（来源：{citation}）"
        lines.append(line)

    lines.extend(["", "---", "", "**🧠 CodexRadar 智力效率**", ""])
    model_efficiency = _mapping(
        sections["model_efficiency"], "sections.model_efficiency"
    )
    _only_keys(
        model_efficiency,
        frozenset(group[0] for group in _METRIC_GROUPS),
        "sections.model_efficiency",
    )
    allowed_metric_keys = {group[0] for group in _METRIC_GROUPS}
    unknown_metric_keys = set(model_efficiency) - allowed_metric_keys
    if unknown_metric_keys:
        unknown = ", ".join(sorted(str(key) for key in unknown_metric_keys))
        raise ValueError(f"sections.model_efficiency has unknown group IDs: {unknown}")
    for group_key, label, limit in _METRIC_GROUPS:
        value = model_efficiency.get(group_key, [])
        items = _list(value, f"sections.model_efficiency.{group_key}")
        if limit is not None and len(items) > limit:
            raise ValueError(
                f"sections.model_efficiency.{group_key} accepts at most {limit} items"
            )
        # _metric_text performs the item-level validation and fixed numeric
        # formatting.  It is called with the already checked list so missing
        # groups naturally render as “无”.
        rendered = _metric_text(
            items,
            f"sections.model_efficiency.{group_key}",
            joiner="；" if group_key == "other" else " > ",
        )
        lines.append(f"- {label}：{rendered}")

    lines.extend(["", "---", "", "**🔥 开源热点趋势**", ""])
    open_source = _mapping(sections["open_source"], "sections.open_source")
    _only_keys(
        open_source,
        frozenset({"trends", "categories"}),
        "sections.open_source",
    )
    trends = _list(_field(open_source, "trends", "sections.open_source"), "sections.open_source.trends")
    checked_trends = [
        _checked_text(value, f"sections.open_source.trends[{index}]")
        for index, value in enumerate(trends)
    ]
    # The skeleton always has two trend rows.  Missing semantic material is
    # represented explicitly rather than allowing a model to remove a row.
    trend_markers = ("①", "②")
    for index in range(2):
        trend = checked_trends[index] if index < len(checked_trends) else "信息有限"
        lines.append(f"- {trend_markers[index]} {trend}")

    categories = _list(
        _field(open_source, "categories", "sections.open_source"),
        "sections.open_source.categories",
    )
    lines.append("")
    for category_index, category_value in enumerate(categories):
        category_path = f"sections.open_source.categories[{category_index}]"
        category = _mapping(category_value, category_path)
        _only_keys(
            category,
            frozenset({"name", "hot_projects", "other_projects"}),
            category_path,
        )
        name = _checked_text(_field(category, "name", category_path), f"{category_path}.name")
        hot = _list(
            _field(category, "hot_projects", category_path),
            f"{category_path}.hot_projects",
        )
        other = _list(
            _field(category, "other_projects", category_path),
            f"{category_path}.other_projects",
        )
        hot_text = _projects_text(hot, f"{category_path}.hot_projects")
        other_text = _projects_text(other, f"{category_path}.other_projects")
        lines.extend(
            [
                name,
                f"- 热门项目：{hot_text}",
                f"- 其他项目：{other_text}",
            ]
        )
        if category_index != len(categories) - 1:
            lines.append("")

    result = "\n".join(lines).rstrip() + "\n"
    if result.count("\n---\n") != 2:
        # This should only be reachable if a future change lets untrusted text
        # become a standalone separator.  Fail closed rather than emit a
        # contract-breaking report.
        raise ValueError("renderer produced an invalid separator count")
    return result


def _projects_text(projects_value: Any, path: str) -> str:
    projects = _list(projects_value, path)
    rendered: list[str] = []
    for index, project_value in enumerate(projects):
        project_path = f"{path}[{index}]"
        project = _mapping(project_value, project_path)
        _only_keys(
            project,
            frozenset({"name", "url", "description", "stars_today"}),
            project_path,
        )
        name = _checked_text(_field(project, "name", project_path), f"{project_path}.name")
        url = _checked_url(_field(project, "url", project_path), f"{project_path}.url")
        description = _optional_text(
            project.get("description"), f"{project_path}.description"
        )
        entry = f"[{name}]({url})"
        if description:
            entry += f" - {description}"
        if "stars_today" in project:
            stars_today = project["stars_today"]
            if isinstance(stars_today, bool) or not isinstance(stars_today, int) or stars_today <= 0:
                raise ValueError(f"{project_path}.stars_today must be a positive integer")
            entry += f"（+{stars_today:,}★/日）"
        rendered.append(entry)
    return "；".join(rendered) if rendered else "无"


def render_report(semantic: Mapping[str, Any]) -> str:
    """Render a validated V2 semantic report into deterministic Markdown."""

    semantic = _validate_report_name(semantic)
    if semantic["report"] == "noon-news":
        return _render_noon(semantic)
    return _render_agents(semantic)


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a V2 semantic report as Markdown.")
    parser.add_argument("--input", required=True, type=Path, help="semantic JSON path")
    parser.add_argument("--output", required=True, type=Path, help="Markdown output path")
    args = parser.parse_args(argv)

    try:
        with args.input.open("r", encoding="utf-8") as handle:
            semantic = json.load(handle)
        report = render_report(semantic)
        if str(args.output) == "-":
            sys.stdout.write(report)
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report, encoding="utf-8")
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
