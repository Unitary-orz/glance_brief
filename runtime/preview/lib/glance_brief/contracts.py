"""Current schema and safety validators for glance_brief v0.3.0.

The module intentionally knows only the current contracts. Historical
protocol names and presentation-derived shapes are not accepted here.
"""
from __future__ import annotations

import datetime as _datetime
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit

SCHEMA_VERSION = 2
NOON_REPORT = "noon-news"
AGENTS_REPORT = "agents-report"
_LEGACY_AGENTS_SECTION_IDS = ("ai_ecosystem", "codexradar", "open_source")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CANDIDATE_ID_RE = re.compile(r"^c[0-9a-f]{12,64}$")
_CANDIDATE_REF_RE = re.compile(r"^S([1-9][0-9]*)C([0-9]{2,})$")
_SECTION_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

# These keys belonged to removed protocols or make deterministic facts model
# owned.  Unknown harmless keys remain ignorable in model responses, but these
# explicit names are rejected so stale responses cannot pass accidentally.
LEGACY_KEYS = frozenset(
    {
        "semantic_protocol",
        "protocol",
        "item_ref",
        "item_refs",
        "hot_projects",
        "other_projects",
        "title",  # model detail title alias; source candidates use headline
    }
)


class ContractError(ValueError):
    """Raised when a current v0.3.0 object cannot be validated."""


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{path} must be an object")
    return value


def _require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractError(f"{path} must be an array")
    return value


def _only_keys(value: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ContractError(f"{path} has unknown fields: {sorted(map(str, unknown))!r}")


def _required(value: Mapping[str, Any], fields: set[str], path: str) -> None:
    missing = fields - set(value)
    if missing:
        raise ContractError(f"{path} is missing fields: {sorted(missing)!r}")


def safe_text(value: Any, path: str, *, allow_empty: bool = False) -> str:
    """Validate text that will be inserted into a renderer-owned line."""
    if not isinstance(value, str):
        raise ContractError(f"{path} must be a string")
    if not allow_empty and not value.strip():
        raise ContractError(f"{path} must not be empty")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise ContractError(f"{path} contains a control character")
    if "\r" in value or "\n" in value:
        raise ContractError(f"{path} must not contain newlines")
    stripped = value.strip()
    if stripped in {"---", "***", "___"}:
        raise ContractError(f"{path} contains a Markdown structural marker")
    # A semantic value cannot be allowed to create a block or link in the
    # fixed Markdown skeleton.  Ordinary punctuation remains valid.
    if re.search(r"https?://|!\[[^\]]*\]\(|\[[^\]]*\]\(|```", value, re.I):
        raise ContractError(f"{path} contains unsafe Markdown content")
    if re.match(r"^\s*(?:[-+*>#]|\d+[.)])\s", value):
        raise ContractError(f"{path} starts with Markdown block syntax")
    return " ".join(value.split())


def is_title_only_evidence(title: Any, text: Any) -> bool:
    """Return whether a candidate has no evidence beyond its headline."""
    if not isinstance(title, str) or not isinstance(text, str):
        raise ContractError("candidate title/text must be strings")

    def normalized(value: str) -> str:
        return " ".join(unicodedata.normalize("NFKC", value).casefold().split())

    normalized_title = normalized(title)
    normalized_text = normalized(text)
    return bool(normalized_title) and (
        not normalized_text or normalized_text == normalized_title
    )


def url(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{path} must be a non-empty URL string")
    if any(ord(char) < 0x20 or ord(char) == 0x7F or char.isspace() for char in value):
        raise ContractError(f"{path} URL contains whitespace/control content")
    if any(char in value for char in "()<>\\"):
        raise ContractError(f"{path} URL contains a Markdown-unsafe delimiter")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
    except ValueError as exc:
        raise ContractError(f"{path} URL is invalid") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or not hostname:
        raise ContractError(f"{path} URL must use http or https")
    return value


def date(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        raise ContractError(f"{path} must use YYYY-MM-DD")
    try:
        _datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError(f"{path} is not a valid date") from exc
    return value


def timestamp(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{path} must be an ISO-8601 timestamp")
    try:
        parsed = _datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{path} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ContractError(f"{path} must include a timezone")
    return value


def finite_number(value: Any, path: str, *, nonnegative: bool = True) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{path} must be a number")
    if not math.isfinite(float(value)):
        raise ContractError(f"{path} must be finite")
    if nonnegative and float(value) < 0:
        raise ContractError(f"{path} must not be negative")
    return value


def candidate_id(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _CANDIDATE_ID_RE.fullmatch(value):
        raise ContractError(f"{path} must be a stable candidate ID")
    return value


def noon_candidate_ref(section_position: int, candidate_position: int) -> str:
    if section_position < 1 or candidate_position < 1:
        raise ContractError("Noon candidate reference positions must be positive")
    return f"S{section_position}C{candidate_position:02d}"


def candidate_ref(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{path} must be a short candidate reference")
    match = _CANDIDATE_REF_RE.fullmatch(value)
    if match is None or int(match.group(2)) < 1:
        raise ContractError(f"{path} must be a short candidate reference")
    return value


def section_id(value: Any, path: str = "section_id") -> str:
    if not isinstance(value, str) or not _SECTION_ID_RE.fullmatch(value):
        raise ContractError(f"{path} must be a lowercase snake-case identifier")
    return value


def candidate_ids(value: Any, path: str, *, max_count: int | None = None) -> list[str]:
    """Validate a non-empty, ordered group of stable candidate IDs."""
    ids = _require_list(value, path)
    if not ids:
        raise ContractError(f"{path} must contain at least one candidate ID")
    if max_count is not None and len(ids) > max_count:
        raise ContractError(f"{path} must contain at most {max_count} candidate IDs")
    checked = [candidate_id(item, f"{path}[{index}]") for index, item in enumerate(ids)]
    if len(set(checked)) != len(checked):
        raise ContractError(f"{path} must not contain duplicate candidate IDs")
    return checked


def short_topic(value: Any, path: str = "topic") -> str:
    """Validate a compact renderer-owned lead label."""
    text = safe_text(value, path)
    if not 2 <= len(text) <= 16:
        raise ContractError(f"{path} must contain 2-16 characters")
    if re.search(r"[:：,，;；。！？!?]", text):
        raise ContractError(f"{path} must be a short label without sentence punctuation")
    return text


def top_point_fact(value: Any, path: str = "fact") -> str:
    """Validate a concise reader-facing Chinese key-news fact.

    The model may retain natural names and abbreviations; validation only checks
    for a Chinese-language signal and a bounded length, not a maintained name
    list or an English-word ratio.
    """
    text = safe_text(value, path)
    if len(text) > 60:
        raise ContractError(f"{path} must be at most 60 characters")
    if not re.search(r"[\u3400-\u9fff]", text):
        raise ContractError(f"{path} must contain Chinese text")
    return text


def noon_top_point_topic(value: Any, path: str = "topic") -> str:
    """Validate a tiny V1-style event headline for noon key points."""
    text = short_topic(value, path)
    if not 4 <= len(text) <= 8:
        raise ContractError(f"{path} must contain 4-8 characters")
    return text


def ecosystem_topic(value: Any, path: str = "topic") -> str:
    """Validate the compact lead label for Agents ecosystem clusters."""
    text = short_topic(value, path)
    if not 4 <= len(text) <= 8:
        raise ContractError(f"{path} must contain 4-8 characters")
    return text


def noon_detail_summary(value: Any, path: str = "summary") -> str:
    """Validate a bounded Chinese detail summary written by the model."""
    text = safe_text(value, path)
    if len(text) > 120:
        raise ContractError(f"{path} must be at most 120 characters")
    if not re.search(r"[\u3400-\u9fff]", text):
        raise ContractError(f"{path} must contain Chinese text")
    return text


def validate_provenance(value: Any, path: str = "provenance") -> None:
    channels = _require_list(value, path)
    if not channels:
        raise ContractError(f"{path} must contain at least one channel")
    seen_channels: set[str] = set()
    for index, channel_value in enumerate(channels):
        channel_path = f"{path}[{index}]"
        channel = _require_mapping(channel_value, channel_path)
        _only_keys(channel, {"channel_id", "channel_label", "links"}, channel_path)
        channel_id = channel.get("channel_id")
        if not isinstance(channel_id, str) or not channel_id:
            raise ContractError(f"{channel_path}.channel_id must be a non-empty string")
        if channel_id in seen_channels:
            raise ContractError(f"{path} contains duplicate channel_id {channel_id!r}")
        seen_channels.add(channel_id)
        safe_text(channel.get("channel_label"), f"{channel_path}.channel_label")
        links = _require_list(channel.get("links"), f"{channel_path}.links")
        if not links:
            raise ContractError(f"{channel_path}.links must not be empty")
        seen_urls: set[str] = set()
        for link_index, link_value in enumerate(links):
            link_path = f"{channel_path}.links[{link_index}]"
            link = _require_mapping(link_value, link_path)
            _only_keys(link, {"role", "label", "url"}, link_path)
            role = link.get("role")
            if not isinstance(role, str) or not role:
                raise ContractError(f"{link_path}.role must be a non-empty string")
            safe_text(link.get("label"), f"{link_path}.label")
            link_url = url(link.get("url"), f"{link_path}.url")
            if link_url in seen_urls:
                raise ContractError(f"{path} repeats URL within channel")
            seen_urls.add(link_url)


def _validate_noon_detail(value: Any, path: str) -> None:
    detail = _require_mapping(value, path)
    _only_keys(
        detail,
        {"candidate_id", "headline", "headline_zh", "content_mode", "summary", "published_at", "provenance"},
        path,
    )
    _required(detail, {"candidate_id", "headline", "content_mode", "provenance"}, path)
    candidate_id(detail["candidate_id"], f"{path}.candidate_id")
    safe_text(detail["headline"], f"{path}.headline")
    if "headline_zh" in detail and detail["headline_zh"] not in (None, ""):
        safe_text(detail["headline_zh"], f"{path}.headline_zh")
    content_mode = detail["content_mode"]
    if content_mode not in {"summary", "title_only"}:
        raise ContractError(f"{path}.content_mode must be summary or title_only")
    if content_mode == "summary":
        if "summary" not in detail:
            raise ContractError(f"{path} is missing fields: ['summary']")
        noon_detail_summary(detail["summary"], f"{path}.summary")
    elif "summary" in detail:
        raise ContractError(f"{path}.summary is not allowed for title_only content")
    published = detail.get("published_at")
    if published is not None:
        timestamp(published, f"{path}.published_at")
    validate_provenance(detail["provenance"], f"{path}.provenance")


def validate_section_definitions(value: Any, path: str = "section_definitions") -> tuple[str, ...]:
    definitions = _require_list(value, path)
    if not definitions:
        raise ContractError(f"{path} must contain at least one section")
    seen_ids: set[str] = set()
    orders: list[int] = []
    ids: list[str] = []
    for index, definition_value in enumerate(definitions):
        item_path = f"{path}[{index}]"
        definition = _require_mapping(definition_value, item_path)
        _only_keys(
            definition,
            {"id", "order", "title", "editorial_hint", "minimum_candidates", "selection_limit"},
            item_path,
        )
        _required(
            definition,
            {"id", "order", "title", "editorial_hint", "minimum_candidates", "selection_limit"},
            item_path,
        )
        section = section_id(definition["id"], f"{item_path}.id")
        if section in seen_ids:
            raise ContractError(f"{item_path}.id is duplicated")
        seen_ids.add(section)
        order = definition["order"]
        if isinstance(order, bool) or not isinstance(order, int) or order < 1:
            raise ContractError(f"{item_path}.order must be a positive integer")
        orders.append(order)
        ids.append(section)
        safe_text(definition["title"], f"{item_path}.title")
        safe_text(definition["editorial_hint"], f"{item_path}.editorial_hint")
        minimum = definition["minimum_candidates"]
        if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 0:
            raise ContractError(f"{item_path}.minimum_candidates must be a non-negative integer")
        limit = definition["selection_limit"]
        if not isinstance(limit, Mapping) or set(limit) != {"min", "max"}:
            raise ContractError(f"{item_path}.selection_limit must contain min and max")
        limit_min = limit["min"]
        limit_max = limit["max"]
        if (
            isinstance(limit_min, bool)
            or not isinstance(limit_min, int)
            or isinstance(limit_max, bool)
            or not isinstance(limit_max, int)
            or limit_min < 0
            or limit_max < limit_min
        ):
            raise ContractError(f"{item_path}.selection_limit must satisfy 0 <= min <= max")
    if orders != list(range(1, len(orders) + 1)):
        raise ContractError(f"{path}.order must be a unique contiguous sequence starting at 1")
    return tuple(ids)


def _validate_noon(value: Mapping[str, Any], section_ids: Sequence[str] | None = None) -> None:
    _only_keys(
        value,
        {"schema_version", "report", "report_date", "generated_at", "top_points", "sections"},
        "resolved",
    )
    _required(value, {"schema_version", "report", "report_date", "generated_at", "top_points", "sections"}, "resolved")
    if value["schema_version"] != SCHEMA_VERSION:
        raise ContractError("resolved.schema_version must be 2")
    if value["report"] != NOON_REPORT:
        raise ContractError("resolved.report must be noon-news")
    date(value["report_date"], "resolved.report_date")
    timestamp(value["generated_at"], "resolved.generated_at")
    points = _require_list(value["top_points"], "resolved.top_points")
    if len(points) > 5:
        raise ContractError("resolved.top_points must contain at most five items")
    seen_points: set[str] = set()
    for index, point_value in enumerate(points):
        path = f"resolved.top_points[{index}]"
        point = _require_mapping(point_value, path)
        _only_keys(point, {"candidate_id", "topic", "fact"}, path)
        _required(point, {"candidate_id", "topic", "fact"}, path)
        cid = candidate_id(point["candidate_id"], f"{path}.candidate_id")
        if cid in seen_points:
            raise ContractError(f"{path}.candidate_id is reused")
        seen_points.add(cid)
        noon_top_point_topic(point["topic"], f"{path}.topic")
        top_point_fact(point["fact"], f"{path}.fact")
    sections = _require_mapping(value["sections"], "resolved.sections")
    if section_ids is None:
        section_ids = tuple(section_id(key, f"resolved.sections key {key!r}") for key in sections)
    else:
        section_ids = tuple(section_id(item, "resolved section ID") for item in section_ids)
    if not section_ids or set(sections) != set(section_ids):
        raise ContractError("resolved.sections must match the configured noon sections")
    seen_details: set[str] = set()
    selected: set[str] = set()
    for current_section_id in section_ids:
        items = _require_list(sections[current_section_id], f"resolved.sections.{current_section_id}")
        for index, detail in enumerate(items):
            path = f"resolved.sections.{current_section_id}[{index}]"
            _validate_noon_detail(detail, path)
            cid = detail["candidate_id"]
            if cid in seen_details:
                raise ContractError(f"candidate_id {cid!r} is reused across details")
            seen_details.add(cid)
            selected.add(cid)
    if not seen_points.issubset(selected):
        raise ContractError("top_points must reference selected details")


def _validate_project(
    value: Any,
    path: str,
    *,
    require_fresh: bool = True,
    require_category: bool = False,
) -> None:
    project = _require_mapping(value, path)
    allowed = {"name", "url", "description", "stars_today", "is_fresh_hot", "category"}
    _only_keys(project, allowed, path)
    required = {"name", "url", "description", "stars_today"}
    if require_fresh:
        required.add("is_fresh_hot")
    if require_category:
        required.add("category")
    _required(project, required, path)
    safe_text(project["name"], f"{path}.name")
    url(project["url"], f"{path}.url")
    safe_text(project["description"], f"{path}.description", allow_empty=True)
    finite_number(project["stars_today"], f"{path}.stars_today")
    if not isinstance(project["stars_today"], int):
        raise ContractError(f"{path}.stars_today must be an integer")
    if require_fresh and not isinstance(project["is_fresh_hot"], bool):
        raise ContractError(f"{path}.is_fresh_hot must be boolean")
    if "category" in project:
        safe_text(project["category"], f"{path}.category")


def validate_codex_markdown(
    value: Any,
    path: str = "codexradar.markdown",
    *,
    expected_title: str = "CodexRadar 智力效率",
) -> None:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{path} must be a non-empty string")
    safe_text(expected_title, f"{path}.expected_title")
    if not value.startswith(f"**🧠 {expected_title}**"):
        raise ContractError(f"{path} has an invalid CodexRadar heading")
    if "\x00" in value or "\r" in value:
        raise ContractError(f"{path} contains unsafe control content")
    lines = value.splitlines()
    if len(lines) < 2:
        raise ContractError(f"{path} is missing its body")
    # The block belongs to the producer; validate only shape, never re-render it.
    if not any(line.lstrip().startswith("-") for line in lines[1:]):
        raise ContractError(f"{path} has no metric rows")


def _validate_agents(value: Mapping[str, Any]) -> None:
    _only_keys(value, {"schema_version", "report", "date", "sections"}, "resolved")
    _required(value, {"schema_version", "report", "date", "sections"}, "resolved")
    if value["schema_version"] != SCHEMA_VERSION:
        raise ContractError("resolved.schema_version must be 2")
    if value["report"] != AGENTS_REPORT:
        raise ContractError("resolved.report must be agents-report")
    date(value["date"], "resolved.date")
    sections = _require_mapping(value["sections"], "resolved.sections")
    if set(sections) != set(_LEGACY_AGENTS_SECTION_IDS):
        raise ContractError("resolved.sections must contain exactly the current agents sections")
    ai_items = _require_list(sections["ai_ecosystem"], "resolved.sections.ai_ecosystem")
    seen: set[str] = set()
    for index, item_value in enumerate(ai_items):
        path = f"resolved.sections.ai_ecosystem[{index}]"
        item = _require_mapping(item_value, path)
        _only_keys(item, {"candidate_ids", "topic", "summary", "provenance"}, path)
        _required(item, {"candidate_ids", "topic", "summary", "provenance"}, path)
        ids = candidate_ids(item["candidate_ids"], f"{path}.candidate_ids", max_count=3)
        reused = set(ids) & seen
        if reused:
            raise ContractError(f"{path}.candidate_ids reuses {sorted(reused)!r}")
        seen.update(ids)
        ecosystem_topic(item["topic"], f"{path}.topic")
        safe_text(item["summary"], f"{path}.summary")
        validate_provenance(item["provenance"], f"{path}.provenance")
    codex = _require_mapping(sections["codexradar"], "resolved.sections.codexradar")
    _only_keys(codex, {"markdown"}, "resolved.sections.codexradar")
    _required(codex, {"markdown"}, "resolved.sections.codexradar")
    validate_codex_markdown(codex["markdown"])
    source = _require_mapping(sections["open_source"], "resolved.sections.open_source")
    _only_keys(source, {"trends", "fresh_hot", "categories", "quality"}, "resolved.sections.open_source")
    _required(source, {"trends", "fresh_hot", "categories", "quality"}, "resolved.sections.open_source")
    trends = _require_list(source["trends"], "resolved.sections.open_source.trends")
    if len(trends) != 2:
        raise ContractError("resolved open-source trends must contain exactly two items")
    for index, trend in enumerate(trends):
        safe_text(trend, f"resolved.sections.open_source.trends[{index}]")
    fresh = _require_list(source["fresh_hot"], "resolved.sections.open_source.fresh_hot")
    for index, project in enumerate(fresh):
        _validate_project(
            project,
            f"resolved.sections.open_source.fresh_hot[{index}]",
            require_category=True,
        )
    categories = _require_list(source["categories"], "resolved.sections.open_source.categories")
    for index, category_value in enumerate(categories):
        path = f"resolved.sections.open_source.categories[{index}]"
        category = _require_mapping(category_value, path)
        _only_keys(category, {"title", "projects"}, path)
        _required(category, {"title", "projects"}, path)
        safe_text(category["title"], f"{path}.title")
        projects = _require_list(category["projects"], f"{path}.projects")
        if len(projects) > 3:
            raise ContractError(f"{path}.projects must contain at most three items")
        for project_index, project in enumerate(projects):
            _validate_project(project, f"{path}.projects[{project_index}]")
    quality = _require_mapping(source["quality"], "resolved.sections.open_source.quality")
    if quality.get("ok") is not True:
        raise ContractError("resolved.sections.open_source.quality.ok must be true")


def _validate_agents_plan(value: Mapping[str, Any], report_plan: Mapping[str, Any]) -> None:
    """Validate the shared resolved envelope using kind-specific block contracts."""
    from . import profiles

    profiles.validate_report_plan(report_plan, AGENTS_REPORT)
    _only_keys(
        value,
        {"schema_version", "report", "report_date", "generated_at", "sections"},
        "resolved",
    )
    _required(
        value,
        {"schema_version", "report", "report_date", "generated_at", "sections"},
        "resolved",
    )
    if value["schema_version"] != SCHEMA_VERSION:
        raise ContractError("resolved.schema_version must be 2")
    if value["report"] != AGENTS_REPORT:
        raise ContractError("resolved.report must be agents-report")
    date(value["report_date"], "resolved.report_date")
    timestamp(value["generated_at"], "resolved.generated_at")
    sections = _require_mapping(value["sections"], "resolved.sections")
    components = report_plan["components"]
    component_ids = [component["id"] for component in components]
    if list(sections) != component_ids:
        raise ContractError("resolved.sections must match Report Plan component order")

    for component in components:
        component_id = component["id"]
        kind = component["kind"]
        path = f"resolved.sections.{component_id}"
        section = sections[component_id]
        if kind == "semantic_clusters":
            items = _require_list(section, path)
            maximum = component["policy"]["max_items"]
            if len(items) > maximum:
                raise ContractError(f"{path} must contain at most {maximum} items")
            seen: set[str] = set()
            for index, item_value in enumerate(items):
                item_path = f"{path}[{index}]"
                item = _require_mapping(item_value, item_path)
                _only_keys(item, {"candidate_ids", "topic", "summary", "provenance"}, item_path)
                _required(item, {"candidate_ids", "topic", "summary", "provenance"}, item_path)
                ids = candidate_ids(
                    item["candidate_ids"],
                    f"{item_path}.candidate_ids",
                    max_count=component["policy"]["max_candidates_per_item"],
                )
                reused = set(ids) & seen
                if reused:
                    raise ContractError(f"{item_path}.candidate_ids reuses {sorted(reused)!r}")
                seen.update(ids)
                ecosystem_topic(item["topic"], f"{item_path}.topic")
                safe_text(item["summary"], f"{item_path}.summary")
                validate_provenance(item["provenance"], f"{item_path}.provenance")
        elif kind == "producer_markdown":
            block = _require_mapping(section, path)
            _only_keys(block, {"markdown"}, path)
            _required(block, {"markdown"}, path)
            validate_codex_markdown(
                block["markdown"],
                f"{path}.markdown",
                expected_title=component["title"],
            )
        elif kind == "semantic_synthesis":
            trends = _require_list(section, path)
            exact = component["policy"]["exact_items"]
            if len(trends) != exact:
                raise ContractError(f"{path} must contain exactly {exact} items")
            for index, trend in enumerate(trends):
                safe_text(trend, f"{path}[{index}]")
        elif kind == "project_board":
            board = _require_mapping(section, path)
            _only_keys(board, {"fresh_hot", "categories", "quality"}, path)
            _required(board, {"fresh_hot", "categories", "quality"}, path)
            fresh = _require_list(board["fresh_hot"], f"{path}.fresh_hot")
            for index, project in enumerate(fresh):
                _validate_project(
                    project,
                    f"{path}.fresh_hot[{index}]",
                    require_category=True,
                )
            categories = _require_list(board["categories"], f"{path}.categories")
            maximum = component["policy"]["max_projects_per_category"]
            for index, category_value in enumerate(categories):
                category_path = f"{path}.categories[{index}]"
                category = _require_mapping(category_value, category_path)
                _only_keys(category, {"title", "projects"}, category_path)
                _required(category, {"title", "projects"}, category_path)
                safe_text(category["title"], f"{category_path}.title")
                projects = _require_list(category["projects"], f"{category_path}.projects")
                if len(projects) > maximum:
                    raise ContractError(f"{category_path}.projects must contain at most {maximum} items")
                for project_index, project in enumerate(projects):
                    _validate_project(project, f"{category_path}.projects[{project_index}]")
            quality = _require_mapping(board["quality"], f"{path}.quality")
            if quality.get("ok") is not True:
                raise ContractError(f"{path}.quality.ok must be true")
        else:
            raise ContractError(f"{path} uses unsupported block kind {kind!r}")


def validate_resolved(
    value: Any,
    *,
    noon_section_ids: Sequence[str] | None = None,
    report_plan: Mapping[str, Any] | None = None,
) -> None:
    """Validate one current resolved report; return ``None`` on success."""
    report = _require_mapping(value, "resolved")
    if report.get("semantic_protocol") is not None:
        raise ContractError("semantic_protocol is not part of the current resolved schema")
    report_id = report.get("report")
    if report_id == NOON_REPORT:
        if report_plan is not None:
            from . import profiles

            profiles.validate_report_plan(report_plan, NOON_REPORT)
            noon_section_ids = tuple(component["id"] for component in report_plan["components"])
        _validate_noon(report, noon_section_ids)
    elif report_id == AGENTS_REPORT:
        if report_plan is None:
            _validate_agents(report)
        else:
            _validate_agents_plan(report, report_plan)
    else:
        raise ContractError("resolved.report is unsupported")


def reject_legacy_model_keys(value: Any, path: str = "model") -> None:
    """Reject removed protocol names while permitting harmless model extras."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in LEGACY_KEYS:
                raise ContractError(f"{path}.{key} is not part of the current model contract")
            reject_legacy_model_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_legacy_model_keys(child, f"{path}[{index}]")


def validate_registry_url(url_value: str, registry_urls: set[str], path: str) -> None:
    checked = url(url_value, path)
    if checked not in registry_urls:
        raise ContractError(f"{path} is not present in the candidate registry")
