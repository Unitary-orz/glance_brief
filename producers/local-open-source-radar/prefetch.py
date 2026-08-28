#!/usr/bin/env python3
"""Cron prefetch wrapper for the independent local open-source radar."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

COLLECTOR = Path(__file__).resolve().with_name("collector.py")
COLLECTOR_TIMEOUT = 240


def _empty_signals() -> dict[str, list[Any]]:
    return {"hot_today": [], "fresh_hot": [], "new_projects": []}


def failure_payload(
    error: str,
    *,
    returncode: int | None = None,
    stderr: str = "",
) -> dict[str, Any]:
    """Return the stable failure shape consumed by the scheduled report."""
    return {
        "schema_version": 1,
        "ok": False,
        "error": error,
        "returncode": returncode,
        "stderr": stderr.strip()[-4000:],
        "items": [],
        "report_date": None,
        "generated_at": None,
        "diagnostics": {},
        "quality": {"ok": False, "errors": [error], "candidate_count": 0},
        "signals": _empty_signals(),
        "categories": {},
        "instructions": "",
    }


def emit(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def main() -> int:
    try:
        proc = subprocess.run(
            [sys.executable, str(COLLECTOR)],
            text=True,
            capture_output=True,
            timeout=COLLECTOR_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return emit(
            failure_payload(
                f"local radar collector timed out after {COLLECTOR_TIMEOUT} seconds"
            )
        )
    except OSError as exc:
        return emit(failure_payload(f"local radar collector could not start: {exc}"))

    if proc.returncode != 0:
        return emit(
            failure_payload(
                f"local radar collector exited with code {proc.returncode}",
                returncode=proc.returncode,
                stderr=proc.stderr,
            )
        )

    try:
        metadata = json.loads(proc.stdout)
        output_path = Path(metadata["output_path"])
        report = json.loads(output_path.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise ValueError("report must be a JSON object")
        if report.get("schema_version") != 1:
            raise ValueError("report has unsupported schema_version")
        required = (
            "report_date",
            "generated_at",
            "diagnostics",
            "quality",
            "signals",
            "categories",
            "instructions",
        )
        missing = [name for name in required if name not in report]
        if missing:
            raise ValueError(f"report is missing required fields: {', '.join(missing)}")
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return emit(failure_payload(f"invalid local radar collector output: {exc}"))

    slim = {
        "schema_version": report["schema_version"],
        "ok": True,
        "report_date": report["report_date"],
        "generated_at": report["generated_at"],
        "diagnostics": report["diagnostics"],
        "quality": report["quality"],
        "signals": report["signals"],
        "categories": report["categories"],
        "instructions": report["instructions"],
    }
    return emit(slim)


if __name__ == "__main__":
    raise SystemExit(main())
