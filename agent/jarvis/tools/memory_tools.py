"""Tools that let Jarvis manage its own long-term memory."""

from ..memory import CATEGORIES, MemoryError, MemoryStore
from .registry import Registry, Tool, ToolError


def _describe_forget(store: MemoryStore, memory_id: int) -> str:
    for m in store.load():
        if m.id == memory_id:
            return f"permanently forget memory #{memory_id}: \"{m.text}\""
    return f"forget memory #{memory_id} (it doesn't seem to exist)"


def register(registry: Registry, store: MemoryStore) -> None:
    def remember(fact: str, category: str) -> str:
        memory, created = store.add(fact, category)
        if not created:
            return f"Already remembered as #{memory.id}: {memory.text}"
        return f"Remembered #{memory.id}: {memory.text}"

    def update_memory(memory_id: int, fact: str) -> str:
        try:
            old, memory = store.update(memory_id, fact)
        except MemoryError as e:
            raise ToolError(str(e)) from None
        return f"Updated #{memory.id}. Was: {old!r}. Now: {memory.text!r}"

    def forget_memory(memory_id: int) -> str:
        try:
            memory = store.remove(memory_id)
        except MemoryError as e:
            raise ToolError(str(e)) from None
        return f"Forgot #{memory.id}: {memory.text}"

    def recall_memories(query: str) -> str:
        found = store.search(query)
        if not found:
            return f"Nothing remembered about '{query}'."
        return "\n".join(m.line() for m in found)

    registry.register(Tool(
        name="remember",
        description=(
            "Save a durable fact about the user to long-term memory, so you still know it in future sessions. "
            "Use it when the user tells you something lasting about themselves: who they are, what they're studying, "
            "a preference, or a decision they've made, or when they ask you to remember something. "
            "Don't store passing chatter, one-off requests, or things only relevant to this conversation. "
            "Write one plain statement per fact, in the user's perspective, e.g. 'I'm a second-year biology student.'"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "fact": {"type": "string", "description": "One short, self-contained statement.", "minLength": 1, "maxLength": 300},
                "category": {"type": "string", "enum": list(CATEGORIES),
                             "description": "about_me (identity, background), preference, fact (about their world), or decision."},
            },
            "required": ["fact", "category"],
            "additionalProperties": False,
        },
        handler=remember,
    ))
    registry.register(Tool(
        name="update_memory",
        description=(
            "Correct or refresh an existing memory when the user tells you it has changed or was wrong, "
            "e.g. they switched courses. Use the memory's #id. Prefer this over saving a contradicting new fact."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "memory_id": {"type": "integer"},
                "fact": {"type": "string", "description": "The corrected statement.", "minLength": 1, "maxLength": 300},
            },
            "required": ["memory_id", "fact"],
            "additionalProperties": False,
        },
        handler=update_memory,
    ))
    registry.register(Tool(
        name="forget_memory",
        description="Permanently delete a memory. Use only when the user asks you to forget something.",
        input_schema={
            "type": "object",
            "properties": {"memory_id": {"type": "integer"}},
            "required": ["memory_id"],
            "additionalProperties": False,
        },
        handler=forget_memory,
        consequential=True,  # deletes data
        describe=lambda args: _describe_forget(store, args["memory_id"]),
    ))
    registry.register(Tool(
        name="recall_memories",
        description=(
            "Search everything you remember about the user by keywords. Use it when a question might depend on "
            "something you remember but it isn't in the memories already shown to you."
        ),
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string", "maxLength": 200}},
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=recall_memories,
    ))
