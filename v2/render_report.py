"""Deterministic Markdown rendering for Brief V2 resolved reports."""
from __future__ import annotations

import re
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any

from . import contracts

NOON_TITLES = {
    "international": "① 国际要闻",
    "macro_business": "② 宏观与商业",
    "ai": "③ AI 主线",
}


def _inline(value: Any, path: str, *, allow_empty: bool = False) -> str:
    # Validation also prevents a semantic value from injecting a new block.
    return contracts.safe_text(value, path, allow_empty=allow_empty)


def _label(value: Any, path: str) -> str:
    text = _inline(value, path)
    text = re.sub(r"\s*[:：]\s*", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _source_links(value: Any, path: str, *, separator: str = "•") -> str:
    """Render a canonical provenance registry without altering URL bytes."""
    if not isinstance(value, list) or not value:
        raise contracts.ContractError(f"{path} must contain at least one channel")
    rendered_channels: list[str] = []
    seen_channels: set[str] = set()
    for index, channel_value in enumerate(value):
        channel_path = f"{path}[{index}]"
        if not isinstance(channel_value, Mapping):
            raise contracts.ContractError(f"{channel_path} must be an object")
        channel_id = channel_value.get("channel_id")
        channel_label = _label(channel_value.get("channel_label"), f"{channel_path}.channel_label")
        links = channel_value.get("links")
        if not isinstance(channel_id, str) or not channel_id:
            raise contracts.ContractError(f"{channel_path}.channel_id must be a string")
        if channel_id in seen_channels:
            raise contracts.ContractError(f"{path} contains a duplicate channel")
        seen_channels.add(channel_id)
        if not isinstance(links, list) or not links:
            raise contracts.ContractError(f"{channel_path}.links must be a non-empty array")
        link_markdown: list[str] = []
        seen_urls: set[str] = set()
        for link_index, link_value in enumerate(links):
            link_path = f"{channel_path}.links[{link_index}]"
            if not isinstance(link_value, Mapping):
                raise contracts.ContractError(f"{link_path} must be an object")
            role = link_value.get("role")
            label = _label(link_value.get("label"), f"{link_path}.label")
            link_url = contracts.url(link_value.get("url"), f"{link_path}.url")
            if not isinstance(role, str) or not role:
                raise contracts.ContractError(f"{link_path}.role must be a string")
            if link_url in seen_urls:
                continue
            seen_urls.add(link_url)
            if not link_markdown:
                if role == "item":
                    visible_label = channel_label
                elif channel_id == "aihot" and role == "original":
                    # AIHOT's original link is an independent media link; when
                    # it is the only link, do not invent a second AIHOT link.
                    visible_label = label
                elif role in {"article", "repository", "repo", "project"}:
                    visible_label = f"{channel_label}•{label}"
                else:
                    visible_label = label
            else:
                visible_label = label
            link_markdown.append(f"[{visible_label}]({link_url})")
        if link_markdown:
            rendered_channels.append(separator.join(link_markdown))
    if not rendered_channels:
        raise contracts.ContractError(f"{path} has no usable links")
    omitted = max(0, len(seen_channels) - 2)
    result = separator.join(rendered_channels[:2])
    if omitted:
        result += f" +{omitted}"
    return result


def _english_title(value: str) -> bool:
    return bool(re.search(r"[A-Za-z]", value)) and not bool(re.search(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]", value))


def _render_noon(semantic: Mapping[str, Any]) -> str:
    contracts.validate_resolved(semantic)
    lines = ["📰 今日热点简报", "", "### 今日要点"]
    for index, point in enumerate(semantic["top_points"], 1):
        lines.append(f"{index}. {_inline(point['topic'], f'top_points[{index - 1}].topic')}：{_inline(point['fact'], f'top_points[{index - 1}].fact')}")
    lines.extend(["", "### 分类详情", ""])
    for section_index, section_id in enumerate(contracts.NOON_SECTION_IDS):
        lines.append(f"**{NOON_TITLES[section_id]}**")
        for item_index, item in enumerate(semantic["sections"][section_id]):
            path = f"sections.{section_id}[{item_index}]"
            title = _inline(item["headline"], f"{path}.headline")
            title_line = f"- **{title}**"
            translation = item.get("headline_zh")
            if translation and _english_title(title):
                title_line += f"（{_inline(translation, f'{path}.headline_zh')}）"
            lines.extend([
                title_line,
                f"  {_inline(item['summary'], f'{path}.summary')}",
                f"  > 来源：{_source_links(item['provenance'], f'{path}.provenance')}",
            ])
        if section_index != len(contracts.NOON_SECTION_IDS) - 1:
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _project_link(project: Mapping[str, Any], path: str, *, fresh_prefix: bool = False) -> str:
    name = _inline(project["name"], f"{path}.name")
    link_url = contracts.url(project["url"], f"{path}.url")
    return f"{'✨ ' if fresh_prefix else ''}[{name}]({link_url})"


def _render_agents(semantic: Mapping[str, Any]) -> str:
    contracts.validate_resolved(semantic)
    sections = semantic["sections"]
    lines = ["📡 **agents-radar 生态报告 | " + semantic["date"] + "**", "", "**🤖 AI 生态动态**"]
    for index, item in enumerate(sections["ai_ecosystem"], 1):
        source = _source_links(item["provenance"], f"sections.ai_ecosystem[{index - 1}].provenance", separator=" · ")
        lines.append(f"- {_circled(index)} {_inline(item['summary'], f'sections.ai_ecosystem[{index - 1}].summary')}（来源：{source}）")
    # The Codex block is producer-owned.  Do not parse, normalize, or rebuild it.
    codex = sections["codexradar"]["markdown"]
    lines.extend(["", codex, "", "**🔥 开源热点趋势**"])
    for index, trend in enumerate(sections["open_source"]["trends"], 1):
        lines.append(f"- {_circled(index)} {_inline(trend, f'sections.open_source.trends[{index - 1}]')}")
    open_source = sections["open_source"]
    if open_source["fresh_hot"]:
        lines.extend(["", "**✨新热门开源**"])
        for index, project in enumerate(open_source["fresh_hot"]):
            description = _inline(project["description"], f"sections.open_source.fresh_hot[{index}].description", allow_empty=True)
            suffix = f"「{description}」" if description else ""
            lines.append(f"- {_project_link(project, f'sections.open_source.fresh_hot[{index}]')}{suffix}(+{project['stars_today']}★/日)")
    for index, category in enumerate(open_source["categories"], 1):
        lines.extend(["", f"{_circled(index)} {_inline(category['title'], f'sections.open_source.categories[{index - 1}].title')}"])
        project = category["project"]
        if project is None:
            lines.append("- 热门项目：信息有限")
        else:
            fresh_prefix = bool(project.get("is_fresh_hot"))
            description = _inline(project["description"], f"sections.open_source.categories[{index - 1}].project.description", allow_empty=True)
            suffix = f"「{description}」" if description else ""
            lines.append(
                f"- 热门项目：{_project_link(project, f'sections.open_source.categories[{index - 1}].project', fresh_prefix=fresh_prefix)}"
                f"{suffix}(+{project['stars_today']}★/日)"
            )
    return "\n".join(lines).rstrip() + "\n"


def _circled(index: int) -> str:
    if 1 <= index <= 20:
        return chr(0x245f + index)
    return f"({index})"


def render_report(semantic: Mapping[str, Any]) -> str:
    if not isinstance(semantic, Mapping):
        raise contracts.ContractError("resolved report must be an object")
    if semantic.get("report") == contracts.NOON_REPORT:
        return _render_noon(semantic)
    if semantic.get("report") == contracts.AGENTS_REPORT:
        return _render_agents(semantic)
    raise contracts.ContractError("resolved.report is unsupported")
