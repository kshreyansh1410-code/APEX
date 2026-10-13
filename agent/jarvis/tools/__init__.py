"""Jarvis's tools. To add a capability: write a module with register(), and add it below."""

from pathlib import Path

from ..memory import MemoryStore
from . import lookup, memory_tools, notes, tasks
from .registry import Registry, Tool, ToolError, ToolOutcome


def build_registry(data_dir: Path, simulate_failure: frozenset[str] = frozenset(),
                   memory: MemoryStore | None = None) -> Registry:
    registry = Registry(simulate_failure=simulate_failure)
    notes.register(registry, data_dir)
    tasks.register(registry, data_dir)
    lookup.register(registry)
    memory_tools.register(registry, memory or MemoryStore(data_dir / "memory.md"))
    return registry


__all__ = ["Registry", "Tool", "ToolError", "ToolOutcome", "build_registry"]
