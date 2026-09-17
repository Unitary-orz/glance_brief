"""Executable contract for source prefetch/producers.

A producer prints one JSON envelope.  It owns network access and raw source
facts, but it must not print logs, Markdown reports, or delivery messages to
stdout.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from . import contracts

PRODUCER_SCHEMA_VERSION = 1
CONTROL_FIELDS = {
    "ok": ((bool,), "boolean"),
    "error": ((str, type(None)), "string or null"),
    "instructions": ((str, Mapping, list), "string, object, or array"),
    "generated_at": ((str,), "string"),
}


def validate_payload(payload: Any, *, path: str = "producer output") -> dict[str, Any]:
    """Validate and return one schema-1 producer envelope.

    The envelope is intentionally source-agnostic: source namespaces are
    discovered by the report config.  A small set of optional control fields
    is allowed because the existing Agents producer reports source health and
    provenance instructions alongside its namespaces.  Every other top-level
    field is a source namespace and must be an object or array.
    """
    if not isinstance(payload, Mapping):
        raise contracts.ContractError(f"{path} must be a JSON object")
    if payload.get("schema_version") != PRODUCER_SCHEMA_VERSION:
        raise contracts.ContractError(
            f"{path}.schema_version must be {PRODUCER_SCHEMA_VERSION}"
        )
    for key, (expected, description) in CONTROL_FIELDS.items():
        if key in payload and not isinstance(payload[key], expected):
            raise contracts.ContractError(f"{path}.{key} must be {description}")
    namespaces = [
        key for key in payload
        if key != "schema_version" and key not in CONTROL_FIELDS
    ]
    if not namespaces:
        raise contracts.ContractError(f"{path} must contain at least one source namespace")
    for key in namespaces:
        if not isinstance(key, str) or not key.strip():
            raise contracts.ContractError(f"{path} source namespace names must be non-empty strings")
        value = payload[key]
        if not isinstance(value, (Mapping, list)):
            raise contracts.ContractError(
                f"{path}.{key} must be a JSON object or array, not a scalar"
            )
    return dict(payload)


def parse_stdout(stdout: str, *, path: str = "producer stdout") -> dict[str, Any]:
    """Parse producer stdout and reject mixed logs or malformed JSON."""
    if not isinstance(stdout, str) or not stdout.strip():
        raise contracts.ContractError(f"{path} must contain one JSON envelope")
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise contracts.ContractError(f"{path} must contain valid JSON only: {exc.msg}") from exc
    return validate_payload(payload, path=path)
