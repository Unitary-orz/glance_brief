#!/usr/bin/env python3
"""Read today's local open-source radar snapshot without collecting again."""
from __future__ import annotations

import json
import os
import re
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
LOCAL_REPORT_OUTPUT_DIR_VALUE = os.environ.get("LOCAL_OPEN_SOURCE_RADAR_REPORT_DIR", "").strip()
LOCAL_REPORT_OUTPUT_DIR = (
    Path(LOCAL_REPORT_OUTPUT_DIR_VALUE).expanduser()
    if LOCAL_REPORT_OUTPUT_DIR_VALUE
    else None
)
TODAY = datetime.now(tz=ZoneInfo("Asia/Shanghai")).date().isoformat()
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https://github\.com/[^)\s]+)\)")
CATEGORY_HEADING_RE = re.compile(r"^\s*[①②③④⑤⑥⑦⑧⑨⑩]\s+.+$")


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


def read_local_report_categories(hot_names: set[str]) -> list[dict[str, object]] | None:
    """Extract and validate today's category/project mapping from the local report."""
    if LOCAL_REPORT_OUTPUT_DIR is None or not LOCAL_REPORT_OUTPUT_DIR.exists():
        return None

    for path in sorted(LOCAL_REPORT_OUTPUT_DIR.glob("*.md"), reverse=True):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        marker = f"📡 **本地开源雷达｜{TODAY}**"
        marker_index = text.find(marker)
        if marker_index < 0:
            continue
        report = text[marker_index:]
        start = report.find("**🚀 今日热门**")
        if start < 0:
            continue
        end_candidates = [
            index for index in (
                report.find("**🌱 新项目发现**", start),
                report.find("> 本次独立采集", start),
            )
            if index >= 0
        ]
        end = min(end_candidates) if end_candidates else len(report)
        hot_section = report[start:end]

        categories: list[dict[str, object]] = []
        current: dict[str, object] | None = None
        seen: set[str] = set()
        invalid = False
        for line in hot_section.splitlines():
            if CATEGORY_HEADING_RE.match(line):
                current = {"name": line.strip(), "projects": []}
                categories.append(current)
                continue
            if current is None:
                continue
            for match in MARKDOWN_LINK_RE.finditer(line):
                full_name, url = match.groups()
                if url != f"https://github.com/{full_name}" or full_name not in hot_names:
                    invalid = True
                    continue
                projects = current["projects"]
                assert isinstance(projects, list)
                if full_name not in seen:
                    projects.append(full_name)
                    seen.add(full_name)

        covered = {
            full_name
            for category in categories
            for full_name in category["projects"]
        }
        if categories and not invalid and covered == hot_names:
            return categories
    return None


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
    local_report_categories = read_local_report_categories(hot_names)
    if local_report_categories is None:
        return fail("today's local radar report has missing or invalid category mapping")

    slim = {
        "report_date": report["report_date"],
        "generated_at": report.get("generated_at"),
        "diagnostics": report.get("diagnostics", {}),
        "quality": quality,
        "signals": signals,
        "local_report_categories": local_report_categories,
        "instructions": report.get("instructions", ""),
    }
    print(json.dumps(slim, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
