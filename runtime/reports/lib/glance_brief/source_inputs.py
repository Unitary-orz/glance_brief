"""Runtime-independent source input drivers.

Input drivers only obtain one payload.  Mapping that payload into canonical
candidates remains the responsibility of ``adapters``; report assembly does
not need to know whether a source reads a file, runs an argv command, or views
an already loaded immutable snapshot.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from collections.abc import Mapping
from typing import Any

from . import contracts


class SourceInputAdapter:
    """Small input seam used by the source catalog."""

    def load(
        self,
        source_id: str,
        source: Mapping[str, Any],
        config_dir: Path,
        *,
        snapshot_payload: Any = None,
    ) -> Any:
        raise NotImplementedError


def _resolve_path(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else base / path


class JsonFileInput(SourceInputAdapter):
    def load(self, source_id, source, config_dir, *, snapshot_payload=None):
        path = source.get("path")
        if not isinstance(path, str) or not path:
            raise contracts.ContractError(f"source {source_id} json_file path is missing")
        return json.loads(_resolve_path(config_dir, path).read_text(encoding="utf-8"))


class CommandJsonInput(SourceInputAdapter):
    def load(self, source_id, source, config_dir, *, snapshot_payload=None):
        timeout = float(source.get("timeout", 30))
        cwd = _resolve_path(config_dir, source.get("cwd", "."))
        environment_names = {"PATH", "HOME", "LANG", "LC_ALL", "TZ"}
        environment_names.update(source.get("env_allowlist", []))
        environment = {name: os.environ[name] for name in environment_names if name in os.environ}
        completed = subprocess.run(
            source["command"],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=False,
            env=environment,
        )
        if completed.returncode:
            raise RuntimeError(
                f"source {source_id} exited with {completed.returncode}: {completed.stderr.strip()}"
            )
        return json.loads(completed.stdout)


class SnapshotJsonInput(SourceInputAdapter):
    """View the report's one immutable input document without reloading it."""

    def load(self, source_id, source, config_dir, *, snapshot_payload=None):
        if snapshot_payload is None:
            raise contracts.ContractError(
                f"source {source_id} snapshot_json requires a report input payload"
            )
        return snapshot_payload


SOURCE_INPUT_ADAPTERS: dict[str, SourceInputAdapter] = {
    "json_file": JsonFileInput(),
    "command_json": CommandJsonInput(),
    "snapshot_json": SnapshotJsonInput(),
    # Compatibility for schema-v3 Reports configs written before the driver
    # was renamed.  New configs should use snapshot_json.
    "report_json": SnapshotJsonInput(),
}


def load_source_input(
    source_id: str,
    source: Mapping[str, Any],
    config_dir: Path,
    *,
    snapshot_payload: Any = None,
) -> Any:
    """Load one source through its registered input adapter."""
    driver = source.get("driver")
    adapter = SOURCE_INPUT_ADAPTERS.get(driver)
    if adapter is None:
        raise contracts.ContractError(f"source {source_id} has unsupported input driver {driver!r}")
    return adapter.load(
        source_id,
        source,
        config_dir,
        snapshot_payload=snapshot_payload,
    )
