"""Long-term memory: small, plain facts that survive restarts.

Stored as a Markdown file you can open, correct, and delete from by hand:

    ## About me
    - My name is Sam. <!-- m1, 2026-10-13 -->

    ## Preferences
    - I like short answers in the morning. <!-- m2, 2026-10-13 -->

One fact per bullet. The trailing comment holds the id and last-updated date; a bullet
you add by hand without one gets an id on the next save. Headings are categories.
"""

import os
import re
import tempfile
import threading
from dataclasses import dataclass
from datetime import date
from pathlib import Path

CATEGORIES = {
    "about_me": "About me",
    "preference": "Preferences",
    "fact": "Facts",
    "decision": "Decisions",
}
_HEADING_TO_CATEGORY = {v.lower(): k for k, v in CATEGORIES.items()}
_BULLET = re.compile(r"^\s*[-*]\s+(?P<text>.*?)\s*(?:<!--\s*(?P<meta>[^>]*?)\s*-->)?\s*$")
_META = re.compile(r"m(?P<id>\d+)(?:\s*,\s*(?P<date>\d{4}-\d{2}-\d{2}))?")

HEADER = (
    "# What Jarvis remembers about me\n\n"
    "One fact per bullet. Edit, fix, or delete anything; Jarvis reads this file at the start of\n"
    "every session. Keep the `<!-- m… -->` tag at the end of a line you edit. New bullets you add\n"
    "need no tag. Headings: About me, Preferences, Facts, Decisions.\n"
)


@dataclass
class Memory:
    id: int
    text: str
    category: str = "fact"
    updated: str = ""

    def line(self) -> str:
        return f"#{self.id} [{CATEGORIES[self.category]}] {self.text}"


class MemoryError(Exception):
    """A memory operation that can't be done; the message is safe to show."""


class MemoryStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()  # voice and heartbeat threads may share one store

    # --- reading and writing the file --------------------------------------

    def load(self) -> list[Memory]:
        if not self.path.exists():
            return []
        memories, category, used_ids = [], "fact", set()
        untagged = []
        for raw in self.path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            if raw.startswith("## "):
                category = _HEADING_TO_CATEGORY.get(raw[3:].strip().lower(), "fact")
                continue
            m = _BULLET.match(raw)
            if not m or not m.group("text"):
                continue
            meta = _META.search(m.group("meta") or "")
            memory = Memory(id=0, text=m.group("text"), category=category,
                            updated=(meta.group("date") if meta and meta.group("date") else ""))
            if meta and int(meta.group("id")) not in used_ids:
                memory.id = int(meta.group("id"))
                used_ids.add(memory.id)
            else:
                untagged.append(memory)  # added by hand (or a duplicated tag)
            memories.append(memory)
        next_id = max(used_ids, default=0) + 1
        for memory in untagged:
            memory.id, next_id = next_id, next_id + 1
        return memories

    def save(self, memories: list[Memory]) -> None:
        sections = []
        for key, heading in CATEGORIES.items():
            lines = [f"- {m.text} <!-- m{m.id}, {m.updated or date.today().isoformat()} -->"
                     for m in memories if m.category == key]
            if lines:
                sections.append(f"## {heading}\n" + "\n".join(lines))
        content = HEADER + ("\n" + "\n\n".join(sections) + "\n" if sections else "")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, self.path)

    # --- operations the tools use ------------------------------------------

    def add(self, text: str, category: str = "fact") -> tuple[Memory, bool]:
        """Store a fact. Returns (memory, created); an identical fact isn't stored twice."""
        text = _one_line(text)
        with self._lock:
            memories = self.load()
            for m in memories:
                if _normalize(m.text) == _normalize(text):
                    return m, False
            memory = Memory(max((m.id for m in memories), default=0) + 1, text, category, date.today().isoformat())
            memories.append(memory)
            self.save(memories)
            return memory, True

    def update(self, memory_id: int, text: str) -> tuple[str, Memory]:
        with self._lock:
            memories = self.load()
            memory = _find(memories, memory_id)
            old, memory.text, memory.updated = memory.text, _one_line(text), date.today().isoformat()
            self.save(memories)
            return old, memory

    def remove(self, memory_id: int) -> Memory:
        with self._lock:
            memories = self.load()
            memory = _find(memories, memory_id)
            memories.remove(memory)
            self.save(memories)
            return memory

    def search(self, query: str, limit: int = 10) -> list[Memory]:
        wanted = _words(query)
        scored = [(len(wanted & _words(m.text)), m) for m in self.load()]
        hits = [(s, m) for s, m in scored if s or not wanted]
        hits.sort(key=lambda sm: (-sm[0], -sm[1].id))
        return [m for _, m in hits[:limit]]

    # --- what goes into the prompt -----------------------------------------

    def prompt_section(self, max_facts: int) -> str:
        """The facts to load at the start of a conversation.

        Everything while memory is small; past max_facts, the most recently updated
        ones, with the rest reachable through the recall_memories tool.
        """
        memories = self.load()
        if not memories:
            return ""
        shown = memories
        if len(memories) > max_facts:
            shown = sorted(memories, key=lambda m: (m.updated, m.id), reverse=True)[:max_facts]
        lines = "\n".join(m.line() for m in sorted(shown, key=lambda m: m.id))
        more = ""
        if len(shown) < len(memories):
            more = (f"\n({len(memories) - len(shown)} older memories are not shown; "
                    "use recall_memories to search them when they might help.)")
        return lines + more


def _find(memories: list[Memory], memory_id: int) -> Memory:
    for m in memories:
        if m.id == memory_id:
            return m
    raise MemoryError(f"there is no memory #{memory_id}")


def _one_line(text: str) -> str:
    # One fact per bullet: newlines would break the file format. Strip comment markers too.
    return re.sub(r"\s+", " ", text.replace("<!--", "").replace("-->", "")).strip()


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}
