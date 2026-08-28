#!/usr/bin/env python3
"""Read today's local open-source radar snapshot without collecting again."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RUNTIME_ROOT = Path(
    os.environ.get(
        "LOCAL_OPEN_SOURCE_RADAR_RUNTIME_ROOT",
        os.environ.get("HERMES_HOME", str(Path(__file__).resolve().parents[2])),
    )
).expanduser()
DATA_ROOT = Path(
    os.environ.get(
        "LOCAL_OPEN_SOURCE_RADAR_DATA_DIR",
        str(RUNTIME_ROOT / "data" / "local-open-source-radar"),
    )
).expanduser()
OUTPUT_DIR = Path(
    os.environ.get("LOCAL_OPEN_SOURCE_RADAR_OUTPUT_DIR", str(DATA_ROOT / "output"))
).expanduser()
TODAY = datetime.now(tz=ZoneInfo("Asia/Shanghai")).date().isoformat()


def fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def validate_signals(signals: object) -> bool:
    if not isinstance(signals, dict):
        return False

    sections = {}
    for section_name in ("hot_today", "fresh_hot", "new_projects"):
        items = signals.get(section_name)
        if not isinstance(items, list):
            return False
        checked = []
        for item in items:
            if not isinstance(item, dict):
                return False
            full_name = str(item.get("full_name", ""))
            url = str(item.get("url", ""))
            if not full_name or url != f"https://github.com/{full_name}":
                return False
            checked.append(item)
        sections[section_name] = checked

    hot_names = {item["full_name"] for item in sections["hot_today"]}
    fresh_names = {item["full_name"] for item in sections["fresh_hot"]}
    return fresh_names.issubset(hot_names)


def build_local_report_categories(
    categories: object,
    hot_names: set[str],
) -> list[dict[str, object]] | None:
    """Convert the snapshot's structured category mapping to report sections."""
    if not isinstance(categories, dict) or not categories:
        return None

    normalized: list[dict[str, object]] = []
    covered: set[str] = set()
    for name, items in categories.items():
        if not isinstance(name, str) or not name or not isinstance(items, list):
            return None
        projects: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                return None
            full_name = item.get("full_name")
            url = item.get("url", f"https://github.com/{full_name}")
            if (
                not isinstance(full_name, str)
                or not full_name
                or url != f"https://github.com/{full_name}"
                or full_name not in hot_names
                or full_name in covered
            ):
                return None
            projects.append(full_name)
            covered.add(full_name)
        if projects:
            normalized.append({"name": name, "projects": projects})

    if not normalized or covered != hot_names:
        return None
    return normalized


def main() -> int:
    path = OUTPUT_DIR / f"local-open-source-radar-{TODAY}.json"
    if not path.exists():
        return fail(f"today's local radar snapshot is missing: {path}")

    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return fail(f"today's local radar snapshot is unreadable: {exc}")

    if not isinstance(report, dict):
        return fail("today's local radar snapshot is not a JSON object")
    if report.get("schema_version") != 1:
        return fail("today's local radar snapshot has unsupported schema_version")
    if report.get("report_date") != TODAY:
        return fail(
            f"local radar snapshot date mismatch: expected {TODAY}, "
            f"got {report.get('report_date')!r}"
        )
    quality = report.get("quality")
    if not isinstance(quality, dict) or not quality.get("ok", False):
        return fail("today's local radar snapshot failed quality checks")
    signals = report.get("signals")
    if not validate_signals(signals):
        return fail("today's local radar snapshot has invalid signals/provenance")
    hot_names = {item["full_name"] for item in signals["hot_today"]}
    categories = report.get("categories")
    local_report_categories = build_local_report_categories(categories, hot_names)
    if local_report_categories is None:
        return fail("today's local radar snapshot has missing or invalid category mapping")

    slim = {
        "schema_version": report["schema_version"],
        "report_date": report["report_date"],
        "generated_at": report.get("generated_at"),
        "diagnostics": report.get("diagnostics", {}),
        "quality": quality,
        "signals": signals,
        "categories": categories,
        "local_report_categories": local_report_categories,
        "instructions": report.get("instructions", ""),
    }
    print(json.dumps(slim, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
