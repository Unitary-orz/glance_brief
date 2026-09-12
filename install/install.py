#!/usr/bin/env python3
"""glance_brief agent-facing installer.

Mechanical installer only. It copies project-owned files into a runtime's
official directories, records the installed state, verifies it, and can remove
only what it owns. It deliberately does NOT create, modify, or delete Cron
jobs; the installing agent does that with the runtime's own job interface
(Hermes `cronjob`), using the job suggestions printed by `install`.

Actions:
    install   --runtime hermes [--components a,b] [--prefix DIR] [--dry-run]
    verify    --runtime hermes [--prefix DIR]
    doctor    --runtime hermes [--prefix DIR]
    uninstall --runtime hermes [--prefix DIR] [--dry-run]

Semantics:
    - install is idempotent; re-running it updates project-owned files and
      preserves user config/state/output under the runtime data dir.
    - verify checks that the installation is complete and wired (manifest,
      entry points, lib hashes, config files, cron wiring).
    - doctor checks runtime health: entry points compile, config parses,
      external skills and deps exist, cron jobs are wired, and the latest
      report output is fresh. It never fetches data or sends anything.
    - uninstall removes only files listed in the installed manifest and
      reports which jobs to detach. User config is preserved by default.
    - No third-party dependencies: stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import py_compile
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = Path(__file__).resolve().parent / "install-manifest.json"
INSTALL_MANIFEST_NAME = "install-manifest.json"

# Report entry points are thin runtime adapters around the shared core.  Source
# acquisition is configured through the core's bounded json_file/command_json
# drivers; the wrappers never bypass resolver or deterministic rendering.
REPORT_ENTRYPOINT_TEMPLATE = """#!/usr/bin/env python3
\"\"\"Installed strict report entry point for glance_brief.\"\"\"
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPORT_ID = "__REPORT_ID__"
HERE = Path(__file__).resolve().parent
HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(HERE.parents[1]))).expanduser()
DATA_DIR = HERMES_HOME / "data" / "glance-brief"
LIB_DIR = HERE / "lib"
sys.path.insert(0, str(LIB_DIR))

from glance_brief.cli import run_pipeline

config = Path(
    os.environ.get("GLANCE_BRIEF_CONFIG", str(DATA_DIR / "config" / "brief.json"))
).expanduser()
if not config.is_file():
    print(
        f"glance_brief configuration missing: {config}; copy and customize brief.example.json",
        file=sys.stderr,
    )
    raise SystemExit(2)

output_override = os.environ.get("GLANCE_BRIEF_OUTPUT_DIR")
if output_override:
    output = Path(output_override).expanduser()
else:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    output = DATA_DIR / "output" / REPORT_ID / stamp

model_path_value = os.environ.get("GLANCE_BRIEF_MODEL_RESPONSE")
model_response = Path(model_path_value).expanduser() if model_path_value else None


def invoke_model(prompt: str):
    executable = os.environ.get("GLANCE_BRIEF_HERMES", "hermes")
    model = os.environ.get("GLANCE_BRIEF_MODEL")
    provider = os.environ.get("GLANCE_BRIEF_PROVIDER")
    reasoning = os.environ.get("GLANCE_BRIEF_REASONING")
    timeout = float(os.environ.get("GLANCE_BRIEF_TIMEOUT", "600"))
    argv = [
        executable, "chat", "-q", prompt,
        "--toolsets", "safe",
        "--ignore-rules",
        "--source", "tool",
        "--max-turns", "1",
        "--quiet",
    ]
    if model:
        argv.extend(["--model", model])
    if provider:
        argv.extend(["--provider", provider])
    if reasoning:
        argv.extend(["--reasoning", reasoning])
    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
            shell=False,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Hermes model call timed out after {timeout:g}s") from exc
    except OSError as exc:
        raise RuntimeError(f"could not start Hermes model adapter: {exc}") from exc
    usage = {
        "mode": "hermes-runtime-adapter",
        "model": model,
        "provider": provider,
        "reasoning": reasoning,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "returncode": completed.returncode,
    }
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"Hermes model adapter exited with {completed.returncode}: {detail}")
    return completed.stdout, usage


args = argparse.Namespace(
    config=config,
    report=REPORT_ID,
    output_dir=output,
    model_response=model_response,
    date=os.environ.get("GLANCE_BRIEF_DATE"),
)
try:
    report_path = run_pipeline(
        args,
        model_runner=None if model_response is not None else invoke_model,
    )
except Exception as exc:
    print(f"glance_brief Hermes runtime error: {exc}", file=sys.stderr)
    raise SystemExit(1)

sys.stdout.write(report_path.read_text(encoding="utf-8"))
"""


def report_entrypoint(report_id: str) -> str:
    return REPORT_ENTRYPOINT_TEMPLATE.replace("__REPORT_ID__", report_id)


PREVIEW_FLAT_ENTRYPOINT_TEMPLATE = """#!/usr/bin/env python3
\"\"\"Installed flat wrapper for the V2 Preview semantic handoff entry point.\"\"\"
from __future__ import annotations

import os
import runpy
from pathlib import Path

RUNTIME_ROOT = Path(__file__).resolve().parent
HERMES_HOME = RUNTIME_ROOT.parents[1]
os.environ.setdefault("HERMES_HOME", str(HERMES_HOME))
os.environ.setdefault("GLANCE_BRIEF_PREVIEW_ROOT", str(RUNTIME_ROOT))
runpy.run_path(
    str(RUNTIME_ROOT / "entrypoints" / "__PREVIEW_ENTRYPOINT__"),
    run_name="__main__",
)
"""


def preview_flat_entrypoint(entrypoint: str) -> str:
    return PREVIEW_FLAT_ENTRYPOINT_TEMPLATE.replace("__PREVIEW_ENTRYPOINT__", entrypoint)


ENTRYPOINT_AGENTS_REPORT = report_entrypoint("agents-report")
ENTRYPOINT_NOON_NEWS = report_entrypoint("noon-news")

ENTRYPOINT_QUALITY_CHECK = """#!/usr/bin/env python3
\"\"\"Quality-check entry point for the installed glance-brief agents report.\"\"\"
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(HERE.parents[1]))).expanduser()
MODULE_DIR = HERE / "lib" / "agents-report"
DATA_DIR = HERMES_HOME / "data" / "glance-brief"

os.environ.setdefault("AGENTS_RADAR_QUALITY_MODULE_DIR", str(MODULE_DIR))
os.environ.setdefault("AGENTS_RADAR_QUALITY_CONFIG", str(DATA_DIR / "config" / "agents_radar_quality.json"))
sys.path.insert(0, str(MODULE_DIR))
runpy.run_path(str(MODULE_DIR / "agents_radar_quality_check.py"), run_name="__main__")
"""

ENTRYPOINT_CODEXRADAR = """#!/usr/bin/env python3
\"\"\"Standalone CodexRadar renderer for the installed glance-brief runtime.\"\"\"
from __future__ import annotations

import os
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(HERE.parents[1]))).expanduser()
MODULE_DIR = HERE / "lib" / "agents-report"
DATA_DIR = HERMES_HOME / "data" / "glance-brief"

os.environ.setdefault("CODEXRADAR_CONFIG", str(DATA_DIR / "config" / "codexradar_watch.json"))
runpy.run_path(str(MODULE_DIR / "codexradar_efficiency.py"), run_name="__main__")
"""

ENTRYPOINT_GLANCE_BRIEF = """#!/usr/bin/env python3
\"\"\"Installed command-line entry point for glance_brief.\"\"\"
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB_DIR = HERE / "lib"
sys.path.insert(0, str(LIB_DIR))

from glance_brief.cli import main

raise SystemExit(main())
"""

ENTRYPOINTS = {
    "glance-brief.py": ENTRYPOINT_GLANCE_BRIEF,
    "agents-report.py": ENTRYPOINT_AGENTS_REPORT,
    "noon-news.py": ENTRYPOINT_NOON_NEWS,
    "agents-quality-check.py": ENTRYPOINT_QUALITY_CHECK,
    "codexradar.py": ENTRYPOINT_CODEXRADAR,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def check_runtime_config(path: Path, components: list[str], schema_version: int) -> tuple[bool, str]:
    """Validate the minimum installer/runtime boundary without importing the core."""
    if not path.is_file():
        return False, f"missing {path}; create it from the installed example"
    try:
        config = load_json(path)
    except (OSError, ValueError) as exc:
        return False, f"invalid {path}: {exc}"
    reports = config.get("reports")
    valid = (
        config.get("schema_version") == schema_version
        and isinstance(reports, dict)
        and all(component in reports for component in components)
    )
    if not valid:
        return False, f"must be schema {schema_version} and configure every installed report"
    return True, str(path)


def hermes_home(prefix: str | None) -> Path:
    if prefix:
        return Path(prefix).expanduser()
    return Path(__import__("os").environ.get("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser()


def check_python_deps(deps: list[str]) -> list[dict]:
    missing = []
    for dep in deps:
        name = dep.split(">=")[0].split("==")[0].strip()
        if importlib.util.find_spec(name) is None:
            missing.append({"dependency": dep, "check": "python-import"})
    return missing


def check_external_skills(skills: dict, home: Path) -> list[dict]:
    missing = []
    for name, spec in skills.items():
        expected = home / "skills" / name / spec["expected_script"]
        if not expected.exists():
            missing.append({
                "skill": name,
                "expected": str(expected),
                "source_hint": spec["source_hint"],
            })
    return missing


def plan_core_copy(manifest: dict) -> list[tuple[Path, Path]]:
    spec = manifest["core"]
    src_dir = REPO_ROOT / spec["source"]
    if not src_dir.is_dir():
        raise SystemExit(f"ERROR: core source missing: {src_dir}")
    destination = Path(spec["destination"])
    pairs = []
    for source in sorted(src_dir.rglob("*")):
        if source.is_file() and "__pycache__" not in source.parts:
            pairs.append((source, destination / source.relative_to(src_dir)))
    return pairs


def plan_lib_copy(manifest: dict, components: list[str]) -> list[tuple[Path, Path]]:
    pairs = []
    for comp in components:
        spec = manifest["components"][comp]
        src_dir = REPO_ROOT / spec["lib_source"]
        if not src_dir.is_dir():
            raise SystemExit(f"ERROR: lib_source missing: {src_dir}")
        for py in sorted(src_dir.glob("*.py")):
            pairs.append((py, Path("lib") / comp / py.name))
    return pairs


def plan_preview_copy(manifest: dict, components: list[str]) -> list[tuple[Path, Path]]:
    spec = manifest["preview_runtime"]
    lib_source = REPO_ROOT / spec["lib_source"]
    if not lib_source.is_dir():
        raise SystemExit(f"ERROR: preview lib source missing: {lib_source}")
    pairs = [
        (source, Path("lib") / "glance_brief" / source.relative_to(lib_source))
        for source in sorted(lib_source.rglob("*"))
        if source.is_file() and "__pycache__" not in source.parts
    ]
    for component in components:
        entry = spec["entrypoints"].get(component)
        prompt = spec["cron_prompts"].get(component)
        if not isinstance(entry, dict) or not isinstance(prompt, str):
            raise SystemExit(f"ERROR: preview runtime mapping missing for {component}")
        source = REPO_ROOT / entry["source"]
        prompt_source = REPO_ROOT / prompt
        if not source.is_file():
            raise SystemExit(f"ERROR: preview entrypoint source missing: {source}")
        if not prompt_source.is_file():
            raise SystemExit(f"ERROR: preview Cron prompt missing: {prompt_source}")
        pairs.append((source, Path(entry["installed"])))
        pairs.append((prompt_source, Path("cron-prompts") / Path(prompt).name))
    return pairs


def is_preview_runtime(runtime_spec: dict) -> bool:
    return runtime_spec.get("kind") == "preview-agent-handoff"


def runtime_entrypoint_names(installed: dict | None) -> set[str]:
    if not installed:
        return set(ENTRYPOINTS)
    names = {installed.get("core_entrypoint", "")}
    names.update(installed.get("entrypoints", {}).values())
    for item in installed.get("owned_files", []):
        path = item.get("path")
        if isinstance(path, str) and not path.startswith("lib/") and path.endswith(".py"):
            names.add(Path(path).name)
    return {name for name in names if name}


def repository_provenance() -> dict[str, object]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return {"source_revision": None, "source_dirty": None}
    return {"source_revision": revision, "source_dirty": bool(status)}


def preview_job_suggestions(manifest: dict, components: list[str], runtime_spec: dict) -> dict[str, dict]:
    preview = manifest["preview_runtime"]
    script_dir = Path(runtime_spec["scripts_dir"]).name
    jobs = {}
    for component in components:
        entry = preview["entrypoints"][component]
        prompt_path = REPO_ROOT / preview["cron_prompts"][component]
        required_environment = [
            "GLANCE_BRIEF_PREVIEW_CONFIG",
            "GLANCE_BRIEF_PREVIEW_PREFETCH",
            "GLANCE_BRIEF_PREVIEW_MODEL",
            "GLANCE_BRIEF_PREVIEW_PROVIDER",
            "GLANCE_BRIEF_PREVIEW_REASONING",
        ]
        if component == "agents-report":
            required_environment.append("GLANCE_BRIEF_PREVIEW_PUBLICATION_DIR")
        jobs[component] = {
            "name": component,
            "script": f"{script_dir}/{entry['cron_entrypoint']}",
            "no_agent": False,
            "prompt": prompt_path.read_text(encoding="utf-8"),
            "default_schedule": manifest["components"][component]["default_schedule"],
            "required_environment": required_environment,
        }
    return jobs


def single_writer_conflicts(manifest: dict, jobs: list[dict], runtime_spec: dict) -> list[dict]:
    if not is_preview_runtime(runtime_spec):
        return []
    preview = manifest["preview_runtime"]["entrypoints"]
    conflicts = []
    for component, component_spec in manifest["components"].items():
        writer_names = {component_spec["entrypoint"]}
        if component in preview:
            writer_names.add(preview[component]["cron_entrypoint"])
        active = [
            {
                "id": job.get("id"),
                "name": job.get("name"),
                "script": job.get("script"),
                "deliver": job.get("deliver"),
            }
            for job in jobs
            if job.get("enabled", True) is not False
            and Path(job.get("script") or "").name in writer_names
        ]
        if len(active) > 1:
            conflicts.append({"component": component, "writers": active})
    return conflicts


def render_entrypoints(manifest: dict, components: list[str]) -> list[tuple[str, str]]:
    files = [(manifest["core"]["entrypoint"], ENTRYPOINTS[manifest["core"]["entrypoint"]])]
    for comp in components:
        files.append((manifest["components"][comp]["entrypoint"], ENTRYPOINTS[manifest["components"][comp]["entrypoint"]]))
    for name, spec in manifest["utility_entrypoints"].items():
        if spec["lib_component"] in components:
            files.append((name, ENTRYPOINTS[name]))
    return files


def cmd_install(args) -> int:
    manifest = load_json(MANIFEST_PATH)
    home = hermes_home(args.prefix)
    rt = manifest["runtime_adapters"][args.runtime]
    preview_runtime = is_preview_runtime(rt)
    scripts_root = home / rt["scripts_dir"]
    data_root = home / rt["data_dir"]

    components = args.components or list(manifest["components"].keys())
    unknown = [c for c in components if c not in manifest["components"]]
    if unknown:
        raise SystemExit(f"ERROR: unknown components: {', '.join(unknown)}")

    plan = {
        "scripts_dir": str(scripts_root),
        "data_dir": str(data_root),
        "runtime_kind": rt.get("kind", "formal-batch"),
        **repository_provenance(),
    }
    changes = {
        "core_files": [],
        "lib_files": [],
        "runtime_files": [],
        "entrypoints": [],
        "config_files": [],
        "dirs": [],
    }

    if preview_runtime:
        core_pairs = []
        lib_pairs = []
        runtime_pairs = plan_preview_copy(manifest, components)
        entry_files = [
            (
                manifest["preview_runtime"]["entrypoints"][component]["cron_entrypoint"],
                preview_flat_entrypoint(
                    Path(manifest["preview_runtime"]["entrypoints"][component]["installed"]).name
                ),
            )
            for component in components
        ]
    else:
        core_pairs = plan_core_copy(manifest)
        lib_pairs = plan_lib_copy(manifest, components)
        runtime_pairs = core_pairs + lib_pairs
        entry_files = render_entrypoints(manifest, components)

    # dirs
    for sub in ("config", "state", "cache", "output"):
        changes["dirs"].append(str(data_root / sub))

    core_rels = {rel for _src, rel in core_pairs}
    # project-owned runtime files (always updated on re-install)
    for src, rel in runtime_pairs:
        changes["runtime_files"].append({"src": str(src), "dst": str(scripts_root / rel)})
        if not preview_runtime and rel in core_rels:
            changes["core_files"].append(str(scripts_root / rel))
        elif str(rel).startswith("lib/"):
            changes["lib_files"].append({"src": str(src), "dst": str(scripts_root / rel)})

    # flat scheduler entrypoints (always updated)
    for name, _content in entry_files:
        changes["entrypoints"].append(str(scripts_root / name))

    # default configs (only when target missing)
    if preview_runtime:
        preview_spec = manifest["preview_runtime"]
        config_template = preview_spec["config_template"]
        config_target = preview_spec["config_target"]
    else:
        core_config = manifest["core"]
        config_template = core_config["config_template"]
        config_target = core_config["config_target"]
    core_config_dst = data_root / "config" / config_target
    if not core_config_dst.exists():
        changes["config_files"].append({
            "template": config_template,
            "dst": str(core_config_dst),
        })
    if not preview_runtime:
        for comp in components:
            for target, template_rel in manifest["components"][comp].get("config_templates", {}).items():
                dst = data_root / "config" / target
                if not dst.exists():
                    changes["config_files"].append({"template": template_rel, "dst": str(dst)})

    if args.dry_run:
        print(json.dumps({
            "action": "install",
            "dry_run": True,
            "project_version": manifest["project_version"],
            "components": components,
            "plan": plan,
            "changes": changes,
        }, ensure_ascii=False, indent=2))
        return 0

    scripts_root.mkdir(parents=True, exist_ok=True)
    (data_root / "config").mkdir(parents=True, exist_ok=True)
    for d in changes["dirs"]:
        Path(d).mkdir(parents=True, exist_ok=True)

    for src, rel in runtime_pairs:
        dst = scripts_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    for name, content in entry_files:
        dst = scripts_root / name
        dst.write_text(content, encoding="utf-8")
        dst.chmod(0o755)
    for item in changes["config_files"]:
        shutil.copy2(REPO_ROOT / item["template"], Path(item["dst"]))

    # dependency report (warnings only; agent decides whether to install)
    dep_missing = check_python_deps(manifest.get("python_deps", []))
    skill_missing = check_external_skills(manifest.get("external_skills", {}), home)

    owned = []
    for src, rel in runtime_pairs:
        owned.append({"path": str(rel), "sha256": sha256(src)})
    for name, _content in entry_files:
        dst = scripts_root / name
        owned.append({"path": name, "sha256": sha256(dst)})

    if preview_runtime:
        preview_spec = manifest["preview_runtime"]
        jobs = preview_job_suggestions(manifest, components, rt)
        installed_entrypoints = {
            component: preview_spec["entrypoints"][component]["cron_entrypoint"]
            for component in components
        }
        user_config_files = [f"config/{preview_spec['config_target']}"]
        runtime_config_file = f"config/{preview_spec['runtime_config_target']}"
    else:
        jobs = {
            comp: {
                "name": comp,
                "script": f"{Path(rt['scripts_dir']).name}/{manifest['components'][comp]['entrypoint']}",
                "no_agent": True,
                "default_schedule": manifest["components"][comp]["default_schedule"],
            }
            for comp in components
        }
        installed_entrypoints = {
            comp: manifest["components"][comp]["entrypoint"] for comp in components
        }
        user_config_files = [
            f"config/{manifest['core']['config_target']}",
            *[
                f"config/{name}"
                for comp in components
                for name in manifest["components"][comp].get("config_templates", {})
            ],
        ]
        runtime_config_file = f"config/{manifest['core']['runtime_config_target']}"

    installed = {
        "schema_version": 2,
        "project": manifest["project"],
        "project_version": manifest["project_version"],
        "runtime": args.runtime,
        "runtime_kind": rt.get("kind", "formal-batch"),
        "config_schema_version": rt["config_schema_version"],
        "components": components,
        "scripts_dir": rt["scripts_dir"],
        "data_dir": rt["data_dir"],
        "core_entrypoint": None if preview_runtime else manifest["core"]["entrypoint"],
        "entrypoints": installed_entrypoints,
        "jobs": jobs,
        "owned_files": owned,
        "user_config_files": user_config_files,
        "runtime_config_file": runtime_config_file,
        **repository_provenance(),
    }
    manifest_dst = data_root / INSTALL_MANIFEST_NAME
    manifest_dst.write_text(json.dumps(installed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = {
        "action": "install",
        "ok": True,
        "runtime": args.runtime,
        "project_version": manifest["project_version"],
        "components": components,
        "installed_manifest": str(manifest_dst),
        "missing_python_deps": dep_missing,
        "missing_external_skills": skill_missing,
        "required_setup": [
            {
                "action": "create_runtime_config",
                "template": str(data_root / "config" / config_target),
                "target": str(data_root / installed["runtime_config_file"]),
            },
            *([
                {
                    "action": "configure_scheduler_environment",
                    "variables": [
                        "GLANCE_BRIEF_PREVIEW_CONFIG",
                        "GLANCE_BRIEF_PREVIEW_PREFETCH",
                        "GLANCE_BRIEF_PREVIEW_PUBLICATION_DIR",
                        "GLANCE_BRIEF_PREVIEW_MODEL",
                        "GLANCE_BRIEF_PREVIEW_PROVIDER",
                        "GLANCE_BRIEF_PREVIEW_REASONING",
                    ],
                    "note": "Set deployment-specific values in the scheduler process; no live paths or credentials are stored by the installer.",
                }
            ] if preview_runtime else []),
        ],
        "jobs_to_create": list(installed["jobs"].values()),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_verify(args) -> int:
    manifest = load_json(MANIFEST_PATH)
    home = hermes_home(args.prefix)
    rt = manifest["runtime_adapters"][args.runtime]
    scripts_root = home / rt["scripts_dir"]
    data_root = home / rt["data_dir"]

    checks = []

    def add(name: str, ok: bool, detail: str):
        checks.append({"check": name, "ok": ok, "detail": detail})

    # installed manifest
    installed_path = data_root / INSTALL_MANIFEST_NAME
    if installed_path.exists():
        installed = load_json(installed_path)
        add("installed-manifest", True, str(installed_path))
    else:
        installed = None
        add("installed-manifest", False, "not installed; run install first")

    # only entry points owned by this installed component set
    if installed:
        expected_entrypoints = sorted(
            {
                item["path"]
                for item in installed.get("owned_files", [])
                if isinstance(item.get("path"), str) and not item["path"].startswith("lib/")
            }
        )
    elif is_preview_runtime(rt):
        expected_entrypoints = sorted(
            entry["cron_entrypoint"]
            for entry in manifest["preview_runtime"]["entrypoints"].values()
        )
    else:
        expected_entrypoints = [manifest["core"]["entrypoint"]]
    for name in expected_entrypoints:
        p = scripts_root / name
        add(f"entrypoint:{name}", p.exists() and p.is_file(), str(p))

    # every owned file must exist and match its recorded source/runtime hash
    if installed:
        for owned in installed.get("owned_files", []):
            live = scripts_root / owned["path"]
            if not live.exists():
                add(f"file:{owned['path']}", False, "missing")
                continue
            live_sha = sha256(live)
            expected_sha = owned.get("sha256")
            ok = live_sha == expected_sha
            kind = "lib" if owned["path"].startswith("lib/") else "file"
            add(
                f"{kind}:{owned['path']}",
                ok,
                "match" if ok else f"hash drift {live_sha[:12]} != {str(expected_sha)[:12]}",
            )

    # installed templates plus the user-authored runtime config
    if installed:
        for rel in installed.get("user_config_files", []):
            p = data_root / rel
            add(f"config:{rel}", p.exists(), str(p))
        runtime_rel = installed.get("runtime_config_file")
        if not isinstance(runtime_rel, str) or not runtime_rel:
            add("runtime-config", False, "installed manifest does not declare runtime_config_file")
        else:
            valid, detail = check_runtime_config(
                data_root / runtime_rel,
                installed.get("components", []),
                int(installed.get("config_schema_version", rt.get("config_schema_version", 2))),
            )
            add("runtime-config", valid, detail)

    # cron wiring: a job whose script resolves to our installed entrypoints.
    # Hermes job `script` is relative to $HERMES_HOME/scripts/.
    jobs_file = home / rt["jobs_file"]
    if jobs_file.exists():
        try:
            jobs = load_json(jobs_file).get("jobs", [])
            scripts_base = home / "scripts"
            known_entrypoints = runtime_entrypoint_names(installed)
            wired = []
            for job in jobs:
                script = job.get("script", "")
                if not script:
                    continue
                entry_name = Path(script).name
                if entry_name in known_entrypoints and (scripts_base / script).exists():
                    wired.append({"job_id": job.get("id"), "name": job.get("name"), "script": script})
            add("cron-wiring", bool(wired), json.dumps(wired, ensure_ascii=False))
            conflicts = single_writer_conflicts(manifest, jobs, rt)
            add(
                "single-writer",
                not conflicts,
                "one active writer per report"
                if not conflicts
                else json.dumps(conflicts, ensure_ascii=False),
            )
        except (OSError, ValueError) as exc:
            add("cron-wiring", False, f"cannot read {jobs_file}: {exc}")
    else:
        add("cron-wiring", False, f"jobs file not found: {jobs_file}")

    ok = all(c["ok"] for c in checks)
    result = {"action": "verify", "ok": ok, "runtime": args.runtime, "checks": checks}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def cmd_doctor(args) -> int:
    """Component completeness + runtime hints for an installing/updating agent.

    Statuses: 'ok' (complete), 'warn' (optional hint: missing external skill,
    stale output, job error), 'error' (installation is broken). Warnings are
    hints only and do not fail the check; exit code is 1 only when a hard
    error is present. Read-only: never fetches data and never sends anything.
    """
    manifest = load_json(MANIFEST_PATH)
    home = hermes_home(args.prefix)
    rt = manifest["runtime_adapters"][args.runtime]
    scripts_root = home / rt["scripts_dir"]
    data_root = home / rt["data_dir"]

    components: dict[str, dict] = {}
    warnings: list[str] = []
    errors: list[str] = []

    def emit(group: str, name: str, status: str, detail: str):
        components.setdefault(group, {})[name] = {"status": status, "detail": detail}
        if status == "error":
            errors.append(f"{group}.{name}: {detail}")
        elif status == "warn":
            warnings.append(f"{group}.{name}: {detail}")

    installed_path = data_root / INSTALL_MANIFEST_NAME
    installed = load_json(installed_path) if installed_path.exists() else None
    if installed is None:
        emit("runtime", "installed-manifest", "error", "not installed; run install first")

    # per-component completeness: entry point, lib hashes, config
    if installed:
        entry_map = {spec["entrypoint"]: comp for comp, spec in manifest["components"].items()}
        entry_map.update({name: spec["lib_component"] for name, spec in manifest["utility_entrypoints"].items()})
        lib_hashes = {f["path"]: f["sha256"] for f in installed.get("owned_files", [])}

        for comp in installed.get("components", []):
            group = f"component:{comp}"
            # entry point
            ep_name = installed.get("entrypoints", {}).get(comp)
            ep = scripts_root / ep_name if ep_name else None
            if ep and ep.exists():
                try:
                    py_compile.compile(str(ep), doraise=True)
                    emit(group, "entrypoint", "ok", ep_name)
                except py_compile.PyCompileError as exc:
                    emit(group, "entrypoint", "error", f"{ep_name}: {exc}")
            else:
                emit(group, "entrypoint", "error", f"missing {ep_name}")
            # lib hashes
            for path, sha in lib_hashes.items():
                if not path.startswith(f"lib/{comp}/"):
                    continue
                live = scripts_root / path
                if not live.exists():
                    emit(group, path, "error", "missing")
                    continue
                ok = sha256(live) == sha
                emit(group, path, "ok" if ok else "error", "match" if ok else "hash drift")
            # config templates
            for cfg_name in manifest["components"][comp].get("config_templates", {}):
                p = data_root / "config" / cfg_name
                if not p.exists():
                    emit(group, f"config:{cfg_name}", "warn", "missing default config (seeded at install)")
                    continue
                try:
                    json.loads(p.read_text(encoding="utf-8"))
                    emit(group, f"config:{cfg_name}", "ok", "parses")
                except (OSError, ValueError) as exc:
                    emit(group, f"config:{cfg_name}", "error", f"invalid JSON: {exc}")

        runtime_rel = installed.get("runtime_config_file")
        if not isinstance(runtime_rel, str) or not runtime_rel:
            emit("runtime", "runtime-config", "error", "installed manifest does not declare runtime_config_file")
        else:
            valid, detail = check_runtime_config(
                data_root / runtime_rel,
                installed.get("components", []),
                int(installed.get("config_schema_version", rt.get("config_schema_version", 2))),
            )
            emit("runtime", "runtime-config", "ok" if valid else "error", detail)

    # dependencies and external skills (shared, hints)
    for dep in manifest.get("python_deps", []):
        pkg = dep.split(">=")[0].split("==")[0].strip()
        ok = importlib.util.find_spec(pkg) is not None
        emit("dependencies", dep, "ok" if ok else "warn", "importable" if ok else "missing; pip install it")
    for name, spec in manifest.get("external_skills", {}).items():
        p = home / "skills" / name / spec["expected_script"]
        emit("dependencies", f"skill:{name}", "ok" if p.exists() else "warn",
             str(p) if p.exists() else f"missing; obtain from {spec['source_hint']}")

    # runtime hints: cron wiring, job status, output freshness
    jobs_file = home / rt["jobs_file"]
    wired = []
    if jobs_file.exists():
        try:
            jobs = load_json(jobs_file).get("jobs", [])
            scripts_base = home / "scripts"
            known_entrypoints = runtime_entrypoint_names(installed)
            for job in jobs:
                script = job.get("script", "")
                if script and Path(script).name in known_entrypoints and (scripts_base / script).exists():
                    wired.append(job)
            conflicts = single_writer_conflicts(manifest, jobs, rt)
            emit(
                "runtime",
                "single-writer",
                "error" if conflicts else "ok",
                "one active writer per report"
                if not conflicts
                else json.dumps(conflicts, ensure_ascii=False),
            )
        except (OSError, ValueError) as exc:
            emit("runtime", "cron-jobs", "error", f"cannot read {jobs_file}: {exc}")
    else:
        emit("runtime", "cron-jobs", "warn", f"no jobs file at {jobs_file}; jobs not created yet")

    if wired:
        emit("runtime", "cron-wiring", "ok", f"{len(wired)} job(s) wired")
        for job in wired:
            jid = job.get("id")
            status = job.get("last_status", "unknown")
            ok = status in (None, "ok", "unknown")
            emit("runtime", f"job:{jid}", "ok" if ok else "warn",
                 f"{job.get('name')} last_status={status}" + (f" error={str(job.get('last_error'))[:160]}" if job.get("last_error") else ""))
            deliver = job.get("deliver") or ""
            if deliver:
                emit("runtime", f"deliver:{jid}", "ok", deliver)
            else:
                emit("runtime", f"deliver:{jid}", "warn",
                     "delivery target not configured; ask the user which platform and target to deliver to "
                     "(e.g. feishu:<chat_id>, telegram:<chat_id>, or origin) and set the job deliver field")
    else:
        emit("runtime", "cron-wiring", "warn", "no jobs wired to glance-brief entry points")

    if installed:
        now = datetime.now().astimezone().timestamp()
        for comp in installed.get("components", []):
            out_dir = data_root / "output" / comp
            files = sorted(out_dir.glob("*/report.md"), key=lambda p: p.stat().st_mtime) if out_dir.is_dir() else []
            if not files:
                emit("runtime", f"latest-output:{comp}", "warn", f"no verified report under {out_dir}")
                continue
            latest = files[-1]
            age_hours = max(0.0, (now - latest.stat().st_mtime) / 3600)
            fresh = age_hours <= 36
            emit(
                "runtime",
                f"latest-output:{comp}",
                "ok" if fresh else "warn",
                f"{latest} (age={age_hours:.1f}h)" + ("; check the scheduled job" if not fresh else ""),
            )

    result = {
        "action": "doctor",
        "ok": not errors,
        "runtime": args.runtime,
        "components": components,
        "warnings": warnings,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


def cmd_uninstall(args) -> int:
    home = hermes_home(args.prefix)
    rt = load_json(MANIFEST_PATH)["runtime_adapters"][args.runtime]
    data_root = home / rt["data_dir"]
    installed_path = data_root / INSTALL_MANIFEST_NAME
    if not installed_path.exists():
        print(json.dumps({"action": "uninstall", "ok": True, "note": "no installed manifest; nothing to remove"}, ensure_ascii=False))
        return 0

    installed = load_json(installed_path)
    scripts_root = home / installed["scripts_dir"]
    owned = [scripts_root / f["path"] for f in installed.get("owned_files", [])]

    # jobs to detach: Agent removes them via the runtime job interface.
    # Hermes job `script` is relative to $HERMES_HOME/scripts/.
    jobs_file = home / rt["jobs_file"]
    detach = []
    if jobs_file.exists():
        try:
            jobs = load_json(jobs_file).get("jobs", [])
            scripts_base = home / "scripts"
            known_entrypoints = runtime_entrypoint_names(installed)
            for job in jobs:
                script = job.get("script", "")
                if not script:
                    continue
                entry_name = Path(script).name
                if entry_name in known_entrypoints and (scripts_base / script).exists():
                    detach.append({"job_id": job.get("id"), "name": job.get("name"), "script": script})
        except (OSError, ValueError):
            pass

    if args.dry_run:
        print(json.dumps({
            "action": "uninstall", "dry_run": True,
            "would_remove_files": [str(p) for p in owned],
            "would_keep_config": str(data_root),
            "jobs_to_detach": detach,
        }, ensure_ascii=False, indent=2))
        return 0

    removed, missing = [], []
    for p in owned:
        if p.exists():
            p.unlink()
            removed.append(str(p))
        else:
            missing.append(str(p))
    # prune empty lib dirs
    for comp in installed.get("components", []):
        lib_dir = scripts_root / "lib" / comp
        if lib_dir.exists() and not any(lib_dir.iterdir()):
            lib_dir.rmdir()
    try:
        (scripts_root / "lib").rmdir()
    except OSError:
        pass

    result = {
        "action": "uninstall", "ok": True,
        "removed_files": removed,
        "already_missing": missing,
        "preserved_config": str(data_root),
        "jobs_to_detach": detach,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="glance_brief installer (agent-facing, stdlib only)")
    sub = parser.add_subparsers(dest="action", required=True)

    p_install = sub.add_parser("install", help="install or update project-owned files")
    p_install.add_argument("--runtime", default="hermes", choices=["hermes", "hermes-preview"])
    p_install.add_argument("--components", default="", help="comma-separated components")
    p_install.add_argument("--prefix", default="", help="runtime home (default: $HERMES_HOME or ~/.hermes)")
    p_install.add_argument("--dry-run", action="store_true")

    p_verify = sub.add_parser("verify", help="verify installed state")
    p_verify.add_argument("--runtime", default="hermes", choices=["hermes", "hermes-preview"])
    p_verify.add_argument("--prefix", default="")

    p_doctor = sub.add_parser("doctor", help="runtime health check (read-only)")
    p_doctor.add_argument("--runtime", default="hermes", choices=["hermes", "hermes-preview"])
    p_doctor.add_argument("--prefix", default="")

    p_uninstall = sub.add_parser("uninstall", help="remove project-owned files (keeps user config)")
    p_uninstall.add_argument("--runtime", default="hermes", choices=["hermes", "hermes-preview"])
    p_uninstall.add_argument("--prefix", default="")
    p_uninstall.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    if args.action == "install":
        args.components = [
            component.strip()
            for component in args.components.split(",")
            if component.strip()
        ]
        return cmd_install(args)
    if args.action == "verify":
        return cmd_verify(args)
    if args.action == "doctor":
        return cmd_doctor(args)
    if args.action == "uninstall":
        return cmd_uninstall(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
