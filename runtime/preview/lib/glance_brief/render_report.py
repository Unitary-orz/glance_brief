"""Deterministic Markdown rendering for glance_brief v0.3.0 resolved reports."""
from __future__ import annotations

import re
import unicodedata
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from . import contracts, profiles



def _inline(value: Any, path: str, *, allow_empty: bool = False) -> str:
    # Validation also prevents a semantic value from injecting a new block.
    return contracts.safe_text(value, path, allow_empty=allow_empty)


def _label(value: Any, path: str) -> str:
    text = _inline(value, path)
    text = re.sub(r"\s*[:：]\s*", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _category_suffix(value: Any, path: str) -> str:
    """Render the category text without a leading category icon."""
    text = _inline(value, path).lstrip()
    while text:
        first = text[0]
        if first in "\ufe0f\u200d" or unicodedata.category(first) in {"So", "Sk"}:
            text = text[1:].lstrip()
            continue
        break
    return text or "分类"


def _source_label(value: Any, path: str) -> str:
    """Hide transport metadata while keeping the publisher/channel identity."""
    text = _label(value, path)
    text = re.sub(r"(?i)\b(?:rss|atom\s+feed|web\s+feed|feed)\b", "", text)
    text = re.sub(r"(?:网页采集|网页抓取|网页)", "", text)
    text = re.sub(r"([（(])\s*[·•|/、,，-]+\s*", r"\1", text)
    text = re.sub(r"\s*[·•|/、,，-]+\s*([）)])", r"\1", text)
    text = re.sub(r"\s*[（(]\s*[）)]", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ·/|-")
    return text or "来源"


def _source_links(
    value: Any,
    path: str,
    *,
    separator: str = "•",
    clean_transport: bool = False,
) -> str:
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
        channel_label = (
            _source_label(channel_value.get("channel_label"), f"{channel_path}.channel_label")
            if clean_transport
            else _label(channel_value.get("channel_label"), f"{channel_path}.channel_label")
        )
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
            label = (
                _source_label(link_value.get("label"), f"{link_path}.label")
                if clean_transport
                else _label(link_value.get("label"), f"{link_path}.label")
            )
            # AI HOT's original-link label may carry an editorial/account
            # qualifier in parentheses. It is provenance metadata, not part
            # of the reader-facing publisher name.
            if channel_id == "aihot" and role == "original":
                label = re.sub(r"\s*[（(][^（）()]*[）)]$", "", label).strip()
            link_url = contracts.url(link_value.get("url"), f"{link_path}.url")
            if not isinstance(role, str) or not role:
                raise contracts.ContractError(f"{link_path}.role must be a string")
            if role in {"original", "article", "source", "link"}:
                label = _original_publisher_label(label, link_url)
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


_SOURCE_LABEL_NOISE = re.compile(
    r"(?:RSS|网页|网页动态|官网动态|官方动态|公众号|博客|Blog|Newsroom|News|官方报道|报道)",
    re.IGNORECASE,
)
_SOURCE_TOKEN_STOPWORDS = {
    "ai",
    "the",
    "one",
    "useful",
    "thing",
    "official",
    "news",
    "newsroom",
    "blog",
    "x",
}
_GENERIC_SOURCE_LABELS = {
    "原文",
    "原始",
    "原始报道",
    "来源",
    "article",
    "direct source",
    "link",
    "original",
    "source",
}
_SOCIAL_HOSTS = {"x.com", "twitter.com", "www.x.com", "www.twitter.com", "t.co"}
_INTERMEDIARY_SOURCE_LABEL = re.compile(r"(?:\bHacker(?:\s+News)?\b|buzzing\.cc|新闻聚合|聚合来源|热门)", re.IGNORECASE)
_INTERMEDIARY_HOSTS = {"news.ycombinator.com", "buzzing.cc", "www.buzzing.cc", "aihot.virxact.com"}


def _publisher_label_from_host(host: str) -> str:
    """Derive a conservative publisher label from a verified original URL."""
    parts = host.removeprefix("www.").split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in {"co.uk", "com.au", "co.jp"}:
        stem = parts[-3]
    else:
        stem = parts[-2] if len(parts) >= 2 else parts[0]
    words = stem.replace("-", " ").split()
    return " ".join(word.upper() if word.isascii() and word.isalpha() and len(word) <= 5 else word.title() for word in words)


def _original_publisher_label(label: str, link_url: str) -> str:
    """Do not present an intermediary discovery label as the publisher."""
    host = (urlsplit(link_url).hostname or "").lower()
    if host and host not in _INTERMEDIARY_HOSTS and _INTERMEDIARY_SOURCE_LABEL.search(label):
        return _publisher_label_from_host(host)
    return label


def _compact_ai_source_label(value: Any, path: str) -> str:
    """Return a short publisher label for the AI-ecosystem source row."""
    text = _source_label(value, path)
    # Transport/account qualifiers do not help a reader choose a source.
    text = re.sub(r"\s*[（(][^）)]*[）)]", "", text)
    text = re.sub(r"^\s*(?:X|Twitter)\s+", "", text, flags=re.IGNORECASE)
    text = _SOURCE_LABEL_NOISE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" ·•/-")
    # Long English source names are usually an author plus a publication;
    # the author is the compact, recognizable label for this report.
    if len(text.split()) > 2 and re.search(r"[A-Za-z]", text):
        text = " ".join(text.split()[:2])
    return text or "来源"


def _ai_source_tokens(label: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+|[\u3400-\u9fff]{2,}", label.lower())
    return {token for token in tokens if token not in _SOURCE_TOKEN_STOPWORDS and len(token) > 1}


def _ai_ecosystem_source_links(value: Any, path: str) -> str:
    """Render a compact, reader-facing source row for AI ecosystem items.

    AIHOT item pages remain in the validated provenance registry, but they are
    an editorial intermediary rather than a useful reader-facing source. Show
    original/direct links instead, deduplicate one publisher, prefer a direct
    article over a social post from the same publisher, and cap the visible
    row at two links.
    """
    if not isinstance(value, list) or not value:
        raise contracts.ContractError(f"{path} must contain at least one channel")

    candidates: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    sequence = 0
    for channel_index, channel_value in enumerate(value):
        channel_path = f"{path}[{channel_index}]"
        if not isinstance(channel_value, Mapping):
            raise contracts.ContractError(f"{channel_path} must be an object")
        channel_id = channel_value.get("channel_id")
        if not isinstance(channel_id, str) or not channel_id:
            raise contracts.ContractError(f"{channel_path}.channel_id must be a string")
        links = channel_value.get("links")
        if not isinstance(links, list) or not links:
            raise contracts.ContractError(f"{channel_path}.links must be a non-empty array")
        for link_index, link_value in enumerate(links):
            link_path = f"{channel_path}.links[{link_index}]"
            if not isinstance(link_value, Mapping):
                raise contracts.ContractError(f"{link_path} must be an object")
            role = link_value.get("role")
            link_url = contracts.url(link_value.get("url"), f"{link_path}.url")
            if not isinstance(role, str) or not role:
                raise contracts.ContractError(f"{link_path}.role must be a string")
            if link_url in seen_urls:
                continue
            seen_urls.add(link_url)

            # AIHOT item pages are intentionally hidden.  For AIHOT, only its
            # original media link can be shown; other channels may expose a
            # direct article link under their own native role.
            if channel_id == "aihot" and role != "original":
                continue
            if channel_id != "aihot" and role not in {"original", "article", "source", "link"}:
                continue
            link_label = _compact_ai_source_label(
                link_value.get("label", channel_value.get("channel_label", "来源")),
                f"{link_path}.label",
            )
            channel_label = _compact_ai_source_label(
                channel_value.get("channel_label", "来源"),
                f"{channel_path}.channel_label",
            )
            label = (
                channel_label
                if link_label.casefold() in _GENERIC_SOURCE_LABELS
                and channel_label.casefold() not in {"aihot", "来源"}
                else link_label
            )
            host = (urlsplit(link_url).hostname or "").lower()
            if channel_id == "aihot" and role == "original":
                label = _original_publisher_label(label, link_url)
            candidates.append(
                {
                    "label": label,
                    "url": link_url,
                    "tokens": _ai_source_tokens(label),
                    "social": host in _SOCIAL_HOSTS,
                    "sequence": sequence,
                }
            )
            sequence += 1

    if not candidates:
        return "暂无可见原文"

    # Prefer a direct article over a social post, while retaining source order
    # among otherwise equivalent links.
    candidates.sort(key=lambda item: (item["social"], item["sequence"]))
    selected: list[dict[str, Any]] = []
    for candidate in candidates:
        if any(candidate["tokens"] and candidate["tokens"] & chosen["tokens"] for chosen in selected):
            continue
        selected.append(candidate)
        if len(selected) == 2:
            break
    if not selected:
        selected = candidates[:1]
    return " · ".join(f"[{item['label']}]({item['url']})" for item in selected)


def _english_title(value: str) -> bool:
    return bool(re.search(r"[A-Za-z]", value)) and not bool(re.search(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]", value))


def _render_noon(
    semantic: Mapping[str, Any],
    section_definitions: list[Mapping[str, Any]],
    *,
    report_title: str = "今日热点简报",
) -> str:
    section_ids = contracts.validate_section_definitions(
        section_definitions,
        "assembled.section_definitions",
    )
    contracts.validate_resolved(semantic, noon_section_ids=section_ids)
    definitions = {item["id"]: item for item in section_definitions}
    lines = [f"📰 {_inline(report_title, 'report_plan.title')}", "", "### 今日要点"]
    for index, point in enumerate(semantic["top_points"], 1):
        topic = _inline(point["topic"], f"top_points[{index - 1}].topic")
        fact = _inline(point["fact"], f"top_points[{index - 1}].fact")
        lines.append(f"{index}. {topic}：{fact}")
    lines.extend(["", "### 分类详情", ""])
    for section_index, section_id in enumerate(section_ids):
        definition = definitions[section_id]
        title = _inline(definition["title"], f"section_definitions.{section_id}.title")
        lines.append(f"**{_circled(definition['order'])} {title}**")
        for item_index, item in enumerate(semantic["sections"][section_id]):
            path = f"sections.{section_id}[{item_index}]"
            headline = _inline(item["headline"], f"{path}.headline")
            title_line = f"- **{headline}**"
            translation = item.get("headline_zh")
            if translation and _english_title(headline):
                title_line += f"（{_inline(translation, f'{path}.headline_zh')}）"
            block = [title_line]
            if "summary" in item:
                block.append(f"  {_inline(item['summary'], f'{path}.summary')}")
            block.append(f"  > 来源：{_source_links(item['provenance'], f'{path}.provenance')}")
            lines.extend(block)
            if item_index != len(semantic["sections"][section_id]) - 1:
                lines.append("")
        if section_index != len(section_ids) - 1:
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
        path = f"sections.ai_ecosystem[{index - 1}]"
        topic = _inline(item["topic"], f"{path}.topic")
        summary = _inline(item["summary"], f"{path}.summary")
        source = _ai_ecosystem_source_links(item["provenance"], f"{path}.provenance")
        lines.append(f"- {_circled(index)} **{topic}**：{summary}（来源：{source}）")
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
            category = _category_suffix(project["category"], f"sections.open_source.fresh_hot[{index}].category")
            lines.append(
                f"- {_project_link(project, f'sections.open_source.fresh_hot[{index}]')}{suffix}"
                f"(+{project['stars_today']}★/日)（{category}）"
            )
    lines.extend(["", "📦**最热门开源**"])
    for index, category in enumerate(open_source["categories"], 1):
        lines.extend(["", f"{_circled(index)} {_inline(category['title'], f'sections.open_source.categories[{index - 1}].title')}"])
        projects = category["projects"]
        if not projects:
            lines.append("- 信息有限")
        else:
            rendered_projects = []
            for project_index, project in enumerate(projects):
                project_path = f"sections.open_source.categories[{index - 1}].projects[{project_index}]"
                fresh_prefix = bool(project.get("is_fresh_hot"))
                description = _inline(project["description"], f"{project_path}.description", allow_empty=True)
                suffix = f"「{description}」" if description else ""
                rendered_projects.append(
                    f"{_project_link(project, project_path, fresh_prefix=fresh_prefix)}"
                    f"{suffix}(+{project['stars_today']}★/日)"
                )
            lines.append("- " + " · ".join(rendered_projects))
    return "\n".join(lines).rstrip() + "\n"


def _render_agents_plan(semantic: Mapping[str, Any], report_plan: Mapping[str, Any]) -> str:
    """Render ordered Agents blocks through the fixed kind registry."""
    profiles.validate_report_plan(report_plan, contracts.AGENTS_REPORT)
    contracts.validate_resolved(semantic, report_plan=report_plan)
    sections = semantic["sections"]
    blocks: list[list[str]] = []
    for component in report_plan["components"]:
        component_id = component["id"]
        title = _inline(component["title"], f"report_plan.components.{component_id}.title")
        kind = component["kind"]
        section = sections[component_id]
        if kind == "semantic_clusters":
            block = [f"**🤖 {title}**"]
            for index, item in enumerate(section, 1):
                path = f"sections.{component_id}[{index - 1}]"
                topic = _inline(item["topic"], f"{path}.topic")
                summary = _inline(item["summary"], f"{path}.summary")
                source = _ai_ecosystem_source_links(item["provenance"], f"{path}.provenance")
                block.append(f"- {_circled(index)} **{topic}**：{summary}（来源：{source}）")
        elif kind == "producer_markdown":
            block = [section["markdown"]]
        elif kind == "semantic_synthesis":
            block = [f"**🔥 {title}**"]
            for index, trend in enumerate(section, 1):
                block.append(f"- {_circled(index)} {_inline(trend, f'sections.{component_id}[{index - 1}]')}")
        elif kind == "project_board":
            block = []
            if section["fresh_hot"]:
                fresh_title = _inline(
                    component["policy"]["fresh_title"],
                    f"report_plan.components.{component_id}.policy.fresh_title",
                )
                block.append(f"**✨{fresh_title}**")
                for index, project in enumerate(section["fresh_hot"]):
                    path = f"sections.{component_id}.fresh_hot[{index}]"
                    description = _inline(project["description"], f"{path}.description", allow_empty=True)
                    suffix = f"「{description}」" if description else ""
                    category = _category_suffix(project["category"], f"{path}.category")
                    block.append(
                        f"- {_project_link(project, path)}{suffix}"
                        f"(+{project['stars_today']}★/日)（{category}）"
                    )
                block.append("")
            block.append(f"📦**{title}**")
            for index, category in enumerate(section["categories"], 1):
                category_path = f"sections.{component_id}.categories[{index - 1}]"
                block.extend(["", f"{_circled(index)} {_inline(category['title'], f'{category_path}.title')}"])
                projects = category["projects"]
                if not projects:
                    block.append("- 信息有限")
                    continue
                rendered_projects = []
                for project_index, project in enumerate(projects):
                    project_path = f"{category_path}.projects[{project_index}]"
                    description = _inline(project["description"], f"{project_path}.description", allow_empty=True)
                    suffix = f"「{description}」" if description else ""
                    rendered_projects.append(
                        f"{_project_link(project, project_path, fresh_prefix=bool(project.get('is_fresh_hot')))}"
                        f"{suffix}(+{project['stars_today']}★/日)"
                    )
                block.append("- " + " · ".join(rendered_projects))
        else:
            raise contracts.ContractError(f"unsupported renderer block kind {kind!r}")
        blocks.append(block)

    report_title = _inline(report_plan["title"], "report_plan.title")
    lines = [f"📡 **{report_title} | {semantic['report_date']}**"]
    for block in blocks:
        lines.append("")
        lines.extend(block)
    return "\n".join(lines).rstrip() + "\n"


def _circled(index: int) -> str:
    if 1 <= index <= 20:
        return chr(0x245f + index)
    return f"({index})"


def render_report(
    semantic: Mapping[str, Any],
    *,
    section_definitions: list[Mapping[str, Any]] | None = None,
    report_plan: Mapping[str, Any] | None = None,
) -> str:
    if not isinstance(semantic, Mapping):
        raise contracts.ContractError("resolved report must be an object")
    if semantic.get("report") == contracts.NOON_REPORT:
        if report_plan is not None:
            profiles.validate_report_plan(report_plan, contracts.NOON_REPORT)
            section_definitions = [
                {
                    "id": component["id"],
                    "order": component["order"],
                    "title": component["title"],
                    "editorial_hint": component["editorial_hint"],
                    "minimum_candidates": component["health"]["minimum_candidates"],
                    "selection_limit": component["policy"]["selection_limit"],
                }
                for component in report_plan["components"]
            ]
        if section_definitions is None:
            raise contracts.ContractError("noon rendering requires assembled section definitions")
        return _render_noon(
            semantic,
            section_definitions,
            report_title=(report_plan["title"] if report_plan is not None else "今日热点简报"),
        )
    if semantic.get("report") == contracts.AGENTS_REPORT:
        if report_plan is not None:
            return _render_agents_plan(semantic, report_plan)
        return _render_agents(semantic)
    raise contracts.ContractError("resolved.report is unsupported")
