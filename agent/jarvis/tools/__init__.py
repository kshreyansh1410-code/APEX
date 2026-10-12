"""Jarvis's tools. To add a capability: write a module with register(), and add it below."""

from pathlib import Path

from . import lookup, notes, tasks
from .registry import Registry, Tool, ToolError, ToolOutcome


def build_registry(data_dir: Path, simulate_failure: frozenset[str] = frozenset()) -> Registry:
    registry = Registry(simulate_failure=simulate_failure)
    notes.register(registry, data_dir)
    tasks.register(registry, data_dir)
    lookup.register(registry)
    return registry


__all__ = ["Registry", "Tool", "ToolError", "ToolOutcome", "build_registry"]
