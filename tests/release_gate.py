#!/usr/bin/env python3
"""Stdlib-only static release gate for glance_brief v0.3.0."""
from __future__ import annotations

import json
import py_compile
import re
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", ".venv", "venv", "build", "dist", "__pycache__"}


def repository_files(pattern: str):
    for path in ROOT.rglob(pattern):
        relative = path.relative_to(ROOT)
        if any(part in SKIP_PARTS or part.endswith(".egg-info") for part in relative.parts):
            continue
        if path.is_file():
            yield path


def main() -> int:
    errors: list[str] = []
    python_files = sorted(repository_files("*.py"))
    with TemporaryDirectory(prefix="glance-brief-compile-") as temp:
        compiled = Path(temp)
        for index, path in enumerate(python_files):
            try:
                py_compile.compile(str(path), cfile=str(compiled / f"{index}.pyc"), doraise=True)
            except py_compile.PyCompileError as exc:
                errors.append(f"python:{path.relative_to(ROOT)}: {exc}")

    json_files = sorted(repository_files("*.json"))
    for path in json_files:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"json:{path.relative_to(ROOT)}: {exc}")

    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    pyproject_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project_section = pyproject_text.split("[project]", 1)[1].split("[", 1)[0]
    version_match = re.search(r'^version\s*=\s*"([^"]+)"\s*$', project_section, re.MULTILINE)
    if version_match is None:
        errors.append("version:pyproject: [project] version is missing")
        pyproject_version = ""
    else:
        pyproject_version = version_match.group(1)
    package_init = (ROOT / "glance_brief" / "__init__.py").read_text(encoding="utf-8")
    installer = json.loads((ROOT / "install" / "install-manifest.json").read_text(encoding="utf-8"))
    version_checks = {
        "pyproject": pyproject_version,
        "installer": installer["project_version"],
    }
    for name, actual in version_checks.items():
        if actual != expected:
            errors.append(f"version:{name}: expected {expected}, got {actual}")
    if f'__version__ = "{expected}"' not in package_init:
        errors.append("version:package: __version__ does not match VERSION")

    forbidden_names = ("run_" + "experimental.py", "test_" + "experimental_", "/" + "experi" + "mental/")
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in SKIP_PARTS or part.endswith(".egg-info") for part in relative.parts):
            continue
        posix = "/" + relative.as_posix()
        if any(token in posix for token in forbidden_names):
            errors.append(f"layout:experimental path remains: {posix}")

    hermes_jobs = json.loads((ROOT / "adapters" / "hermes" / "jobs.example.json").read_text(encoding="utf-8"))
    forbidden_job_fields = {"prompt", "prompt_file", "model", "provider", "skills"}
    for job in hermes_jobs.get("jobs", []):
        if job.get("no_agent") is not True:
            errors.append(f"hermes-job:{job.get('name')}: no_agent must be true")
        leaked = sorted(forbidden_job_fields.intersection(job))
        if leaked:
            errors.append(f"hermes-job:{job.get('name')}: forbidden fields {leaked}")

    openclaw_jobs = json.loads((ROOT / "adapters" / "openclaw" / "jobs.example.json").read_text(encoding="utf-8"))
    if openclaw_jobs.get("status") != "adapter-contract-only" or openclaw_jobs.get("jobs") != []:
        errors.append("openclaw: v0.3.0 must not advertise unverified runnable jobs")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "version": expected,
                "python_files": len(python_files),
                "json_files": len(json_files),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
