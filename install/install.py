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
    uninstall --runtime hermes [--prefix DIR] [--dry-run]

Semantics:
    - install is idempotent; re-running it updates project-owned files and
      preserves user config/state/output under the runtime data dir.
    - uninstall removes only files listed in the installed manifest and
      reports which jobs to detach. User config is preserved by default.
    - No third-party dependencies: stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = Path(__file__).resolve().parent / "install-manifest.json"
INSTALL_MANIFEST_NAME = "install-manifest.json"

# Adapter entry points are thin wrappers: they resolve the runtime home and
# config paths, then execute the matching library module with runpy.
ENTRYPOINT_AGENTS_REPORT = """#!/usr/bin/env python3
\"\"\"Hermes runtime entry point for the glance-brief agents report.\"\"\"
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
os.environ.setdefault("AGENTS_RADAR_COLLECTOR", str(MODULE_DIR / "agents-radar-daily.py"))
os.environ.setdefault("AGENTS_RADAR_OUTPUT_DIR", str(DATA_DIR / "output" / "agents-radar"))
os.environ.setdefault("AGENTS_RADAR_QUALITY_CONFIG", str(DATA_DIR / "config" / "agents_radar_quality.json"))
os.environ.setdefault("CODEXRADAR_CONFIG", str(DATA_DIR / "config" / "codexradar_watch.json"))
sys.path.insert(0, str(MODULE_DIR))
runpy.run_path(str(MODULE_DIR / "agents_radar_prefetch.py"), run_name="__main__")
"""

ENTRYPOINT_NOON_NEWS = """#!/usr/bin/env python3
\"\"\"Hermes runtime entry point for the glance-brief noon news report.\"\"\"
from __future__ import annotations

import os
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(HERE.parents[1]))).expanduser()
MODULE_DIR = HERE / "lib" / "noon-news"
SKILLS_DIR = HERMES_HOME / "skills"

os.environ.setdefault(
    "NEWS_AGGREGATOR_SCRIPT",
    str(SKILLS_DIR / "news-aggregator-skill" / "scripts" / "fetch_news.py"),
)
os.environ.setdefault(
    "NEWS_SUMMARY_SCRIPT",
    str(SKILLS_DIR / "news-summary" / "scripts" / "fetch_rss.py"),
)
runpy.run_path(str(MODULE_DIR / "noon_news_prefetch.py"), run_name="__main__")
"""

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

ENTRYPOINTS = {
    "agents-report.py": ENTRYPOINT_AGENTS_REPORT,
    "noon-news.py": ENTRYPOINT_NOON_NEWS,
    "agents-quality-check.py": ENTRYPOINT_QUALITY_CHECK,
    "codexradar.py": ENTRYPOINT_CODEXRADAR,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


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


def render_entrypoints(manifest: dict, components: list[str]) -> list[tuple[str, str]]:
    files = []
    for comp in components:
        files.append((manifest["components"][comp]["entrypoint"], ENTRYPOINTS[manifest["components"][comp]["entrypoint"]]))
    for name, spec in manifest["utility_entrypoints"].items():
        files.append((name, ENTRYPOINTS[name]))
    return files


def cmd_install(args) -> int:
    manifest = load_json(MANIFEST_PATH)
    home = hermes_home(args.prefix)
    rt = manifest["runtime_adapters"][args.runtime]
    scripts_root = home / rt["scripts_dir"]
    data_root = home / rt["data_dir"]

    components = args.components or list(manifest["components"].keys())
    unknown = [c for c in components if c not in manifest["components"]]
    if unknown:
        raise SystemExit(f"ERROR: unknown components: {', '.join(unknown)}")

    plan = {"scripts_dir": str(scripts_root), "data_dir": str(data_root)}
    changes = {"lib_files": [], "entrypoints": [], "config_files": [], "dirs": []}

    lib_pairs = plan_lib_copy(manifest, components)
    entry_files = render_entrypoints(manifest, components)

    # dirs
    for sub in ("config", "state", "cache", "output"):
        changes["dirs"].append(str(data_root / sub))

    # lib files (always updated on re-install)
    for src, rel in lib_pairs:
        changes["lib_files"].append({"src": str(src), "dst": str(scripts_root / rel)})

    # entrypoints (always updated)
    for name, _content in entry_files:
        changes["entrypoints"].append(str(scripts_root / name))

    # default configs (only when target missing)
    for comp in components:
        for target, template_rel in manifest["components"][comp].get("config_templates", {}).items():
            dst = data_root / "config" / target
            if not dst.exists():
                changes["config_files"].append({"template": template_rel, "dst": str(dst)})

    if args.dry_run:
        print(json.dumps({"action": "install", "dry_run": True, "plan": plan, "changes": changes}, ensure_ascii=False, indent=2))
        return 0

    scripts_root.mkdir(parents=True, exist_ok=True)
    (data_root / "config").mkdir(parents=True, exist_ok=True)
    for d in changes["dirs"]:
        Path(d).mkdir(parents=True, exist_ok=True)

    for src, rel in lib_pairs:
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
    for src, rel in lib_pairs:
        owned.append({"path": str(Path("lib") / rel.parent.name / rel.name), "sha256": sha256(src)})
    for name, _content in entry_files:
        dst = scripts_root / name
        owned.append({"path": name, "sha256": sha256(dst)})

    installed = {
        "schema_version": 1,
        "project": manifest["project"],
        "runtime": args.runtime,
        "components": components,
        "scripts_dir": rt["scripts_dir"],
        "data_dir": rt["data_dir"],
        "entrypoints": {comp: manifest["components"][comp]["entrypoint"] for comp in components},
        "jobs": {
            comp: {
                "name": comp,
                "script": f"{Path(rt['scripts_dir']).name}/{manifest['components'][comp]['entrypoint']}",
                "prompt": manifest["components"][comp]["prompt"],
                "default_schedule": manifest["components"][comp]["default_schedule"],
            }
            for comp in components
        },
        "owned_files": owned,
        "user_config_files": [
            f"config/{name}"
            for comp in components
            for name in manifest["components"][comp].get("config_templates", {})
        ],
    }
    manifest_dst = data_root / INSTALL_MANIFEST_NAME
    manifest_dst.write_text(json.dumps(installed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = {
        "action": "install",
        "ok": True,
        "runtime": args.runtime,
        "components": components,
        "installed_manifest": str(manifest_dst),
        "missing_python_deps": dep_missing,
        "missing_external_skills": skill_missing,
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

    # entrypoints
    for name in ENTRYPOINTS:
        p = scripts_root / name
        add(f"entrypoint:{name}", p.exists() and p.is_file(), str(p))

    # owned files: lib must match hashes; entrypoints are runtime wrappers
    if installed:
        for owned in installed.get("owned_files", []):
            live = scripts_root / owned["path"]
            if not live.exists():
                add(f"file:{owned['path']}", False, "missing")
                continue
            is_lib = owned["path"].startswith("lib/")
            if is_lib:
                live_sha = sha256(live)
                ok = live_sha == owned["sha256"]
                add(f"lib:{owned['path']}", ok, "match" if ok else f"drift {live_sha[:12]} != {owned['sha256'][:12]}")
            else:
                add(f"entrypoint:{owned['path']}", True, "present")

    # config files exist
    if installed:
        for rel in installed.get("user_config_files", []):
            p = data_root / rel
            add(f"config:{rel}", p.exists(), str(p))

    # cron wiring: a job whose script resolves to our entrypoints.
    # Hermes job `script` is relative to $HERMES_HOME/scripts/.
    jobs_file = home / rt["jobs_file"]
    if jobs_file.exists():
        try:
            jobs = load_json(jobs_file).get("jobs", [])
            scripts_base = home / "scripts"
            wired = []
            for job in jobs:
                script = job.get("script", "")
                if not script:
                    continue
                entry_name = Path(script).name
                if entry_name in ENTRYPOINTS and (scripts_base / script).exists():
                    wired.append({"job_id": job.get("id"), "name": job.get("name"), "script": script})
            add("cron-wiring", bool(wired), json.dumps(wired, ensure_ascii=False))
        except (OSError, ValueError) as exc:
            add("cron-wiring", False, f"cannot read {jobs_file}: {exc}")
    else:
        add("cron-wiring", False, f"jobs file not found: {jobs_file}")

    ok = all(c["ok"] for c in checks)
    result = {"action": "verify", "ok": ok, "runtime": args.runtime, "checks": checks}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ok else 1


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
            for job in jobs:
                script = job.get("script", "")
                if not script:
                    continue
                entry_name = Path(script).name
                if entry_name in ENTRYPOINTS and (scripts_base / script).exists():
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
    p_install.add_argument("--runtime", default="hermes", choices=["hermes"])
    p_install.add_argument("--components", default="", help="comma-separated components")
    p_install.add_argument("--prefix", default="", help="runtime home (default: $HERMES_HOME or ~/.hermes)")
    p_install.add_argument("--dry-run", action="store_true")

    p_verify = sub.add_parser("verify", help="verify installed state")
    p_verify.add_argument("--runtime", default="hermes", choices=["hermes"])
    p_verify.add_argument("--prefix", default="")

    p_uninstall = sub.add_parser("uninstall", help="remove project-owned files (keeps user config)")
    p_uninstall.add_argument("--runtime", default="hermes", choices=["hermes"])
    p_uninstall.add_argument("--prefix", default="")
    p_uninstall.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    if args.action == "install":
        return cmd_install(args)
    if args.action == "verify":
        return cmd_verify(args)
    if args.action == "uninstall":
        return cmd_uninstall(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
