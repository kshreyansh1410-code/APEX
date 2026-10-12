"""Tier 1 checks that run without network or an API key."""

from types import SimpleNamespace

import anthropic
import pytest

from jarvis.config import AssistantConfig, ModelConfig, load_config
from jarvis.core import Agent
from jarvis.provider import ClaudeProvider, ProviderError, Reply


class FakeProvider:
    """Echoes how many user turns it was shown, and records every request."""

    def __init__(self, fail_on: int | None = None):
        self.calls: list[list[dict]] = []
        self.fail_on = fail_on

    def respond(self, system, messages, on_text=None):
        self.calls.append([dict(m) for m in messages])
        if self.fail_on == len(self.calls):
            raise ProviderError("network down")
        text = f"seen {sum(m['role'] == 'user' for m in messages)} user turns"
        if on_text:
            for word in text.split(" "):
                on_text(word + " ")
        return Reply(text=text, content=[{"type": "text", "text": text}], stop_reason="end_turn")


def test_history_is_passed_back_every_turn():
    provider = FakeProvider()
    agent = Agent(provider, AssistantConfig())
    agent.handle_turn("my name is Sam")
    agent.handle_turn("I study biology")
    result = agent.handle_turn("what's my name?")

    assert result.ok and result.text == "seen 3 user turns"
    last_request = provider.calls[-1]
    assert [m["role"] for m in last_request] == ["user", "assistant", "user", "assistant", "user"]
    assert last_request[0]["content"] == "my name is Sam"


def test_reply_is_streamed():
    chunks = []
    Agent(FakeProvider(), AssistantConfig()).handle_turn("hi", on_text=chunks.append)
    assert len(chunks) > 1


def test_failed_turn_leaves_history_untouched():
    agent = Agent(FakeProvider(fail_on=2), AssistantConfig())
    agent.handle_turn("first")
    before = list(agent.history)

    result = agent.handle_turn("second")

    assert not result.ok and result.text == "network down"
    assert agent.history == before
    assert agent.handle_turn("third").ok  # and the conversation carries on


def test_system_prompt_carries_identity():
    agent = Agent(FakeProvider(), AssistantConfig(name="Jarvis", personality="Warm."))
    assert "Jarvis" in agent.system_prompt and "Warm." in agent.system_prompt


def test_config_file_loads():
    config = load_config()
    assert config.assistant.name == "Jarvis"
    assert config.model.name


# --- the provider seam, with the SDK client faked out -------------------------

class FakeStream:
    def __init__(self, message, chunks):
        self.message, self.text_stream = message, iter(chunks)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


def fake_client(stream_fn):
    return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream_fn)))


def make_message(text="Hello there.", stop_reason="end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=10, output_tokens=3, cache_read_input_tokens=None),
    )


def test_provider_sends_config_and_streams():
    seen = {}

    def stream(**kwargs):
        seen.update(kwargs)
        return FakeStream(make_message(), ["Hello ", "there."])

    provider = ClaudeProvider(ModelConfig(name="claude-opus-5-5", effort="low"))
    provider._client = fake_client(stream)
    chunks = []
    reply = provider.respond("sys", [{"role": "user", "content": "hi"}], on_text=chunks.append)

    assert reply.text == "Hello there." and chunks == ["Hello ", "there."]
    assert seen["model"] == "claude-opus-5-5"
    assert seen["output_config"] == {"effort": "low"}
    assert seen["fallbacks"] == "default"


def test_provider_turns_network_failure_into_friendly_error():
    import httpx2

    def stream(**kwargs):
        raise anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com"))

    provider = ClaudeProvider(ModelConfig())
    provider._client = fake_client(stream)
    with pytest.raises(ProviderError, match="can't reach the model"):
        provider.respond("sys", [{"role": "user", "content": "hi"}])


def test_provider_handles_refusal():
    provider = ClaudeProvider(ModelConfig())
    provider._client = fake_client(lambda **kw: FakeStream(make_message("", "refusal"), []))
    with pytest.raises(ProviderError):
        provider.respond("sys", [{"role": "user", "content": "hi"}])


def test_provider_explains_missing_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    provider = ClaudeProvider(ModelConfig(timeout_seconds=5))
    provider._client = anthropic.Anthropic(api_key=None, max_retries=0)
    with pytest.raises(ProviderError, match="API key"):
        provider.respond("sys", [{"role": "user", "content": "hi"}])
