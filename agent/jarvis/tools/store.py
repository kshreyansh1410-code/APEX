"""A tiny human-readable JSON store, shared by tools that keep data on disk."""

import json
import os
import tempfile
from pathlib import Path

from .registry import ToolError


class JsonStore:
    """A list of dict records in one pretty-printed JSON file you can open and edit."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text() or "[]")
        except json.JSONDecodeError as e:
            raise ToolError(f"{self.path.name} isn't valid JSON (line {e.lineno}); it may have been hand-edited") from None

    def save(self, records: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file then rename, so a crash can't leave a half-written file.
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, self.path)

    @staticmethod
    def next_id(records: list[dict]) -> int:
        return max((r["id"] for r in records), default=0) + 1
