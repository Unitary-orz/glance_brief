#!/usr/bin/env python3
"""Read, rank, and render the CodexRadar intelligence-efficiency block."""
from __future__ import annotations

import json
import math
import os
import time
from http.client import IncompleteRead
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CONFIG_PATH = Path(os.environ.get(
    "CODEXRADAR_CONFIG",
    str(Path(__file__).resolve().parents[1] / "config" / "codexradar_watch.json"),
))
DEFAULT_SNAPSHOT_URL = "https://codexradar.com/data/intelligence-efficiency.json"
DEFAULT_RAW_URL = "https://codexradar.com/api/intelligence-efficiency"
USER_AGENT = "hermes-agents-radar/1.0 (+https://codexradar.com/)"
TIMEOUT = 30
ATTEMPTS = 2
COMBINED_COST_WEIGHT = math.log(2.5) / math.log(1.35)

DISPLAY_MODELS = {
    "gpt-5.6-sol": "Sol",
    "gpt-5.6-luna": "Luna",
    "gpt-5.5": "gpt-5.5",
    "deepseek-v4-flash": "DeepSeek V4",
}


def fetch_json(url: str) -> Any:
    """Fetch JSON with a browser-like UA and bounded retries."""
    last_error: Exception | None = None
    for attempt in range(ATTEMPTS):
        try:
            request = Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": USER_AGENT,
                },
            )
            with urlopen(request, timeout=TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:300]
            last_error = RuntimeError(f"HTTP {exc.code}: {body}")
            if attempt == 0 and (exc.code == 429 or 500 <= exc.code < 600):
                time.sleep(2)
                continue
            break
        except (IncompleteRead, URLError, TimeoutError, OSError, ValueError) as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(2)
                continue
            break
    raise RuntimeError(f"CodexRadar request failed: {last_error}")


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict):
        raise ValueError("CodexRadar watch config must be an object")
    return config


def as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def raw_combined_cost(minutes: float, price: float) -> float:
    return price * (minutes / 10.0) ** COMBINED_COST_WEIGHT * 100.0


def point_from_snapshot(point: dict[str, Any]) -> dict[str, Any] | None:
    model = point.get("model")
    effort = point.get("effort")
    iq = as_float(point.get("iq"))
    minutes = as_float(point.get("average_minutes"))
    price = as_float(point.get("average_price_usd"))
    if not isinstance(model, str) or not isinstance(effort, str):
        return None
    if iq is None or minutes is None or price is None or minutes <= 0 or price < 0:
        return None
    combined = as_float(point.get("combined_cost_index"))
    if combined is None:
        combined = raw_combined_cost(minutes, price)
    return {
        "model": model,
        "effort": effort,
        "iq": iq,
        "minutes": minutes,
        "price": price,
        "combined_cost": combined,
        "valid_tasks": point.get("valid_tasks"),
        "runs_24h": point.get("runs_24h"),
    }


def points_from_snapshot(payload: dict[str, Any]) -> list[dict[str, Any]]:
    points = payload.get("points")
    if not isinstance(points, list) or not points:
        raise ValueError("CodexRadar snapshot has no points")
    parsed = [point_from_snapshot(item) for item in points if isinstance(item, dict)]
    result = [point for point in parsed if point is not None]
    if not result:
        raise ValueError("CodexRadar snapshot has no valid points")
    return result


def points_from_raw(payload: dict[str, Any]) -> list[dict[str, Any]]:
    combos = payload.get("combos")
    tasks = payload.get("tasks")
    cells = payload.get("cells")
    if not isinstance(combos, list) or not isinstance(tasks, list) or not isinstance(cells, dict):
        raise ValueError("CodexRadar raw table schema is incomplete")

    result: list[dict[str, Any]] = []
    for combo in combos:
        if not isinstance(combo, dict):
            continue
        model, effort = combo.get("model"), combo.get("effort")
        if not isinstance(model, str) or not isinstance(effort, str):
            continue
        passed = valid = 0
        duration_sum = price_sum = 0.0
        duration_count = price_count = 0
        for task in tasks:
            if not isinstance(task, dict) or not isinstance(task.get("id"), str):
                continue
            cell = cells.get(f"{task['id']}|{model}|{effort}")
            runners = cell.get("ran_by") if isinstance(cell, dict) else None
            runner = runners[0] if isinstance(runners, list) and runners and isinstance(runners[0], dict) else None
            if not runner:
                continue
            if isinstance(runner.get("passed"), bool):
                valid += 1
                passed += int(runner["passed"])
            duration = as_float(runner.get("duration_sec"))
            if duration is not None and duration > 0:
                duration_sum += duration / 60.0
                duration_count += 1
            price = as_float(runner.get("actual_cost_usd"))
            if price is not None and price >= 0 and (effort != "ultra" or runner.get("cost_complete") is True):
                price_sum += price
                price_count += 1
        if valid == 0 or duration_count == 0 or price_count == 0:
            continue
        minutes = duration_sum / duration_count
        price = price_sum / price_count
        result.append({
            "model": model,
            "effort": effort,
            "iq": passed / valid * 150.0,
            "minutes": minutes,
            "price": price,
            "combined_cost": raw_combined_cost(minutes, price),
            "valid_tasks": valid,
            "runs_24h": None,
        })
    if not result:
        raise ValueError("CodexRadar raw table has no valid points")
    return result


def matches_rule(point: dict[str, Any], rule: dict[str, Any], effort_order: list[str]) -> bool:
    if point["model"] != rule.get("model"):
        return False
    efforts = rule.get("efforts")
    if efforts == "all_available":
        return True
    if isinstance(efforts, list):
        return point["effort"] in efforts
    minimum = rule.get("min_effort")
    if isinstance(minimum, str):
        try:
            return effort_order.index(point["effort"]) >= effort_order.index(minimum)
        except ValueError:
            return False
    return False


def select_points(points: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    selection = config.get("selection", {})
    explicit = selection.get("explicit", [])
    effort_order = config.get("effort_order", [])
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    for point in points:
        if any(isinstance(rule, dict) and matches_rule(point, rule, effort_order) for rule in explicit):
            selected[(point["model"], point["effort"])] = point

    iq_filter = selection.get("iq_filter", {})
    if iq_filter.get("enabled") is True:
        threshold = as_float(iq_filter.get("include_iq_at_least"))
        if threshold is not None:
            for point in points:
                if point["iq"] >= threshold:
                    selected[(point["model"], point["effort"])] = point

    if not selected:
        raise ValueError("CodexRadar selection matched no points")
    return list(selected.values())


def config_order(config: dict[str, Any], point: dict[str, Any]) -> tuple[int, int, str, str]:
    model_order = config.get("ranking", {}).get("other_sort", {}).get("model_order", [])
    effort_order = config.get("effort_order", [])
    try:
        model_index = model_order.index(point["model"])
    except ValueError:
        model_index = len(model_order)
    try:
        effort_index = effort_order.index(point["effort"])
    except ValueError:
        effort_index = len(effort_order)
    return model_index, effort_index, point["model"], point["effort"]


def minmax_high(values: list[float], value: float) -> float:
    low, high = min(values), max(values)
    return (value - low) / (high - low) if high > low else 1.0


def minmax_low(values: list[float], value: float) -> float:
    low, high = min(values), max(values)
    return (high - value) / (high - low) if high > low else 1.0


def percentile_scores(values: list[float], higher_is_better: bool) -> list[float]:
    """Return average-tie percentiles; values are always in (0, 1)."""
    count = len(values)
    ordered = sorted(values, reverse=not higher_is_better)
    rank_by_value: dict[float, float] = {}
    index = 0
    while index < count:
        end = index + 1
        while end < count and ordered[end] == ordered[index]:
            end += 1
        average_rank = (index + 1 + end) / 2.0
        rank_by_value[ordered[index]] = average_rank / (count + 1.0)
        index = end
    return [rank_by_value[value] for value in values]


def rank_intelligence(points: list[dict[str, Any]], top_n: int, config: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        points,
        key=lambda p: (-p["iq"], p["combined_cost"], p["minutes"], p["price"], config_order(config, p)),
    )[:top_n]


def rank_value(points: list[dict[str, Any]], ranking: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    scope = ranking.get("value_scope", "all_explicit_watch_configs")
    candidates = [point for point in points if point["model"] != "gpt-5.6-sol"] if scope == "non_sol_explicit_watch_configs" else list(points)
    if not candidates:
        candidates = list(points)

    floor = as_float(ranking.get("value_iq_floor"))
    if floor is not None:
        candidates = [point for point in candidates if point["iq"] >= floor]
    if not candidates:
        return []

    scored = []
    for point in candidates:
        item = dict(point)
        item["value_score"] = point["iq"] / max(point["price"], 0.000001)
        scored.append(item)
    scored.sort(
        key=lambda p: (
            -p["value_score"],
            -p["iq"],
            p["combined_cost"],
            p["minutes"],
            p["price"],
            config_order(config, p),
        )
    )
    return scored[:int(ranking.get("value_top_n", 3))]


def rank_balanced(points: list[dict[str, Any]], ranking: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    weights = ranking.get("balanced_weights", {})
    weight_iq = float(weights.get("iq", 1))
    weight_time = float(weights.get("average_minutes", 1))
    weight_cost = float(weights.get("average_price_usd", 1))
    total = weight_iq + weight_time + weight_cost or 3.0
    iq_scores = percentile_scores([p["iq"] for p in points], True)
    time_scores = percentile_scores([p["minutes"] for p in points], False)
    cost_scores = percentile_scores([p["price"] for p in points], False)
    scored = []
    for point, iq_score, time_score, cost_score in zip(points, iq_scores, time_scores, cost_scores):
        item = dict(point)
        item["balanced_score"] = math.exp(
            (
                weight_iq * math.log(iq_score)
                + weight_time * math.log(time_score)
                + weight_cost * math.log(cost_score)
            ) / total
        )
        scored.append(item)
    scored.sort(key=lambda p: (-p["balanced_score"], p["combined_cost"], -p["iq"], config_order(config, p)))
    return scored[:int(ranking.get("balanced_top_n", 2))]


def display_model(model: str) -> str:
    return DISPLAY_MODELS.get(model, model)


def format_point(point: dict[str, Any]) -> str:
    return f"`{display_model(point['model'])} {point['effort']}`（IQ {point['iq']:.1f} · {point['minutes']:.1f}m · ${point['price']:.2f}）"


def format_ranked_line(number: int, title: str, points: list[dict[str, Any]]) -> str:
    values = " > ".join(format_point(point) for point in points) or "无"
    return f"- {number} {title}：{values}"


def render_markdown(
    intelligence: list[dict[str, Any]],
    balanced: list[dict[str, Any]],
    value: list[dict[str, Any]],
    other: list[dict[str, Any]],
) -> str:
    lines = [
        "**🧠 CodexRadar 智力效率**",
        "",
        format_ranked_line( "①", "智力Top2", intelligence),
        format_ranked_line( "②", "均衡Top2", balanced),
        format_ranked_line( "③", "性价比Top3", value),
    ]
    other_text = "；".join(format_point(point) for point in other) or "无"
    lines.append(f"- ④ 其他：{other_text}")
    return "\n".join(lines)


def compact_point(point: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": point["model"],
        "effort": point["effort"],
        "iq": round(point["iq"], 1),
        "average_minutes": round(point["minutes"], 1),
        "average_price_usd": round(point["price"], 2),
    }


def build_result(points: list[dict[str, Any]], config: dict[str, Any], source: str, source_updated_at: Any) -> dict[str, Any]:
    selected = select_points(points, config)
    ranking = config.get("ranking", {})
    intelligence = rank_intelligence(selected, int(ranking.get("intelligence_top_n", 2)), config)
    balanced = rank_balanced(selected, ranking, config)
    value = rank_value(selected, ranking, config)
    top_keys = {
        (point["model"], point["effort"])
        for group in (intelligence, balanced, value)
        for point in group
    }
    other = [point for point in selected if (point["model"], point["effort"]) not in top_keys]
    other.sort(key=lambda point: config_order(config, point))
    result = {
        "ok": True,
        "available": True,
        "source": source,
        "source_updated_at": source_updated_at,
        "selected_count": len(selected),
        "selected": [compact_point(point) for point in sorted(selected, key=lambda p: config_order(config, p))],
        "rankings": {
            "intelligence_top2": [compact_point(point) for point in intelligence],
            "balanced_top2": [compact_point(point) for point in balanced],
            "value_top3": [compact_point(point) for point in value],
            "other": [compact_point(point) for point in other],
        },
        "markdown": render_markdown(intelligence, balanced, value, other),
        "instructions": "直接使用 markdown 作为日报板块；IQ 是 CodexRadar 任务集通过率缩放指标，不是通用智力分数。",
    }
    if not isinstance(source_updated_at, str) or not source_updated_at.strip():
        result["warning"] = "source_updated_at missing; data freshness was not verified"
    return result


def unavailable(error: str) -> dict[str, Any]:
    return {
        "ok": False,
        "available": False,
        "error": error,
        "markdown": "**🧠 CodexRadar 智力效率**\n\n- 信息有限：CodexRadar 数据暂时不可用",
    }


def run_codexradar() -> dict[str, Any]:
    try:
        config = load_config()
        snapshot_url = config.get("source", {}).get("snapshot_url", DEFAULT_SNAPSHOT_URL)
        try:
            snapshot = fetch_json(snapshot_url)
            points = points_from_snapshot(snapshot)
            return build_result(
                points,
                config,
                "snapshot",
                snapshot.get("source_updated_at"),
            )
        except Exception as snapshot_error:
            raw_url = config.get("source", {}).get("raw_url", DEFAULT_RAW_URL)
            raw = fetch_json(raw_url)
            points = points_from_raw(raw)
            result = build_result(points, config, "raw_fallback", raw.get("source_updated_at"))
            result["fallback_reason"] = str(snapshot_error)
            return result
    except Exception as exc:
        return unavailable(str(exc))


def main() -> None:
    print(json.dumps(run_codexradar(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
