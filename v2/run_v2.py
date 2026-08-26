"""Single CLI for the minimal independent glance_brief V2 pipeline."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPORTS = ("noon-news", "agents-report")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_NOON_SECTIONS = ("international", "domestic", "business", "ai")
_TOPIC_RE = re.compile(
    r"^(?:AI|(?=[A-Za-z0-9\u3400-\u4dbf\u4e00-\u9fff]{2,8}\Z)"
    r"(?=.*[\u3400-\u4dbf\u4e00-\u9fff])[A-Za-z0-9\u3400-\u4dbf\u4e00-\u9fff]+)\Z"
)
# Kept for parsing older offline fixtures. New noon-news model calls use the
# lean contract below and do not need to echo a protocol or report identifier.
NOON_LEGACY_MODEL_PROTOCOL = "glance_brief.noon-news.model.v2"
# Backward-compatible public name used by older fixtures and callers.
NOON_MODEL_PROTOCOL = NOON_LEGACY_MODEL_PROTOCOL
NOON_SEMANTIC_PROTOCOL = "glance_brief.noon-news.v2"
_EVIDENCE_LEVELS = frozenset({"direct", "attributed", "uncertain"})
_NUMBER_RE = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)?%?")
_MONTHS = {
    name: index
    for index, name in enumerate(
        (
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
        ),
        start=1,
    )
}
_MONTH_ABBREVIATIONS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _core():
    return _load_module("glance_brief_v2_core", HERE / "brief_v2.py")


def assemble(config_path: Path, report: str) -> dict[str, Any]:
    config = _load_json(config_path)
    return _core().assemble_report(config, report, config_path.parent)


def parse_model_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"model response was not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("model response root must be an object")
    return value


def _model_extra(value: Any, key: str = "") -> Any:
    lowered = key.casefold()
    if any(marker in lowered for marker in ("url", "link", "permalink")):
        return None
    if isinstance(value, Mapping):
        return {
            name: cleaned
            for name, child in value.items()
            if (cleaned := _model_extra(child, str(name))) is not None
        }
    if isinstance(value, list):
        return [cleaned for child in value if (cleaned := _model_extra(child)) is not None]
    if isinstance(value, str) and value.strip().lower().startswith(("http://", "https://")):
        return None
    return value


def _model_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    view = {
        "candidate_id": candidate.get("candidate_id"),
        "title": candidate.get("title") or "",
        "text": candidate.get("text") or "",
    }
    if candidate.get("published_at"):
        view["published_at"] = candidate["published_at"]
    extra = _model_extra(candidate.get("extra", {}))
    if extra:
        view["extra"] = extra
    return view


def build_model_payload(assembled: Mapping[str, Any]) -> dict[str, Any]:
    """Expose only semantic evidence; deterministic metadata never reaches the model."""
    report = assembled.get("report")
    sections = assembled.get("sections")
    if report not in REPORTS or not isinstance(sections, Mapping):
        raise ValueError("assembled payload is invalid")
    if report == "noon-news":
        selected = {
            section_id: [_model_candidate(item) for item in sections.get(section_id, [])]
            for section_id in ("international", "domestic", "business", "ai")
        }
    else:
        selected = {
            "ai_ecosystem": [
                _model_candidate(item) for item in sections.get("ai_ecosystem", [])
            ]
        }
    if report == "noon-news":
        # The prompt owns the editorial rules. Do not repeat them in the data
        # payload: the model only needs the four evidence pools.
        return {"sections": selected}
    return {"report": report, "sections": selected}


def build_model_prompt(contract: str, payload: Mapping[str, Any]) -> str:
    if not isinstance(contract, str) or not contract.strip():
        raise ValueError("prompt contract must be non-empty")
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    prefix = contract.rstrip()
    if prefix.endswith("## 候选数据"):
        return f"{prefix}\n{encoded}\n"
    return f"{prefix}\n\n## 候选数据\n{encoded}\n"


def _candidate_index(assembled: Mapping[str, Any]) -> tuple[dict[str, Mapping[str, Any]], dict[str, str]]:
    by_id: dict[str, Mapping[str, Any]] = {}
    section_by_id: dict[str, str] = {}
    sections = assembled.get("sections", {})
    if not isinstance(sections, Mapping):
        raise ValueError("assembled sections must be an object")
    for section_id, candidates in sections.items():
        if not isinstance(candidates, list):
            raise ValueError(f"assembled section {section_id} must be an array")
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                raise ValueError("assembled candidate must be an object")
            candidate_id = candidate.get("candidate_id")
            if not isinstance(candidate_id, str) or candidate_id in by_id:
                raise ValueError("assembled candidate IDs must be unique strings")
            by_id[candidate_id] = candidate
            section_by_id[candidate_id] = str(section_id)
    return by_id, section_by_id


def _object(value: Any, path: str, allowed: set[str], required: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be an object")
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown:
        raise ValueError(f"{path} has unknown fields: {sorted(unknown)!r}")
    if missing:
        raise ValueError(f"{path} is missing fields: {sorted(missing)!r}")
    return value


def _required_object(value: Any, path: str, required: set[str]) -> Mapping[str, Any]:
    """Validate only the fields the lean contract actually consumes."""
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be an object")
    missing = required - set(value)
    if missing:
        raise ValueError(f"{path} is missing fields: {sorted(missing)!r}")
    return value


def _text(value: Any, path: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise ValueError(f"{path} must be a non-empty string")
    return " ".join(value.split())


def _summary(value: Any, path: str, *, limit: int = 140) -> str:
    text = _text(value, path)
    if len(text) > limit:
        raise ValueError(f"{path} must contain at most {limit} characters")
    return text


def _bounded_text(value: Any, path: str, *, limit: int) -> str:
    text = _text(value, path)
    if len(text) > limit:
        raise ValueError(f"{path} must contain at most {limit} characters")
    return text


def _topic(value: Any, path: str) -> str:
    text = _text(value, path)
    if not _TOPIC_RE.fullmatch(text):
        raise ValueError(f"{path} must be AI or a compact 2 to 8 character Chinese/mixed label")
    return text


def _top_fact(value: Any, path: str) -> str:
    # Keep points compact for the rendered list without imposing the old,
    # arbitrary 40-character ceiling on otherwise valid facts.
    text = _bounded_text(value, path, limit=60)
    if "http://" in text or "https://" in text or "来源" in text:
        raise ValueError(f"{path} must be a source-free fact")
    return text


def _check_top_point_anchor(value: str, supporting_text: str, path: str) -> None:
    """Reject a top-point fact that appears to reference a different detail."""

    latin_stop = {
        "about", "after", "from", "into", "latest", "model",
        "news", "report", "says", "the", "with",
    }

    def anchors(text: str) -> tuple[set[str], set[str]]:
        lowered = text.casefold()
        latin = {
            token
            for token in re.findall(r"[a-z][a-z0-9._+-]{2,}", lowered)
            if token not in latin_stop
        }
        cjk_bigrams: set[str] = set()
        for run in re.findall(r"[\u3400-\u9fff]+", text):
            cjk_bigrams.update(run[index : index + 2] for index in range(len(run) - 1))
        return latin, cjk_bigrams

    fact_latin, fact_cjk = anchors(value)
    support_latin, support_cjk = anchors(supporting_text)
    if fact_latin.intersection(support_latin):
        return
    if len(fact_cjk.intersection(support_cjk)) >= 2:
        return
    # Very short or symbol-only facts do not carry enough lexical material for
    # this guard; candidate-ID and numeric checks still apply to them.
    if not fact_latin and len(fact_cjk) < 2:
        return
    raise ValueError(f"{path} does not match referenced detail")


def _iso_datetime(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be an ISO-8601 timestamp")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{path} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{path} must include a timezone")
    return text


def _report_date(value: str | None, generated_at: str) -> str:
    if value is not None:
        if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
            raise ValueError("noon-news report_date must use YYYY-MM-DD format")
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("noon-news report_date is invalid") from exc
        return value
    return generated_at[:10]


def _model_ref(value: Any, path: str) -> str:
    text = _text(value, path)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", text):
        raise ValueError(f"{path} must be a short semantic item reference")
    return text


def _optional_bounded_text(value: Any, path: str, *, limit: int) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return ""
    return _bounded_text(value, path, limit=limit)


def _evidence_text(candidates: Sequence[Mapping[str, Any]]) -> str:
    values: list[str] = []
    for candidate in candidates:
        for key in ("title", "text", "publisher", "published_at"):
            value = candidate.get(key)
            if value is not None:
                values.append(str(value))
        extra = candidate.get("extra")
        if extra is not None:
            values.append(json.dumps(extra, ensure_ascii=False, sort_keys=True))
    return " ".join(values)


def _number_key(value: str) -> str:
    return value.replace(",", "").replace("，", "")


def _number_keys(value: str) -> set[str]:
    keys: set[str] = set()
    for match in _NUMBER_RE.finditer(value):
        raw = match.group(0)
        number = _number_key(raw)
        suffix = re.match(r"\s*([万亿])", value[match.end() :])
        if suffix and not raw.endswith("%"):
            multiplier = {"万": 10_000, "亿": 100_000_000}[suffix.group(1)]
            keys.add(str(int(float(number) * multiplier)))
        else:
            keys.add(number)
    keys.update(
        _number_key(match.group(0))
        for match in re.finditer(r"\d{1,3}(?:[,，]\d{3})+", value)
    )
    lowered = value.casefold()
    for match in re.finditer(r"(?<![a-z])(\d+(?:\.\d+)?)\s*(?:percent|per\s+cent)\b", lowered):
        keys.add(f"{_number_key(match.group(1))}%")
    scale_by_suffix = {
        "k": 1_000,
        "kn": 1_000,
        "m": 1_000_000,
        "mn": 1_000_000,
        "b": 1_000_000_000,
        "bn": 1_000_000_000,
        "t": 1_000_000_000_000,
        "tn": 1_000_000_000_000,
    }
    for match in re.finditer(
        r"(?<![a-z])(\d+(?:\.\d+)?)\s*(kn|mn|bn|tn|[kmbt])(?![a-z])",
        lowered,
    ):
        keys.add(str(int(float(match.group(1)) * scale_by_suffix[match.group(2)])))
    scale_by_word = {"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000, "trillion": 1_000_000_000_000}
    for match in re.finditer(
        r"(?<![a-z])(\d+(?:\.\d+)?)\s*(thousand|million|billion|trillion)\b",
        lowered,
    ):
        keys.add(str(int(float(match.group(1)) * scale_by_word[match.group(2)])))
    for month, month_number in _MONTHS.items():
        if re.search(rf"\b{month}\b", lowered):
            keys.add(str(month_number))
        for match in re.finditer(rf"(\d{{1,2}})\s+{month}", lowered):
            keys.update({str(int(match.group(1))), str(month_number)})
        for match in re.finditer(rf"{month}\s+(\d{{1,2}})", lowered):
            keys.update({str(int(match.group(1))), str(month_number)})
    for month, month_number in _MONTH_ABBREVIATIONS.items():
        token = rf"\b{month}\.?(?=\s|,|$)"
        if re.search(token, lowered):
            keys.add(str(month_number))
        for match in re.finditer(rf"(\d{{1,2}})\s+{token}", lowered):
            keys.update({str(int(match.group(1))), str(month_number)})
        for match in re.finditer(rf"{token}\s+(\d{{1,2}})", lowered):
            keys.update({str(int(match.group(1))), str(month_number)})
    for match in re.finditer(r"(\d{1,2})月\s*(\d{1,2})日?", value):
        keys.update({str(int(match.group(1))), str(int(match.group(2)))})
    for month_number in range(1, 13):
        if f"{month_number}月" in value:
            keys.add(str(month_number))
    # Treat common English and Chinese decade notations as equivalent without
    # weakening the check for genuinely different decades. For example,
    # evidence containing "1990s" supports "上世纪90年代", but not "80年代".
    for match in re.finditer(r"\b((?:19|20)\d{2})s\b", lowered):
        keys.add(str(int(match.group(1)) % 100))
    for match in re.finditer(r"上世纪\s*(\d{2})\s*年代", value):
        keys.add(str(1900 + int(match.group(1))))
    for match in re.finditer(r"本世纪\s*(\d{2})\s*年代", value):
        keys.add(str(2000 + int(match.group(1))))
    for unit, multiplier in {"万": 10_000, "亿": 100_000_000}.items():
        for match in re.finditer(rf"(\d+(?:\.\d+)?)\s*{unit}", value):
            keys.add(str(int(float(match.group(1)) * multiplier)))
    return keys


def _check_supported_numbers(value: str, path: str, candidates: Sequence[Mapping[str, Any]]) -> None:
    evidence_numbers = _number_keys(_evidence_text(candidates))
    unsupported = sorted(_number_keys(value) - evidence_numbers)
    if unsupported:
        raise ValueError(f"{path} contains unsupported numeric claim(s): {', '.join(unsupported)}")


def _item_id(section_id: str, candidate_ids: Sequence[str]) -> str:
    payload = json.dumps([section_id, list(candidate_ids)], ensure_ascii=False, separators=(",", ":"))
    return "i" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ids(value: Any, path: str, by_id: Mapping[str, Any], allowed_sections: set[str], section_by_id: Mapping[str, str]) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{path} must be a non-empty array")
    result: list[str] = []
    for index, candidate_id in enumerate(value):
        if not isinstance(candidate_id, str) or candidate_id not in by_id:
            raise ValueError(f"unknown candidate_id at {path}[{index}]: {candidate_id!r}")
        if section_by_id[candidate_id] not in allowed_sections:
            raise ValueError(f"candidate_id {candidate_id!r} is not allowed in {path}")
        if candidate_id not in result:
            result.append(candidate_id)
    return result


def _sources(candidates: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        for value in candidate.get("provenance", []):
            if not isinstance(value, Mapping):
                continue
            url = value.get("url")
            label = value.get("label")
            if not isinstance(url, str) or not url or not isinstance(label, str) or not label:
                continue
            key = (str(value.get("source_id", "")), url)
            if key in seen:
                continue
            seen.add(key)
            result.append({
                name: value[name]
                for name in ("source_id", "label", "publisher", "url")
                if name in value and value[name] not in (None, "")
            })
    if not result:
        raise ValueError("selected candidates do not contain a usable source URL")
    return result


def _date(value: str | None) -> str:
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        raise ValueError("agents-report requires --date in YYYY-MM-DD form")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("agents-report date is invalid") from exc
    return value


def _metric_sections(candidates: list[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups = {name: [] for name in ("intelligence_top2", "balanced_top2", "value_top3", "other")}
    for candidate in candidates:
        extra = candidate.get("extra", {})
        if not isinstance(extra, Mapping):
            continue
        ranking = extra.get("ranking")
        rankings = ranking if isinstance(ranking, list) else [ranking]
        metric = {
            "model": candidate.get("title"),
            "effort": extra.get("effort"),
            "iq": extra.get("iq"),
            "minutes": extra.get("average_minutes"),
            "price_usd": extra.get("average_price_usd"),
        }
        if any(value is None for value in metric.values()):
            continue
        for group in rankings:
            if group in groups:
                groups[group].append(dict(metric))
    return groups


def _open_source(candidates: list[Mapping[str, Any]]) -> dict[str, Any]:
    trends = [
        candidate.get("text")
        for candidate in candidates
        if candidate.get("extra", {}).get("kind") == "trend"
        and isinstance(candidate.get("text"), str)
        and candidate.get("text")
    ]
    if len(trends) != 2:
        raise ValueError("open-source evidence must contain exactly two trends")
    grouped: OrderedDict[str, list[Mapping[str, Any]]] = OrderedDict()
    for candidate in candidates:
        extra = candidate.get("extra", {})
        if not isinstance(extra, Mapping):
            continue
        if extra.get("kind") != "project":
            continue
        category = extra.get("category")
        if not isinstance(category, str) or not category:
            category = "其他"
        grouped.setdefault(category, []).append(candidate)
    categories = []
    for name, projects in grouped.items():
        hot_index = next(
            (
                index
                for index, value in enumerate(projects)
                if value.get("extra", {}).get("role") == "hot"
            ),
            None,
        )

        def project(value: Mapping[str, Any]) -> dict[str, Any]:
            name_value = value.get("title")
            url = value.get("url")
            if not isinstance(name_value, str) or not name_value or not isinstance(url, str) or not url:
                raise ValueError("open-source candidate needs name and URL")
            result: dict[str, Any] = {"name": name_value, "url": url}
            if isinstance(value.get("text"), str) and value["text"]:
                result["description"] = value["text"]
            stars_today = value.get("extra", {}).get("stars_today")
            if stars_today is not None:
                if isinstance(stars_today, bool) or not isinstance(stars_today, int) or stars_today <= 0:
                    raise ValueError("open-source stars_today must be a positive integer")
                result["stars_today"] = stars_today
            return result

        hot_projects = [project(projects[hot_index])] if hot_index is not None else []
        other_projects = [
            project(value)
            for index, value in enumerate(projects)
            if index != hot_index
        ][:4]
        categories.append(
            {
                "name": name,
                "hot_projects": hot_projects,
                "other_projects": other_projects,
            }
        )
    return {"trends": trends, "categories": categories}


def _resolve_lean_noon(
    assembled: Mapping[str, Any],
    model: Mapping[str, Any],
    report_date: str | None,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Resolve the low-burden noon contract.

    The model selects one candidate per detail. The program creates stable item
    IDs and resolves top-point references, so the model never has to maintain a
    second ID namespace or merge unrelated candidates.
    """

    by_id, section_by_id = _candidate_index(assembled)
    root = _required_object(model, "model", {"top_points", "sections"})
    model_sections = _required_object(
        root["sections"],
        "sections",
        set(_NOON_SECTIONS),
    )
    section_limits = {"international": 5, "domestic": 2, "business": 3, "ai": 4}
    # `topic` is harmless and occasionally emitted by models; it is ignored
    # because program-side rendering does not use a per-detail topic.
    resolved_sections: dict[str, list[dict[str, Any]]] = {}
    used_candidates: set[str] = set()
    candidate_to_item: dict[str, str] = {}
    item_support_text: dict[str, str] = {}

    for section_id in _NOON_SECTIONS:
        values = model_sections[section_id]
        if not isinstance(values, list):
            raise ValueError(f"sections.{section_id} must be an array")
        output: list[dict[str, Any]] = []
        for index, value in enumerate(values[: section_limits[section_id]]):
            path = f"sections.{section_id}[{index}]"
            item = _required_object(value, path, {"candidate_id", "summary"})
            candidate_id = item["candidate_id"]
            if not isinstance(candidate_id, str) or not candidate_id:
                raise ValueError(f"{path}.candidate_id must be a single candidate ID string")
            if candidate_id not in by_id:
                raise ValueError(f"unknown candidate_id at {path}.candidate_id: {candidate_id!r}")
            if section_by_id[candidate_id] not in _NOON_SECTIONS:
                raise ValueError(f"candidate_id {candidate_id!r} is not allowed in {path}")
            if candidate_id in used_candidates:
                raise ValueError(f"candidate IDs reused across details: {[candidate_id]!r}")
            used_candidates.add(candidate_id)

            candidate = by_id[candidate_id]
            title = candidate.get("title")
            if not isinstance(title, str) or not title:
                raise ValueError(f"{path} candidate has no title")
            summary = _text(item["summary"], f"{path}.summary")
            _check_supported_numbers(summary, f"{path}.summary numeric claim", [candidate])
            headline_value = item.get("headline_zh")
            headline_zh = "" if headline_value is None or headline_value == "" else _text(
                headline_value, f"{path}.headline_zh"
            )
            item_id = _item_id(section_id, [candidate_id])
            candidate_to_item[candidate_id] = item_id
            item_support_text[item_id] = " ".join(
                value for value in (title, headline_zh, summary, _evidence_text([candidate])) if value
            )
            resolved = {
                "item_id": item_id,
                "candidate_ids": [candidate_id],
                "headline": title,
                "headline_zh": headline_zh,
                "summary": summary,
                "sources": _sources([candidate]),
                "published_at": candidate.get("published_at"),
            }
            output.append(resolved)
        resolved_sections[section_id] = output

    point_values = root["top_points"]
    if not isinstance(point_values, list):
        raise ValueError("top_points must be an array")
    points: list[dict[str, Any]] = []
    used_point_items: set[str] = set()
    for index, value in enumerate(point_values[:5]):
        path = f"top_points[{index}]"
        item = _required_object(value, path, {"candidate_id", "topic", "fact"})
        candidate_id = item["candidate_id"]
        if not isinstance(candidate_id, str) or not candidate_id:
            continue
        item_id = candidate_to_item.get(candidate_id)
        if item_id is None:
            continue
        if item_id in used_point_items:
            continue
        used_point_items.add(item_id)
        topic = _text(item["topic"], f"{path}.topic")
        fact = _text(item["fact"], f"{path}.fact")
        points.append({"item_ids": [item_id], "topic": topic, "fact": fact})

    generated = _iso_datetime(generated_at or _now_utc(), "generated_at")
    return {
        "semantic_protocol": NOON_SEMANTIC_PROTOCOL,
        "report": "noon-news",
        "report_date": _report_date(report_date, generated),
        "generated_at": generated,
        "top_points": points,
        "sections": resolved_sections,
    }


def resolve_semantic(
    assembled: Mapping[str, Any],
    model: Mapping[str, Any],
    report_date: str | None,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    report = assembled.get("report")
    model_report = model.get("report")
    if model_report is not None and model_report != report:
        raise ValueError("model report id does not match assembled report")
    by_id, section_by_id = _candidate_index(assembled)
    sections = assembled["sections"]
    if report == "noon-news":
        if model_report is None and "protocol" not in model:
            return _resolve_lean_noon(assembled, model, report_date, generated_at=generated_at)
        strict_protocol = model.get("protocol") == NOON_MODEL_PROTOCOL
        allowed_root = {"protocol", "report", "top_points", "sections"}
        required_root = {"report", "top_points", "sections"}
        if strict_protocol:
            required_root.add("protocol")
        root = _object(model, "model", allowed_root, required_root)
        model_sections = _object(
            root["sections"],
            "sections",
            set(_NOON_SECTIONS),
            set(_NOON_SECTIONS),
        )
        resolved_sections: dict[str, list[dict[str, Any]]] = {}
        used: set[str] = set()
        item_refs: dict[str, str] = {}
        item_candidates: dict[str, list[Mapping[str, Any]]] = {}
        item_support_text: dict[str, str] = {}
        section_limits = {"international": 5, "domestic": 2, "business": 3, "ai": 4}
        detail_keys = {
            "candidate_ids",
            "summary",
            "item_ref",
            "headline_zh",
            "why_it_matters",
            "evidence_level",
        }
        for section_id in _NOON_SECTIONS:
            values = model_sections[section_id]
            if not isinstance(values, list):
                raise ValueError(f"sections.{section_id} must be an array")
            output: list[dict[str, Any]] = []
            # Detail arrays are importance-ordered by contract. Apply the hard
            # display cap deterministically so a small model overage does not
            # invalidate an otherwise usable report.
            for index, value in enumerate(values[: section_limits[section_id]]):
                path = f"sections.{section_id}[{index}]"
                required = {"candidate_ids", "summary"}
                if strict_protocol:
                    required.update({"item_ref", "why_it_matters", "evidence_level"})
                item = _object(value, path, detail_keys, required)
                candidate_ids = _ids(
                    item["candidate_ids"],
                    f"{path}.candidate_ids",
                    by_id,
                    set(_NOON_SECTIONS),
                    section_by_id,
                )
                duplicate = used.intersection(candidate_ids)
                if duplicate:
                    raise ValueError(f"candidate IDs reused across details: {sorted(duplicate)!r}")
                used.update(candidate_ids)
                candidates = [by_id[candidate_id] for candidate_id in candidate_ids]
                title = candidates[0].get("title")
                if not isinstance(title, str) or not title:
                    raise ValueError(f"{path} first candidate has no title")
                summary = _summary(item["summary"], f"{path}.summary")
                _check_supported_numbers(summary, f"{path}.summary", candidates)
                if strict_protocol:
                    item_ref = _model_ref(item["item_ref"], f"{path}.item_ref")
                    if item_ref in item_refs:
                        raise ValueError(f"duplicate semantic item_ref: {item_ref!r}")
                    headline_zh = _optional_bounded_text(
                        item.get("headline_zh"), f"{path}.headline_zh", limit=30
                    )
                    why_it_matters = _bounded_text(
                        item["why_it_matters"], f"{path}.why_it_matters", limit=120
                    )
                    _check_supported_numbers(
                        why_it_matters, f"{path}.why_it_matters", candidates
                    )
                    evidence_level = item["evidence_level"]
                    if evidence_level not in _EVIDENCE_LEVELS:
                        raise ValueError(
                            f"{path}.evidence_level must be one of {sorted(_EVIDENCE_LEVELS)!r}"
                        )
                else:
                    item_ref = f"legacy-{section_id}-{index}"
                    headline_zh = _optional_bounded_text(
                        item.get("headline_zh"), f"{path}.headline_zh", limit=30
                    )
                    why_it_matters = _optional_bounded_text(
                        item.get("why_it_matters"), f"{path}.why_it_matters", limit=120
                    )
                    evidence_level = item.get("evidence_level", "direct")
                item_id = _item_id(section_id, candidate_ids)
                item_refs[item_ref] = item_id
                item_candidates[item_id] = candidates
                item_support_text[item_id] = " ".join(
                    value
                    for value in (title, headline_zh, summary, _evidence_text(candidates))
                    if value
                )
                sources_value = _sources(candidates)
                published_at = next(
                    (
                        candidate.get("published_at")
                        for candidate in candidates
                        if candidate.get("published_at")
                    ),
                    None,
                )
                resolved = {
                    "item_id": item_id,
                    "candidate_ids": candidate_ids,
                    "headline": title,
                    "headline_zh": headline_zh,
                    "summary": summary,
                    "why_it_matters": why_it_matters,
                    "sources": sources_value,
                    "published_at": published_at,
                    "evidence_level": evidence_level,
                }
                # Keep the old title key only for legacy model responses.  It
                # lets already-generated offline fixtures remain readable while
                # strict V2 responses use the explicit headline contract.
                if not strict_protocol:
                    resolved["title"] = title
                output.append(resolved)
            resolved_sections[section_id] = output[: section_limits[section_id]]

        point_values = root["top_points"]
        if not isinstance(point_values, list) or not 4 <= len(point_values) <= 5:
            raise ValueError("top_points must contain 4 to 5 items")
        points: list[dict[str, Any]] = []
        used_point_items: set[str] = set()
        for index, value in enumerate(point_values):
            path = f"top_points[{index}]"
            if strict_protocol:
                item = _object(
                    value,
                    path,
                    {"item_refs", "topic", "fact"},
                    {"item_refs", "topic", "fact"},
                )
                refs_value = item["item_refs"]
                if not isinstance(refs_value, list) or not refs_value:
                    raise ValueError(f"{path}.item_refs must be a non-empty array")
                refs: list[str] = []
                for ref_index, ref in enumerate(refs_value):
                    ref_value = _model_ref(ref, f"{path}.item_refs[{ref_index}]")
                    if ref_value not in item_refs:
                        raise ValueError(f"unknown item_ref at {path}.item_refs[{ref_index}]: {ref_value!r}")
                    if ref_value not in refs:
                        refs.append(ref_value)
                resolved_item_ids = [item_refs[ref] for ref in refs]
                duplicate = used_point_items.intersection(resolved_item_ids)
                if duplicate:
                    raise ValueError(f"items reused across top_points: {sorted(duplicate)!r}")
                used_point_items.update(resolved_item_ids)
                candidates = [candidate for item_id in resolved_item_ids for candidate in item_candidates[item_id]]
            else:
                item = _object(
                    value,
                    path,
                    {"candidate_ids", "topic", "fact"},
                    {"candidate_ids", "topic", "fact"},
                )
                candidate_ids = _ids(
                    item["candidate_ids"],
                    f"{path}.candidate_ids",
                    by_id,
                    set(_NOON_SECTIONS),
                    section_by_id,
                )
                resolved_item_ids = [
                    item_id
                    for item_id, item_candidates_value in item_candidates.items()
                    if any(candidate.get("candidate_id") in candidate_ids for candidate in item_candidates_value)
                ]
                candidates = [by_id[candidate_id] for candidate_id in candidate_ids]
            topic = _topic(item["topic"], f"{path}.topic")
            fact = _top_fact(item["fact"], f"{path}.fact")
            _check_supported_numbers(fact, f"{path}.fact numeric claim", candidates)
            if strict_protocol:
                supporting_text = " ".join(
                    item_support_text[item_id] for item_id in resolved_item_ids
                )
                _check_top_point_anchor(fact, supporting_text, f"{path}.fact")
            points.append({"item_ids": resolved_item_ids, "topic": topic, "fact": fact})
        generated = _iso_datetime(generated_at or _now_utc(), "generated_at")
        return {
            "semantic_protocol": NOON_SEMANTIC_PROTOCOL,
            "report": "noon-news",
            "report_date": _report_date(report_date, generated),
            "generated_at": generated,
            "top_points": points,
            "sections": resolved_sections,
        }

    if report != "agents-report":
        raise ValueError(f"unsupported report {report!r}")
    root = _object(model, "model", {"report", "sections"}, {"report", "sections"})
    model_sections = _object(root["sections"], "sections", {"ai_ecosystem"}, {"ai_ecosystem"})
    ecosystem_values = model_sections["ai_ecosystem"]
    if not isinstance(ecosystem_values, list):
        raise ValueError("sections.ai_ecosystem must be an array")
    ecosystem = []
    used: set[str] = set()
    for index, value in enumerate(ecosystem_values):
        path = f"sections.ai_ecosystem[{index}]"
        item = _object(value, path, {"summary", "candidate_ids"}, {"summary", "candidate_ids"})
        candidate_ids = _ids(item["candidate_ids"], f"{path}.candidate_ids", by_id, {"ai_ecosystem"}, section_by_id)
        duplicate = used.intersection(candidate_ids)
        if duplicate:
            raise ValueError(f"candidate IDs reused across ecosystem items: {sorted(duplicate)!r}")
        used.update(candidate_ids)
        ecosystem.append({"summary": _text(item["summary"], f"{path}.summary"), "sources": _sources([by_id[value] for value in candidate_ids])})
    return {
        "report": "agents-report",
        "date": _date(report_date),
        "sections": {
            "ai_ecosystem": ecosystem,
            "model_efficiency": _metric_sections(sections.get("model_efficiency", [])),
            "open_source": _open_source(sections.get("open_source", [])),
        },
    }


def render_resolved(semantic: Mapping[str, Any]) -> str:
    renderer = _load_module("glance_brief_v2_renderer", HERE / "render_report.py")
    return renderer.render_report(semantic)


def invoke_hermes(prompt: str, *, hermes: str, model: str, provider: str, reasoning: str | None, usage_path: Path, timeout: float) -> str:
    argv = [
        hermes, "-z", prompt, "--model", model, "--provider", provider,
        "--toolsets", "context_engine", "--ignore-rules", "--usage-file", str(usage_path),
    ]
    if reasoning:
        argv.extend(["--reasoning", reasoning])
    try:
        completed = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout, check=False, shell=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Hermes model call timed out after {timeout:g}s") from exc
    except OSError as exc:
        raise RuntimeError(f"could not start Hermes: {exc}") from exc
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"Hermes exited with {completed.returncode}: {detail}")
    return completed.stdout


def run_pipeline(args: argparse.Namespace) -> Path:
    assembled = assemble(args.config, args.report)
    model_payload = build_model_payload(assembled)
    contract = (HERE / "prompts" / f"{args.report}.md").read_text(encoding="utf-8")
    prompt = build_model_prompt(contract, model_payload)
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "input": output / f"v2-{args.report}-input.json",
        "model_input": output / f"v2-{args.report}-model-input.json",
        "prompt": output / f"v2-{args.report}-model-prompt.txt",
        "raw": output / f"v2-{args.report}-model-raw.txt",
        "semantic": output / f"v2-{args.report}-semantic.json",
        "markdown": output / f"v2-{args.report}.md",
        "usage": output / f"v2-{args.report}-usage.json",
    }
    _write(paths["input"], json.dumps(assembled, ensure_ascii=False, indent=2) + "\n")
    _write(paths["model_input"], json.dumps(model_payload, ensure_ascii=False, indent=2) + "\n")
    _write(paths["prompt"], prompt)
    raw = invoke_hermes(prompt, hermes=args.hermes, model=args.model, provider=args.provider, reasoning=args.reasoning, usage_path=paths["usage"], timeout=args.timeout)
    _write(paths["raw"], raw)
    model_semantic = parse_model_json(raw)
    semantic = resolve_semantic(
        assembled,
        model_semantic,
        args.date,
        generated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )
    _write(paths["semantic"], json.dumps(semantic, ensure_ascii=False, indent=2) + "\n")
    markdown = render_resolved(semantic)
    _write(paths["markdown"], markdown.rstrip() + "\n")
    return paths["markdown"]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="minimal independent glance_brief V2")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="validate configuration")
    check.add_argument("--config", required=True, type=Path)
    probe = commands.add_parser("probe", help="load configured sources")
    probe.add_argument("--config", required=True, type=Path)
    probe.add_argument("--source")
    run = commands.add_parser("run", help="assemble, call one model, resolve, and render")
    run.add_argument("--config", required=True, type=Path)
    run.add_argument("--report", required=True, choices=REPORTS)
    run.add_argument("--output-dir", required=True, type=Path)
    run.add_argument("--hermes", default="hermes")
    run.add_argument("--model", default="MiniMax-M3")
    run.add_argument("--provider", default="minimax-cn")
    run.add_argument("--reasoning", choices=("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"))
    run.add_argument("--timeout", type=float, default=600.0)
    run.add_argument("--date", help="trusted agents-report date in YYYY-MM-DD form")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        core = _core()
        config = _load_json(args.config)
        if args.command == "check":
            core.validate_config(config)
            print("configuration ok")
            return 0
        if args.command == "probe":
            payload, code = core.probe_sources(config, args.config.parent, args.source)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return code
        path = run_pipeline(args)
        print(path)
        return 0
    except (OSError, TypeError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"V2 pipeline error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
