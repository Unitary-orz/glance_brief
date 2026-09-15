"""Registry for source-specific payload adapters.

Generic sources use the configured input and field-mapping boundary.  Only a
source with additional publication or payload semantics is registered here.
The registry keeps that knowledge out of the report entrypoints and generic
assembler.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .. import contracts
from . import local_open_source_radar

SOURCE_ADAPTERS = {
    "open_source_radar": local_open_source_radar,
}


def get_source_adapter(source_id: str):
    """Return the special adapter for ``source_id``, if one is registered."""
    return SOURCE_ADAPTERS.get(source_id)


def adapt_payload(
    source_id: str,
    payload: Mapping[str, Any],
    *,
    report_date: str,
    report_dir: Path,
) -> dict[str, Any]:
    """Apply one registered source adapter at the source boundary."""
    adapter = get_source_adapter(source_id)
    if adapter is None:
        raise contracts.ContractError(f"no source adapter registered for {source_id!r}")
    return adapter.adapt_payload(
        payload,
        report_date=report_date,
        report_dir=report_dir,
    )


__all__ = ["SOURCE_ADAPTERS", "adapt_payload", "get_source_adapter"]
