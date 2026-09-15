#!/usr/bin/env python3
"""Agents report: prepare semantic evidence, then render deterministically.

The default invocation is the Hermes Cron pre-run stage. It captures the current
formal producer snapshot once, asks the Cron-owned model only for semantic JSON,
and later renders from the immutable prepared artifacts. No nested Hermes/model
process exists here.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

HERMES_HOME = Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()
RUNTIME_ROOT = Path(
    os.environ.get("GLANCE_BRIEF_REPORTS_ROOT", str(Path(__file__).resolve().parents[1]))
).expanduser()
LIB_ROOT = RUNTIME_ROOT / "lib"
DATA_ROOT = Path(
    os.environ.get("GLANCE_BRIEF_AGENTS_DATA", str(HERMES_HOME / "data" / "glance-brief-agents"))
).expanduser()
PREFETCH_VALUE = os.environ.get("GLANCE_BRIEF_AGENTS_PREFETCH")
PREFETCH = Path(PREFETCH_VALUE).expanduser() if PREFETCH_VALUE else None
CONFIG = Path(
    os.environ.get("GLANCE_BRIEF_AGENTS_CONFIG", str(HERMES_HOME / "data" / "glance-brief-reports" / "config" / "brief-live.json"))
).expanduser()
SNAPSHOT = DATA_ROOT / "source-snapshot.json"
TZ = ZoneInfo("Asia/Shanghai")
REPORT = "agents-report"
MODEL = os.environ.get("GLANCE_BRIEF_AGENTS_MODEL", "MiniMax-M3")
PROVIDER = os.environ.get("GLANCE_BRIEF_AGENTS_PROVIDER", "minimax-cn")
REASONING = os.environ.get("GLANCE_BRIEF_AGENTS_REASONING", "medium")

sys.path.insert(0, str(LIB_ROOT))
from glance_brief import cli, local_radar_publication  # noqa: E402

PUBLICATION_DIR_VALUE = os.environ.get("GLANCE_BRIEF_AGENTS_PUBLICATION_DIR")
PUBLICATION_DIR = Path(PUBLICATION_DIR_VALUE).expanduser() if PUBLICATION_DIR_VALUE else None


def _run(command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, value: object) -> None:
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


def _prefetch(report_date: str) -> dict:
    if PREFETCH is None:
        raise RuntimeError(
            "GLANCE_BRIEF_AGENTS_PREFETCH must point to the dedicated agents source command"
        )
    if PUBLICATION_DIR is None:
        raise RuntimeError(
            "GLANCE_BRIEF_AGENTS_PUBLICATION_DIR must point to the dated local-radar publication root"
        )
    result = _run([sys.executable, str(PREFETCH)], timeout=300)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"prefetch exited {result.returncode}: {detail[:500]}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"prefetch returned malformed JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise RuntimeError("prefetch schema_version must be 1")
    return local_radar_publication.attach_local_radar_publication(
        payload,
        report_date=report_date,
        report_dir=PUBLICATION_DIR,
    )


def _prepare() -> dict:
    report_date = dt.datetime.now(TZ).date().isoformat()
    source_payload = _prefetch(report_date)
    _atomic_json(SNAPSHOT, source_payload)

    run_id = dt.datetime.now(TZ).strftime("%H%M%S-%f")
    run_dir = DATA_ROOT / "runs" / report_date / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    prepare_args = argparse.Namespace(
        config=CONFIG,
        report=REPORT,
        output_dir=run_dir,
        date=report_date,
        model=MODEL,
        provider=PROVIDER,
        reasoning=REASONING,
    )
    cli.prepare_pipeline(prepare_args)

    semantic_output = run_dir / "model-response.input.json"
    render_command = " ".join(
        shlex.quote(part)
        for part in (
            sys.executable,
            str(Path(__file__).resolve()),
            "--render-run",
            str(run_dir),
        )
    )
    prepared = cli.load_json(run_dir / "prepared.json")
    prepared.update({
        "run_dir": str(run_dir),
        "semantic_output": str(semantic_output),
        "render_command": render_command,
        "source_snapshot_sha256": _sha256(SNAPSHOT),
    })
    cli.write_json(run_dir / "prepared.json", prepared)
    _atomic_json(DATA_ROOT / "latest-prepared.json", prepared)
    return {
        "prepared": prepared,
        "model_prompt": (run_dir / "model-prompt.txt").read_text(encoding="utf-8"),
        "assembled": cli.load_json(run_dir / "assembled.json"),
    }


def _print_agent_handoff(prepared_result: dict) -> None:
    prepared = prepared_result["prepared"]
    print("GLANCE_BRIEF_AGENTS_SEMANTIC_HANDOFF")
    print(f"RUN_DIR={prepared['run_dir']}")
    print(f"SEMANTIC_OUTPUT={prepared['semantic_output']}")
    print(f"RENDER_COMMAND={prepared['render_command']}")
    print("--- SEMANTIC CONTRACT AND CANDIDATES START ---")
    print(prepared_result["model_prompt"].rstrip())
    print("--- SEMANTIC CONTRACT AND CANDIDATES END ---")


def _validated_run_dir(value: str) -> Path:
    run_dir = Path(value).expanduser().resolve()
    runs_root = (DATA_ROOT / "runs").resolve()
    if run_dir == runs_root or runs_root not in run_dir.parents:
        raise RuntimeError("render run directory is outside the isolated Agents reports runs root")
    if not run_dir.is_dir():
        raise RuntimeError(f"render run directory does not exist: {run_dir}")
    return run_dir


def _render_run(value: str) -> str:
    run_dir = _validated_run_dir(value)
    prepared_path = run_dir / "prepared.json"
    semantic_path = run_dir / "model-response.input.json"
    if not prepared_path.is_file():
        raise RuntimeError("prepared.json is missing")
    if not semantic_path.is_file():
        raise RuntimeError("model-response.input.json is missing")

    prepared = cli.load_json(prepared_path)
    if prepared.get("report") != REPORT:
        raise RuntimeError("prepared report is not agents-report")
    if prepared.get("run_dir") != str(run_dir):
        raise RuntimeError("prepared run_dir does not match requested run")
    if prepared.get("semantic_output") != str(semantic_path):
        raise RuntimeError("prepared semantic output path does not match requested run")
    if prepared.get("config_sha256") != _sha256(CONFIG):
        raise RuntimeError("Agents reports config changed after semantic preparation")
    render_args = argparse.Namespace(
        config=CONFIG,
        output_dir=run_dir,
        model_response=semantic_path,
    )
    report_path = cli.render_prepared_pipeline(render_args)
    manifest = cli.load_json(run_dir / "manifest.json")
    manifest["source_snapshot_sha256"] = prepared.get("source_snapshot_sha256")
    cli.write_json(run_dir / "manifest.json", manifest)
    if manifest.get("status") != "ok" or manifest.get("report") != REPORT:
        raise RuntimeError("Agents reports manifest does not describe a successful run")
    if not report_path.is_file():
        raise RuntimeError("Agents reports renderer succeeded without report.md")
    return report_path.read_text(encoding="utf-8").rstrip()


def _probe(prepared_result: dict) -> dict:
    assembled = prepared_result["assembled"]
    sections = assembled.get("sections", {})
    registry = assembled.get("candidate_registry", {})
    return {
        "ok": True,
        "report": REPORT,
        "report_date": prepared_result["prepared"]["report_date"],
        "run_dir": prepared_result["prepared"]["run_dir"],
        "candidate_counts": {
            name: len(ids) if isinstance(ids, list) else 0
            for name, ids in sections.items()
        },
        "registry_size": len(registry) if isinstance(registry, dict) else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true", help="fetch and validate real Agents candidates without a model call")
    parser.add_argument("--render-run", help="validate semantic JSON and render one prepared Agents reports run")
    args = parser.parse_args()

    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    lock_path = DATA_ROOT / ".agents.lock"
    with lock_path.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another Agents reports stage is already active") from exc
        if args.render_run:
            print(_render_run(args.render_run))
            return 0
        prepared_result = _prepare()
        if args.probe:
            print(json.dumps(_probe(prepared_result), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        _print_agent_handoff(prepared_result)
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Agents reports failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
