#!/usr/bin/env python3
"""Single-Cron V2 Noon wrapper: prepare evidence, then deterministically render.

Default mode is the Hermes Cron pre-run stage.  It fetches real sources,
assembles a lean candidate payload, and prints the semantic task for the Cron
agent.  The Cron agent writes only the model-owned JSON fields, then calls this
same wrapper with --render-run.  No nested Hermes/model process exists here.
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
    os.environ.get("GLANCE_BRIEF_PREVIEW_ROOT", str(Path(__file__).resolve().parents[1]))
).expanduser()
LIB_ROOT = RUNTIME_ROOT / "lib"
DATA_ROOT = Path(
    os.environ.get("GLANCE_BRIEF_PREVIEW_DATA", str(HERMES_HOME / "data" / "glance-brief-v2"))
).expanduser()
PREFETCH = Path(
    os.environ.get("GLANCE_BRIEF_PREVIEW_PREFETCH", str(HERMES_HOME / "scripts" / "glance-brief" / "noon-news.py"))
).expanduser()
CONFIG = Path(
    os.environ.get("GLANCE_BRIEF_PREVIEW_CONFIG", str(DATA_ROOT / "config" / "brief-live.json"))
).expanduser()
SNAPSHOT = DATA_ROOT / "source-snapshot.json"
TZ = ZoneInfo("Asia/Shanghai")
REPORT = "noon-news"
MODEL = "MiniMax-M3"
PROVIDER = "minimax-cn"
REASONING = "low"

sys.path.insert(0, str(LIB_ROOT))
from glance_brief import adapters, cli, contracts  # noqa: E402


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


def _prefetch() -> dict:
    result = _run([sys.executable, str(PREFETCH)], timeout=240)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"prefetch exited {result.returncode}: {detail[:500]}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"prefetch returned malformed JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise RuntimeError("prefetch schema_version must be 1")
    return payload


def _prepare() -> dict:
    source_payload = _prefetch()
    _atomic_json(SNAPSHOT, source_payload)
    report_date = dt.datetime.now(TZ).date().isoformat()
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
    render_command = (
        f"{shlex.quote(sys.executable)} {shlex.quote(str(Path(__file__).resolve()))} "
        f"--render-run {shlex.quote(str(run_dir))}"
    )
    prepared = cli.load_json(run_dir / "prepared.json")
    prepared.update({
        "run_id": run_id,
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
    print("GLANCE_BRIEF_V2_SEMANTIC_HANDOFF")
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
        raise RuntimeError("render run directory is outside the isolated V2 runs root")
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
        raise RuntimeError("prepared report is not noon-news")
    if prepared.get("run_dir") != str(run_dir):
        raise RuntimeError("prepared run_dir does not match requested run")
    if prepared.get("semantic_output") != str(semantic_path):
        raise RuntimeError("prepared semantic output path does not match requested run")
    report_date = contracts.date(prepared.get("report_date"), "prepared.report_date")
    if report_date != run_dir.parent.name:
        raise RuntimeError("prepared report_date does not match run partition")
    if prepared.get("config_sha256") != _sha256(CONFIG):
        raise RuntimeError("V2 config changed after semantic preparation")
    if prepared.get("source_snapshot_sha256") != _sha256(SNAPSHOT):
        raise RuntimeError("source snapshot changed after semantic preparation")

    args = argparse.Namespace(
        config=CONFIG,
        report=REPORT,
        output_dir=run_dir,
        model_response=semantic_path,
        date=prepared.get("report_date"),
        stdout_report=False,
    )
    report_path = cli.render_prepared_pipeline(args)
    core_manifest = cli.load_json(run_dir / "manifest.json")
    usage = {
        "mode": "hermes-cron-agent-tool",
        "model": prepared.get("model"),
        "provider": prepared.get("provider"),
        "reasoning": prepared.get("reasoning"),
    }
    cli.write_json(run_dir / "usage.json", usage)
    cli.write_manifest(
        run_dir,
        report=REPORT,
        status="ok",
        extra={
            "config_sha256": _sha256(CONFIG),
            "model": prepared.get("model"),
            "provider": prepared.get("provider"),
            "reasoning": prepared.get("reasoning"),
            "mode": "hermes-cron-agent-tool",
            "report_date": prepared.get("report_date"),
            "resolved_generated_at": core_manifest.get("resolved_generated_at"),
            "prepared_at": prepared.get("prepared_at"),
            "report_plan_sha256": prepared.get("report_plan_sha256"),
            "source_snapshot_sha256": prepared.get("source_snapshot_sha256"),
        },
    )
    manifest = cli.load_json(run_dir / "manifest.json")
    if manifest.get("status") != "ok" or manifest.get("report") != REPORT:
        raise RuntimeError("V2 manifest does not describe a successful noon-news run")
    if not report_path.is_file():
        raise RuntimeError("V2 renderer succeeded without report.md")
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
    parser.add_argument("--probe", action="store_true", help="fetch and validate real candidates without a model call")
    parser.add_argument("--render-run", help="validate semantic JSON and render one prepared V2 run")
    args = parser.parse_args()

    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    lock_path = DATA_ROOT / ".noon.lock"
    with lock_path.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another V2 Noon stage is already active") from exc
        if args.render_run:
            print(_render_run(args.render_run))
            return 0
        prepared_result = _prepare()
        if args.probe:
            print(json.dumps(_probe(prepared_result), ensure_ascii=False, sort_keys=True))
            return 0
        _print_agent_handoff(prepared_result)
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError,
        RuntimeError,
        ValueError,
        json.JSONDecodeError,
        subprocess.TimeoutExpired,
        contracts.ContractError,
    ) as exc:
        print(f"V2 Noon runtime error: {exc}", file=sys.stderr)
        raise SystemExit(1)
