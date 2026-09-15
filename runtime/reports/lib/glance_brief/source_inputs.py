"""Compatibility facade for the reports input-adapter package.

The implementations live under :mod:`glance_brief.input_adapters`.  This
module remains import-compatible for legacy callers and archived replays while new
code should import the package directly.
"""
from __future__ import annotations

from .input_adapters import (
    SOURCE_INPUT_ADAPTERS,
    CommandJsonInput,
    JsonFileInput,
    SnapshotJsonInput,
    SourceInputAdapter,
    load_source_input,
)

__all__ = [
    "SOURCE_INPUT_ADAPTERS",
    "CommandJsonInput",
    "JsonFileInput",
    "SnapshotJsonInput",
    "SourceInputAdapter",
    "load_source_input",
]
