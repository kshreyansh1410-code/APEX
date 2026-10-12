"""Capability 1: research notes — save a note, search notes later."""

import re
from datetime import datetime
from pathlib import Path

from .registry import Registry, Tool
from .store import JsonStore


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}


def register(registry: Registry, data_dir: Path) -> None:
    store = JsonStore(data_dir / "notes.json")

    def save_note(text: str, topic: str = "") -> str:
        notes = store.load()
        note = {
            "id": JsonStore.next_id(notes),
            "text": text.strip(),
            "topic": topic.strip(),
            "created": datetime.now().isoformat(timespec="minutes"),
        }
        notes.append(note)
        store.save(notes)
        return f"Saved note #{note['id']}" + (f" under '{note['topic']}'." if note["topic"] else ".")

    def search_notes(query: str, limit: int = 5) -> str:
        notes = store.load()
        if not notes:
            return "There are no notes yet."
        wanted = _words(query)
        scored = []
        for n in notes:
            score = len(wanted & _words(n["text"] + " " + n.get("topic", "")))
            if score or not wanted:
                scored.append((score, n["id"], n))
        if not scored:
            return f"No notes match '{query}'."
        scored.sort(key=lambda s: (-s[0], -s[1]))  # best match first, then newest
        lines = [
            f"#{n['id']} ({n['created'][:10]}{', ' + n['topic'] if n.get('topic') else ''}): {n['text']}"
            for _, _, n in scored[: max(1, min(limit, 20))]
        ]
        return f"{len(scored)} matching note(s):\n" + "\n".join(lines)

    registry.register(Tool(
        name="save_note",
        description=(
            "Save a research or study note for the user so it can be found later. "
            "Use this when the user asks you to note, jot down, or save something they learned or want to keep. "
            "Save the note in the user's own words where possible."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The note itself.", "minLength": 1, "maxLength": 4000},
                "topic": {"type": "string", "description": "Optional short topic label, e.g. 'biology' or 'thesis'.", "maxLength": 80},
            },
            "required": ["text"],
            "additionalProperties": False,
        },
        handler=save_note,
    ))
    registry.register(Tool(
        name="search_notes",
        description=(
            "Search the user's saved research and study notes by keywords. "
            "Use this whenever the user asks what they noted, wrote down, or saved about something, "
            "or when their past notes would help answer a question. An empty query lists the newest notes."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keywords to look for, e.g. 'krebs cycle mitochondria'.", "maxLength": 200},
                "limit": {"type": "integer", "description": "Maximum number of notes to return (default 5)."},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=search_notes,
    ))
