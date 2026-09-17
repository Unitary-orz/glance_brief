#!/usr/bin/env python3
"""Prepare one local-radar source snapshot for semantic handoff rendering."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
PREFETCH = HERE / "prefetch.py"
RENDER = HERE / "render.py"
DATA_ROOT = Path(
    os.environ.get(
        "LOCAL_OPEN_SOURCE_RADAR_DATA_DIR",
        str(Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser() / "data" / "local-open-source-radar"),
    )
).expanduser()
TZ = ZoneInfo("Asia/Shanghai")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def _failure(error: str) -> int:
    print(json.dumps({"schema_version": 1, "ok": False, "error": error}, ensure_ascii=False))
    return 0


def _run_prefetch() -> dict:
    try:
        result = subprocess.run(
            [sys.executable, str(PREFETCH)],
            text=True,
            capture_output=True,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("local radar prefetch timed out after 300 seconds")
    except OSError as exc:
        raise RuntimeError(f"local radar prefetch could not start: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"local radar prefetch exited with code {result.returncode}: {detail[:500]}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"local radar prefetch returned malformed JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise RuntimeError("local radar prefetch schema_version must be 1")
    if payload.get("ok") is not True:
        raise RuntimeError(str(payload.get("error") or "local radar source quality check failed"))
    return payload


def prepare() -> dict[str, str]:
    payload = _run_prefetch()
    report_date = payload.get("report_date")
    expected_date = datetime.now(TZ).date().isoformat()
    if report_date != expected_date:
        raise RuntimeError(f"local radar source date mismatch: expected {expected_date}, got {report_date!r}")

    run_id = datetime.now(TZ).strftime("%H%M%S-%f")
    run_dir = DATA_ROOT / "runs" / expected_date / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    source_path = run_dir / "source-input.json"
    semantic_path = run_dir / "semantic-output.json"
    prepared_path = run_dir / "prepared.json"
    _write_json(source_path, payload)
    prepared = {
        "schema_version": 1,
        "report": "local-open-source-radar",
        "report_date": expected_date,
        "run_dir": str(run_dir),
        "source_input": str(source_path),
        "semantic_output": str(semantic_path),
        "render_command": f"{sys.executable} {RENDER} --render-run {run_dir}",
        "source_input_sha256": _sha256(source_path),
    }
    _write_json(prepared_path, prepared)
    return prepared


def print_handoff(prepared: dict[str, str]) -> None:
    print("LOCAL_OPEN_SOURCE_RADAR_SEMANTIC_HANDOFF")
    print(f"RUN_DIR={prepared['run_dir']}")
    print(f"SOURCE_INPUT={prepared['source_input']}")
    print(f"SEMANTIC_OUTPUT={prepared['semantic_output']}")
    print(f"RENDER_COMMAND={prepared['render_command']}")
    print("--- SEMANTIC CONTRACT START ---")
    print(
        "读取 SOURCE_INPUT 的可信 GitHub 快照。只把语义字段写入 SEMANTIC_OUTPUT，"
        "不要写 Markdown、URL、Star、日期或其它来源事实。"
    )
    print("semantic JSON 必须严格包含以下字段：")
    print(
        json.dumps(
            {
                "schema_version": 1,
                "trends": ["1-3 条总体趋势，每条单行"],
                "categories": [{"category_id": "category_definitions 中的 id", "projects": ["hot_today 中的 full_name"]}],
                "hot": [{"full_name": "hot_today 中的 full_name", "summary": "最热行中文简介", "short_summary": "其他行短简介"}],
                "fresh": [{"full_name": "fresh_hot 中的 full_name", "summary": "中文简介", "category_id": "对应分类 id"}],
                "new_projects": [
                    {
                        "full_name": "new_projects 前两项中的 full_name",
                        "summary": "中文简介",
                        "technical_route": "基于技术证据的一句话路线，或 null",
                        "evidence_path": "technical_analysis.evidence_files 中的 path，或 null",
                    }
                ],
            },
            ensure_ascii=False,
        )
    )
    print("严格要求：hot/fresh/new_projects 的项目顺序必须逐字匹配 SOURCE_INPUT；categories 必须恰好覆盖每个 hot_today 项目一次；只根据对应证据写语义文字。")
    print("写完 JSON 后，必须调用 RENDER_COMMAND；最终响应只输出 renderer 的 stdout，不要添加解释、前后缀或确认语。")
    print("--- SEMANTIC CONTRACT END ---")


def main() -> int:
    try:
        print_handoff(prepare())
    except Exception as exc:
        return _failure(f"{type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
