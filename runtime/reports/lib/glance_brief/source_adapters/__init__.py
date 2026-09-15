"""Registry and dispatch for source adapters.

Most sources use the configuration-driven ``generic`` adapter.  Special
sources register an adapter by implementation name and stay out of the
report entrypoints.  ``get_source_adapter`` and ``adapt_payload`` remain
compatibility APIs for the existing local-radar publication bridge.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .. import contracts
from . import generic, local_open_source_radar

SOURCE_ADAPTERS = {
    "generic": generic,
    "local_open_source_radar": local_open_source_radar,
}
_LEGACY_SOURCE_ADAPTERS = {
    "open_source_radar": "local_open_source_radar",
}


def get_adapter(adapter_id: str):
    """Return an adapter module by implementation ID."""
    return SOURCE_ADAPTERS.get(adapter_id)


def get_source_adapter(source_id: str):
    """Compatibility lookup by historical source ID."""
    adapter_id = _LEGACY_SOURCE_ADAPTERS.get(source_id, source_id)
    return get_adapter(adapter_id)


def adapt_source(
    source_id: str,
    source: Mapping[str, Any],
    payload: Any,
) -> dict[str, Any]:
    """Dispatch one source through its configured adapter.

    Generic adapters expose ``adapt_source``.  Special publication adapters
    can be migrated independently; until then their compatibility API remains
    available through ``adapt_payload`` below.
    """
    adapter_id = source.get("adapter", "generic")
    if not isinstance(adapter_id, str) or not adapter_id:
        raise contracts.ContractError(f"sources.{source_id}.adapter must be a non-empty string")
    adapter = get_adapter(adapter_id)
    if adapter is None:
        raise contracts.ContractError(f"unknown source adapter {adapter_id!r}")
    handler = getattr(adapter, "adapt_source", None)
    if not callable(handler):
        raise contracts.ContractError(
            f"source adapter {adapter_id!r} does not expose adapt_source"
        )
    result = handler(source_id, source, payload)
    if not isinstance(result, dict):
        raise contracts.ContractError(
            f"source adapter {adapter_id!r} returned a non-object result"
        )
    return result


def adapt_payload(
    source_id: str,
    payload: Mapping[str, Any],
    *,
    report_date: str,
    report_dir: Path,
) -> dict[str, Any]:
    """Apply the legacy special-source publication adapter."""
    adapter = get_source_adapter(source_id)
    if adapter is None:
        raise contracts.ContractError(f"no source adapter registered for {source_id!r}")
    handler = getattr(adapter, "adapt_payload", None)
    if not callable(handler):
        raise contracts.ContractError(
            f"source adapter {source_id!r} does not expose adapt_payload"
        )
    result = handler(
        payload,
        report_date=report_date,
        report_dir=report_dir,
    )
    if not isinstance(result, dict):
        raise contracts.ContractError(
            f"source adapter {source_id!r} returned a non-object result"
        )
    return result


__all__ = [
    "SOURCE_ADAPTERS",
    "adapt_payload",
    "adapt_source",
    "get_adapter",
    "get_source_adapter",
]
