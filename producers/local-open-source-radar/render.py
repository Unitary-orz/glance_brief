#!/usr/bin/env python3
"""Deterministic renderer for the local open-source radar publication."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


class RenderContractError(ValueError):
    """Raised when semantic output or source facts violate the renderer contract."""


_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def _fail(message: str) -> None:
    raise RenderContractError(message)


def _text(value: Any, path: str, *, max_chars: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{path} must be a non-empty string")
    value = value.strip()
    if "\n" in value or "\r" in value:
        _fail(f"{path} must be one line")
    if len(value) > max_chars:
        _fail(f"{path} is too long")
    if "「" in value or "」" in value:
        _fail(f"{path} must not contain description delimiters")
    return value


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RenderContractError(f"cannot read JSON {path}: {exc}") from exc


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _raw_projects(snapshot: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    signals = snapshot.get("signals")
    if not isinstance(signals, dict):
        _fail("source signals must be an object")
    result: list[list[dict[str, Any]]] = []
    for section in ("hot_today", "fresh_hot", "new_projects"):
        items = signals.get(section)
        if not isinstance(items, list):
            _fail(f"source signals.{section} must be an array")
        checked: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                _fail(f"source signals.{section}[{index}] must be an object")
            name = item.get("full_name")
            url = item.get("url")
            if not isinstance(name, str) or not name or url != f"https://github.com/{name}":
                _fail(f"source signals.{section}[{index}] has invalid repository provenance")
            stars = item.get("stars_today", 0)
            if isinstance(stars, bool) or not isinstance(stars, int) or stars < 0:
                _fail(f"source signals.{section}[{index}].stars_today is invalid")
            if section != "new_projects":
                fresh = item.get("is_fresh_hot")
                if not isinstance(fresh, bool):
                    _fail(f"source signals.{section}[{index}].is_fresh_hot is invalid")
            checked.append(item)
        names = [item["full_name"] for item in checked]
        if len(names) != len(set(names)):
            _fail(f"source signals.{section} contains duplicate projects")
        result.append(checked)
    hot, fresh, new = result
    hot_names = {item["full_name"] for item in hot}
    if not {item["full_name"] for item in fresh}.issubset(hot_names):
        _fail("source fresh_hot is not a hot_today subset")
    return hot, fresh, new


def _definitions(snapshot: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    definitions = snapshot.get("category_definitions")
    if not isinstance(definitions, list) or not definitions:
        _fail("source category_definitions must be a non-empty array")
    by_id: dict[str, dict[str, Any]] = {}
    for index, definition in enumerate(definitions):
        if not isinstance(definition, dict):
            _fail(f"category_definitions[{index}] must be an object")
        category_id = definition.get("id")
        label = definition.get("label")
        if not isinstance(category_id, str) or not category_id:
            _fail(f"category_definitions[{index}].id is invalid")
        _text(label, f"category_definitions[{index}].label", max_chars=100)
        if category_id in by_id:
            _fail(f"duplicate category definition: {category_id}")
        by_id[category_id] = definition
    return definitions, by_id


def _validate_semantic(
    snapshot: dict[str, Any], semantic: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[str, tuple[str, list[str]]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    if semantic.get("schema_version") != 1:
        _fail("semantic schema_version must be 1")
    expected_keys = {"schema_version", "trends", "categories", "hot", "fresh", "new_projects"}
    if set(semantic) != expected_keys:
        _fail(f"semantic output fields must be exactly {sorted(expected_keys)}")

    hot, fresh, new = _raw_projects(snapshot)
    definitions, definitions_by_id = _definitions(snapshot)
    hot_names = [item["full_name"] for item in hot]
    fresh_names = [item["full_name"] for item in fresh]
    new_names = [item["full_name"] for item in new[:2]]

    trends = semantic["trends"]
    if not isinstance(trends, list) or not 1 <= len(trends) <= 3:
        _fail("semantic trends must contain one to three items")
    for index, value in enumerate(trends):
        _text(value, f"trends[{index}]", max_chars=180)

    hot_output = semantic["hot"]
    if not isinstance(hot_output, list) or [item.get("full_name") for item in hot_output if isinstance(item, dict)] != hot_names:
        _fail("semantic hot rows must match hot_today order exactly")
    hot_by_name: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(hot_output):
        if not isinstance(item, dict) or set(item) != {"full_name", "summary", "short_summary"}:
            _fail(f"hot[{index}] must contain full_name, summary, and short_summary only")
        name = item["full_name"]
        hot_by_name[name] = {
            "summary": _text(item["summary"], f"hot[{index}].summary", max_chars=180),
            "short_summary": _text(item["short_summary"], f"hot[{index}].short_summary", max_chars=60),
        }

    category_output = semantic["categories"]
    if not isinstance(category_output, list):
        _fail("semantic categories must be an array")
    category_by_id: dict[str, tuple[str, list[str]]] = {}
    assigned: list[str] = []
    for index, item in enumerate(category_output):
        if not isinstance(item, dict) or set(item) != {"category_id", "projects"}:
            _fail(f"categories[{index}] must contain category_id and projects only")
        category_id = item["category_id"]
        projects = item["projects"]
        if category_id not in definitions_by_id or category_id in category_by_id:
            _fail(f"categories[{index}] references an invalid or duplicate category")
        if not isinstance(projects, list) or not projects or any(not isinstance(name, str) for name in projects):
            _fail(f"categories[{index}].projects must be a non-empty string array")
        if len(projects) != len(set(projects)):
            _fail(f"categories[{index}].projects contains duplicates")
        category_by_id[category_id] = (definitions_by_id[category_id]["label"], list(projects))
        assigned.extend(projects)
    if len(assigned) != len(set(assigned)) or set(assigned) != set(hot_names):
        _fail("semantic categories must cover hot_today exactly once")

    fresh_output = semantic["fresh"]
    if not isinstance(fresh_output, list) or [item.get("full_name") for item in fresh_output if isinstance(item, dict)] != fresh_names:
        _fail("semantic fresh rows must match fresh_hot order exactly")
    fresh_by_name: dict[str, dict[str, Any]] = {}
    project_category = {name: category_id for category_id, (_label, projects) in category_by_id.items() for name in projects}
    for index, item in enumerate(fresh_output):
        if not isinstance(item, dict) or set(item) != {"full_name", "summary", "category_id"}:
            _fail(f"fresh[{index}] must contain full_name, summary, and category_id only")
        name = item["full_name"]
        category_id = item["category_id"]
        if category_id != project_category.get(name):
            _fail(f"fresh[{index}] category does not match hot category assignment")
        fresh_by_name[name] = {"summary": _text(item["summary"], f"fresh[{index}].summary", max_chars=180), "category_id": category_id}

    new_output = semantic["new_projects"]
    if not isinstance(new_output, list) or [item.get("full_name") for item in new_output if isinstance(item, dict)] != new_names:
        _fail("semantic new_projects must match the first two source new_projects in order")
    new_by_name: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(new_output):
        if not isinstance(item, dict) or set(item) != {"full_name", "summary", "technical_route", "evidence_path"}:
            _fail(f"new_projects[{index}] has an invalid field set")
        name = item["full_name"]
        route = item["technical_route"]
        if route is not None and not isinstance(route, str):
            _fail(f"new_projects[{index}].technical_route must be a string or null")
        if isinstance(route, str) and route:
            route = _text(route, f"new_projects[{index}].technical_route", max_chars=500)
        evidence_path = item["evidence_path"]
        if evidence_path is not None and not isinstance(evidence_path, str):
            _fail(f"new_projects[{index}].evidence_path must be a string or null")
        raw = next(source for source in new if source["full_name"] == name)
        technical = raw.get("technical_analysis") if isinstance(raw.get("technical_analysis"), dict) else {}
        evidence_files = technical.get("evidence_files", [])
        evidence_paths = {entry.get("path") for entry in evidence_files if isinstance(entry, dict)}
        if evidence_path is not None and evidence_path not in evidence_paths:
            _fail(f"new_projects[{index}].evidence_path is not source evidence")
        new_by_name[name] = {
            "summary": _text(item["summary"], f"new_projects[{index}].summary", max_chars=180),
            "technical_route": route,
            "evidence_path": evidence_path,
        }

    # Keep the return shape explicit: the renderer owns definition order and
    # source order, while the model owns only semantic text and choices.
    _ = definitions
    return hot_by_name, category_by_id, fresh_by_name, new_by_name


def _category_suffix(label: str) -> str:
    parts = label.split(" ", 1)
    return parts[1] if len(parts) == 2 and parts[0] else label


def _project_text(raw: dict[str, Any], summary: str, *, marker: bool = True) -> str:
    prefix = "✨ " if marker and raw.get("is_fresh_hot") else ""
    return f"{prefix}[{raw['full_name']}]({raw['url']})「{summary}」(+{raw['stars_today']:,}★/日)"


def render_report(snapshot: dict[str, Any], semantic: dict[str, Any]) -> str:
    if snapshot.get("schema_version") != 1:
        _fail("source schema_version must be 1")
    if not isinstance(snapshot.get("report_date"), str) or not snapshot["report_date"]:
        _fail("source report_date is required")
    quality = snapshot.get("quality")
    if not isinstance(quality, dict) or quality.get("ok") is not True:
        _fail("source quality.ok must be true")
    hot, fresh, new = _raw_projects(snapshot)
    definitions, definitions_by_id = _definitions(snapshot)
    hot_by_name, category_by_id, fresh_by_name, new_by_name = _validate_semantic(snapshot, semantic)
    raw_by_name = {item["full_name"]: item for item in [*hot, *new]}
    project_category = {name: category_id for category_id, (_label, projects) in category_by_id.items() for name in projects}

    lines = [
        f"📡 **本地开源雷达｜{snapshot['report_date']}**",
        "",
        "**🔥 今日趋势**",
        "",
    ]
    lines.extend(f"- {value}" for value in semantic["trends"])
    lines.extend(["", "**✨ 本期新入榜**", ""])
    if fresh:
        for item in fresh:
            name = item["full_name"]
            category_id = fresh_by_name[name]["category_id"]
            lines.append(
                f"- {_project_text(item, fresh_by_name[name]['summary'], marker=False)}（{_category_suffix(definitions_by_id[category_id]['label'])}）"
            )
    else:
        lines.append("最近历史中没有未出现的今日热门项目；本期不生成新入榜项目。")

    lines.extend([
        "",
        "**🚀 今日热门**",
        "",
        "> `✨` 表示该项目同时属于\"本期新入榜\"，即最近 7 天未在雷达报告中出现；不代表仓库刚创建。",
        "",
    ])
    hot_order = {item["full_name"]: index for index, item in enumerate(hot)}
    category_number = 0
    for definition in definitions:
        category_id = definition["id"]
        if category_id not in category_by_id:
            continue
        names = sorted(category_by_id[category_id][1], key=hot_order.__getitem__)
        lines.append(f"**{_CIRCLED[category_number]} {definition['label']}**")
        category_number += 1
        first = names[0]
        lines.append(f"- 最热：{_project_text(raw_by_name[first], hot_by_name[first]['summary'])}")
        if len(names) > 1:
            rest = "、".join(_project_text(raw_by_name[name], hot_by_name[name]["short_summary"]) for name in names[1:])
            lines.append(f"- 其他：{rest}")
        lines.append("")

    lines.extend(["**🌱 新项目发现**", ""])
    for item in new[:2]:
        name = item["full_name"]
        semantic_item = new_by_name[name]
        age = item.get("repo_age_days")
        if isinstance(age, bool) or not isinstance(age, int) or age < 0:
            _fail(f"source {name}.repo_age_days is invalid")
        lines.append(f"[{name}]({item['url']})「{semantic_item['summary']}」(创建{age}天 · {item.get('stars_total', 0):,}★)")
        technical = item.get("technical_analysis") if isinstance(item.get("technical_analysis"), dict) else {}
        if technical.get("status") != "ok":
            lines.append("- 技术路线：本次未能读取仓库技术信息，暂不判断具体路线。")
        else:
            route = semantic_item["technical_route"] or "具体实现暂不明确"
            line = f"- 技术路线：{route}"
            evidence_path = semantic_item["evidence_path"]
            if evidence_path is not None:
                evidence_url = next(
                    entry["url"] for entry in technical.get("evidence_files", [])
                    if isinstance(entry, dict) and entry.get("path") == evidence_path and isinstance(entry.get("url"), str)
                )
                line += f"；依据：[{evidence_path}]({evidence_url})"
            lines.append(line)
        lines.append("")

    diagnostics = snapshot.get("diagnostics") if isinstance(snapshot.get("diagnostics"), dict) else {}
    for key in ("trending_count", "search_result_count", "merged_count", "relevant_count", "ranked_count", "technical_success_count", "technical_requested_count"):
        if isinstance(diagnostics.get(key), bool) or not isinstance(diagnostics.get(key), int):
            _fail(f"source diagnostics.{key} is required")
    lines.append(
        "> 本次独立采集："
        f"GitHub Trending {diagnostics['trending_count']} 个、Search {diagnostics['search_result_count']} 条，"
        f"合并后 {diagnostics['merged_count']} 个候选，AI 相关性初筛保留 {diagnostics['relevant_count']} 个，"
        f"最终排序 {diagnostics['ranked_count']} 个；新项目技术取证成功 "
        f"{diagnostics['technical_success_count']}/{diagnostics['technical_requested_count']} 个；质量检查通过。数据来自本地采集。"
    )
    return "\n".join(lines).rstrip() + "\n"


def _validated_run_dir(value: str, data_root: Path) -> Path:
    run_dir = Path(value).expanduser().resolve()
    runs_root = (data_root / "runs").resolve()
    if run_dir == runs_root or runs_root not in run_dir.parents or not run_dir.is_dir():
        _fail("render run directory is outside the local radar runs root")
    return run_dir


def render_run(value: str, *, data_root: Path | None = None) -> str:
    root = data_root or Path(os.environ.get("LOCAL_OPEN_SOURCE_RADAR_DATA_DIR", "~/.hermes/data/local-open-source-radar")).expanduser()
    run_dir = _validated_run_dir(value, root)
    prepared_path = run_dir / "prepared.json"
    prepared = _load(prepared_path)
    source_path = Path(prepared.get("source_input", ""))
    semantic_path = Path(prepared.get("semantic_output", ""))
    if source_path.resolve().parent != run_dir or semantic_path.resolve().parent != run_dir:
        _fail("prepared artifact paths must remain inside the run directory")
    if prepared.get("source_input_sha256") != _sha256(source_path):
        _fail("source input changed after handoff preparation")
    if not semantic_path.is_file():
        _fail("semantic output is missing")
    try:
        snapshot = _load(source_path)
        semantic = _load(semantic_path)
        output = render_report(snapshot, semantic)
        (run_dir / "report.md").write_text(output, encoding="utf-8")
        manifest = {
            "status": "ok",
            "schema_version": 1,
            "report": "local-open-source-radar",
            "report_date": snapshot.get("report_date"),
            "source_input_sha256": _sha256(source_path),
            "semantic_output_sha256": _sha256(semantic_path),
            "report_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
        }
        (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return output
    except Exception as exc:
        try:
            (run_dir / "report.md").unlink()
        except FileNotFoundError:
            pass
        failure = {"status": "failed", "error_type": type(exc).__name__, "error": str(exc)}
        (run_dir / "failure.json").write_text(json.dumps(failure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--render-run", required=True)
    args = parser.parse_args()
    print(render_run(args.render_run), end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"local radar render failed: {type(exc).__name__}: {exc}", file=os.sys.stderr)
        raise SystemExit(1)
