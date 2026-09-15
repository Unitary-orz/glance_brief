import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "skills" / "agents-report" / "scripts" / "codexradar_efficiency.py"
spec = importlib.util.spec_from_file_location("codexradar_efficiency", MODULE_PATH)
if spec is None or spec.loader is None:
    raise ImportError(f"cannot load CodexRadar module from {MODULE_PATH}")
efficiency = importlib.util.module_from_spec(spec)
spec.loader.exec_module(efficiency)


def _point(model, effort, iq, minutes, price):
    return {
        "model": model,
        "effort": effort,
        "iq": iq,
        "minutes": minutes,
        "price": price,
        "combined_cost": efficiency.raw_combined_cost(minutes, price),
    }


def test_display_cap_counts_rendered_ranking_entries_not_unique_configs():
    points = [
        _point("gpt-5.6-sol", "medium", 95.5, 16.1, 2.93),
        _point("gpt-5.6-sol", "high", 96.9, 19.8, 4.12),
        _point("gpt-5.6-luna", "xhigh", 87.0, 24.3, 0.33),
        _point("gpt-5.6-luna", "max", 101.3, 37.0, 0.54),
        _point("deepseek-v4.1-flash", "high", 85.7, 11.9, 0.47),
        _point("deepseek-v4-pro", "high", 88.2, 28.7, 0.58),
        _point("gpt-6-astra", "low", 100.0, 8.9, 2.01),
        _point("gpt-6-astra", "medium", 107.3, 8.9, 2.22),
        _point("gpt-6-astra", "high", 108.1, 12.8, 3.07),
        _point("gpt-6-astra", "xhigh", 106.2, 17.8, 4.01),
        _point("gpt-6-astra", "max", 107.6, 25.4, 5.27),
        _point("gpt-6-astra", "ultra", 108.8, 13.7, 9.40),
    ]
    config = {
        "display": {"max_configs": 12, "fill_method": "balanced_score"},
        "selection": {
            "explicit": [
                {"model": "gpt-5.6-luna", "efforts": ["xhigh", "max"]},
                {"model": "gpt-5.6-sol", "min_effort": "medium"},
                {"model": "deepseek-v4.1-flash", "efforts": "all_available"},
                {"model": "deepseek-v4-pro", "efforts": "all_available"},
                {"model": "gpt-6-astra", "efforts": "all_available"},
            ]
        },
        "effort_order": ["low", "medium", "high", "xhigh", "max", "ultra"],
        "ranking": {
            "intelligence_top_n": 2,
            "balanced_top_n": 2,
            "value_top_n": 3,
            "value_scope": "non_sol_explicit_watch_configs",
            "value_iq_floor": 70,
            "value_price_bands": [
                {"max_price_usd": 0.30, "factor": 1.00},
                {"max_price_usd": 0.50, "factor": 0.98},
                {"max_price_usd": 1.00, "factor": 0.95},
                {"max_price_usd": 3.00, "factor": 0.78},
                {"max_price_usd": 5.00, "factor": 0.75},
                {"factor": 0.65},
            ],
            "balanced_weights": {
                "iq": 1,
                "average_minutes": 1,
                "average_price_usd": 1,
            },
            "other_sort": {
                "model_order": [
                    "gpt-5.6-sol",
                    "gpt-5.6-luna",
                    "deepseek-v4.1-flash",
                    "deepseek-v4-pro",
                    "gpt-6-astra",
                ]
            },
        },
    }

    result = efficiency.build_result(points, config, "test", "2026-09-08T00:00:00Z")
    rankings = result["rankings"]
    rendered_count = sum(
        len(rankings[name])
        for name in ("intelligence_top2", "balanced_top2", "value_top3", "other")
    )

    assert rendered_count == 12
    assert len(rankings["intelligence_top2"]) == 2
    assert len(rankings["balanced_top2"]) == 2
    assert len(rankings["value_top3"]) == 3
    assert "DP V4.1 Flash" in result["markdown"]


if __name__ == "__main__":
    test_display_cap_counts_rendered_ranking_entries_not_unique_configs()
    print("ok")
