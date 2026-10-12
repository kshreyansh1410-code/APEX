"""The agent core: one conversation loop shared by every way in and out.

Typed turns (Tier 1), spoken turns (Tier 3), and heartbeat turns (Tier 5) all call
`Agent.handle_turn()`. Never fork this logic per channel; add adapters at the edges.
"""

from dataclasses import dataclass
from typing import Callable

from .config import AssistantConfig
from .provider import Provider, ProviderError


def build_system_prompt(assistant: AssistantConfig) -> str:
    return (
        f"You are {assistant.name}, a personal voice-first assistant. "
        f"Your job is to {assistant.purpose}.\n\n"
        f"Personality: {assistant.personality}\n\n"
        "Your replies may be read aloud, so prefer short, natural sentences. "
        "Avoid tables, heavy markdown, and long lists unless asked for them."
    )


@dataclass
class TurnResult:
    ok: bool
    text: str  # the reply, or a user-facing error message when ok is False


class Agent:
    def __init__(self, provider: Provider, assistant: AssistantConfig):
        self.provider = provider
        self.assistant = assistant
        self.system_prompt = build_system_prompt(assistant)
        # Short-term memory: the running conversation for this session only.
        self.history: list[dict] = []

    def handle_turn(self, user_text: str, on_text: Callable[[str], None] | None = None) -> TurnResult:
        """Run one turn. History is only committed if the model call succeeds,
        so a failed or interrupted turn leaves the conversation exactly as it was."""
        pending = self.history + [{"role": "user", "content": user_text}]
        try:
            reply = self.provider.respond(self.system_prompt, pending, on_text=on_text)
        except ProviderError as e:
            return TurnResult(ok=False, text=str(e))
        self.history = pending + [{"role": "assistant", "content": reply.content}]
        return TurnResult(ok=True, text=reply.text)

    def reset(self) -> None:
        self.history = []
