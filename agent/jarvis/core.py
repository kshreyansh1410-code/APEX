"""The agent core: one conversation loop shared by every way in and out.

Typed turns (Tier 1), spoken turns (Tier 3), and heartbeat turns (Tier 5) all call
`Agent.handle_turn()`. Never fork this logic per channel; add adapters at the edges.
"""

import threading
from dataclasses import dataclass
from typing import Callable

from .config import AssistantConfig
from .provider import Provider, ProviderError
from .tools import Registry, ToolOutcome


def build_system_prompt(assistant: AssistantConfig) -> str:
    return (
        f"You are {assistant.name}, a personal voice-first assistant. "
        f"Your job is to {assistant.purpose}.\n\n"
        f"Personality: {assistant.personality}\n\n"
        "Your replies may be read aloud, so prefer short, natural sentences. "
        "Avoid tables, heavy markdown, and long lists unless asked for them.\n\n"
        "You have tools for the user's notes, their to-do list, and looking things up. "
        "Use them whenever they help instead of guessing. If a tool fails, tell the user "
        "plainly what went wrong and what they can do, and don't pretend it worked."
    )


@dataclass
class TurnResult:
    ok: bool
    text: str  # the reply, or a user-facing error message when ok is False
    cancelled: bool = False


class TurnCancelled(Exception):
    """Raise from a callback (e.g. on_text) to abandon the current turn."""


# Called when the model asks for a tool (name, input) and when it finishes (name, outcome).
OnToolStart = Callable[[str, dict], None]
OnToolEnd = Callable[[str, ToolOutcome], None]


class Agent:
    def __init__(self, provider: Provider, assistant: AssistantConfig, registry: Registry | None = None,
                 max_tool_rounds: int = 8):
        self.provider = provider
        self.assistant = assistant
        self.registry = registry or Registry()
        self.max_tool_rounds = max_tool_rounds
        self.system_prompt = build_system_prompt(assistant)
        # Short-term memory: the running conversation for this session only.
        self.history: list[dict] = []
        self._lock = threading.Lock()

    def handle_turn(
        self,
        user_text: str,
        on_text: Callable[[str], None] | None = None,
        on_tool_start: OnToolStart | None = None,
        on_tool_end: OnToolEnd | None = None,
        cancel: threading.Event | None = None,
    ) -> TurnResult:
        """Run one turn, letting the model call as many tools as it needs before answering.

        History is only committed when the turn completes, so a failed, interrupted,
        or cancelled turn leaves the conversation exactly as it was.
        """
        try:
            return self._run_turn(user_text, on_text, on_tool_start, on_tool_end, cancel or threading.Event())
        except TurnCancelled:
            return TurnResult(ok=False, text="", cancelled=True)

    def _run_turn(self, user_text, on_text, on_tool_start, on_tool_end, cancel) -> TurnResult:
        with self._lock:
            pending = self.history + [{"role": "user", "content": user_text}]
        tools = self.registry.schemas() or None
        texts: list[str] = []

        for _ in range(self.max_tool_rounds + 1):
            if cancel.is_set():
                raise TurnCancelled
            try:
                reply = self.provider.respond(self.system_prompt, pending, tools=tools, on_text=on_text)
            except ProviderError as e:
                return TurnResult(ok=False, text=str(e))
            pending.append({"role": "assistant", "content": reply.content})
            if reply.text:
                texts.append(reply.text)

            tool_uses = [b for b in reply.content if _get(b, "type") == "tool_use"]
            if not tool_uses:
                with self._lock:
                    # Checked under the lock so a newer turn can never be overwritten.
                    if cancel.is_set():
                        raise TurnCancelled
                    self.history = pending
                return TurnResult(ok=True, text="\n".join(texts))
            if reply.stop_reason == "max_tokens":
                # A cut-off tool call can look valid; never run it.
                return TurnResult(ok=False, text="My answer got cut off mid-action, so I didn't run it. Try a narrower request.")

            results = []
            for block in tool_uses:
                if cancel.is_set():
                    raise TurnCancelled
                name, args = _get(block, "name"), _get(block, "input")
                if on_tool_start:
                    on_tool_start(name, args)
                outcome = self.registry.run(name, args)
                if on_tool_end:
                    on_tool_end(name, outcome)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": _get(block, "id"),
                    "content": outcome.content,
                    "is_error": outcome.is_error,
                })
            # All results for one assistant turn go back together in a single user message.
            pending.append({"role": "user", "content": results})

        return TurnResult(ok=False, text="I went round in circles calling tools without finishing, so I stopped. Try asking another way.")

    def reset(self) -> None:
        with self._lock:
            self.history = []


def _get(block, key):
    """Read a field from an SDK content block or a plain dict."""
    return block.get(key) if isinstance(block, dict) else getattr(block, key)
