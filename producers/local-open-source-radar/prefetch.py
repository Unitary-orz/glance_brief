#!/usr/bin/env python3
"""Cron prefetch wrapper for the independent local open-source radar."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

COLLECTOR = Path(__file__).resolve().with_name("collector.py")


def main() -> int:
    proc = subprocess.run(
        [sys.executable, str(COLLECTOR)],
        text=True,
        capture_output=True,
        timeout=240,
        check=False,
    )
    if proc.returncode != 0:
        if proc.stderr:
            print(proc.stderr.strip(), file=sys.stderr)
        return proc.returncode

    try:
        metadata = json.loads(proc.stdout)
        output_path = Path(metadata["output_path"])
        report = json.loads(output_path.read_text(encoding="utf-8"))
    except (KeyError, OSError, ValueError) as exc:
        print(f"invalid local radar collector output: {exc}", file=sys.stderr)
        return 1

    slim = {
        "report_date": report["report_date"],
        "generated_at": report["generated_at"],
        "diagnostics": report["diagnostics"],
        "quality": report["quality"],
        "signals": report["signals"],
        "instructions": report["instructions"],
    }
    print(json.dumps(slim, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
