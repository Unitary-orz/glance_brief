"""Deterministic Markdown rendering for glance_brief v0.3.0 resolved reports."""
from __future__ import annotations

import re
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

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
        path = f"sections.ai_ecosystem[{index - 1}]"
        topic = _inline(item["topic"], f"{path}.topic")
        summary = _inline(item["summary"], f"{path}.summary")
        source = _ai_ecosystem_source_links(item["provenance"], f"{path}.provenance")
        lines.append(f"- {_circled(index)} {topic}：{summary}（来源：{source}）")
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
