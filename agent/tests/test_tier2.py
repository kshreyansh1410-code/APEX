"""Tier 2 checks: the tool loop, the registry, and the three capabilities. Offline."""

import json
from types import SimpleNamespace

import pytest

from jarvis.config import AssistantConfig, ModelConfig
from jarvis.core import Agent
from jarvis.provider import ClaudeProvider, ProviderError, Reply
from jarvis.tools import Registry, Tool, ToolError, build_registry
from jarvis.tools import lookup
from jarvis.tools.registry import validate


def tool_use(name, args, id_="t1"):
    return {"type": "tool_use", "id": id_, "name": name, "input": args}


def text(t):
    return {"type": "text", "text": t}


class ScriptedProvider:
    """Plays back a fixed list of assistant turns and records each request."""

    def __init__(self, *turns, stop_reasons=None):
        self.turns = list(turns)
        self.stop_reasons = list(stop_reasons or [])
        self.requests: list[list[dict]] = []
        self.tools_seen = None

    def respond(self, system, messages, tools=None, on_text=None):
        self.requests.append(list(messages))
        self.tools_seen = tools
        content = self.turns.pop(0)
        stop = self.stop_reasons.pop(0) if self.stop_reasons else (
            "tool_use" if any(b["type"] == "tool_use" for b in content) else "end_turn")
        reply_text = "".join(b["text"] for b in content if b["type"] == "text")
        if on_text and reply_text:
            on_text(reply_text)
        return Reply(text=reply_text, content=content, stop_reason=stop)


@pytest.fixture
def registry(tmp_path):
    return build_registry(tmp_path)


def last_tool_results(provider):
    return provider.requests[-1][-1]["content"]


# --- the loop ---------------------------------------------------------------

def test_tool_result_is_fed_back_and_used(registry):
    registry.run("add_task", {"title": "Review chapter 4"})
    provider = ScriptedProvider(
        [text("Let me check."), tool_use("list_tasks", {"which": "open"})],
        [text("You have one thing: review chapter 4.")],
    )
    agent = Agent(provider, AssistantConfig(), registry)
    started, ended = [], []

    result = agent.handle_turn("what's on my list?", on_tool_start=lambda n, a: started.append(n),
                               on_tool_end=lambda n, o: ended.append(o))

    assert result.ok and "review chapter 4" in result.text
    assert started == ["list_tasks"] and not ended[0].is_error
    tool_result = last_tool_results(provider)[0]
    assert tool_result["tool_use_id"] == "t1" and "Review chapter 4" in tool_result["content"]
    # History keeps the whole exchange so later turns can refer back to it.
    assert [m["role"] for m in agent.history] == ["user", "assistant", "user", "assistant"]


def test_several_tools_in_a_row_and_in_parallel(registry):
    provider = ScriptedProvider(
        [tool_use("get_current_datetime", {}, "a")],
        [tool_use("add_task", {"title": "Read paper"}, "b"), tool_use("save_note", {"text": "Paper is about RNNs"}, "c")],
        [text("Done.")],
    )
    result = Agent(provider, AssistantConfig(), registry).handle_turn("remind me and note it")

    assert result.ok and len(provider.requests) == 3
    parallel_results = last_tool_results(provider)
    assert [r["tool_use_id"] for r in parallel_results] == ["b", "c"]  # one message, both results


def test_tools_are_offered_to_the_model(registry):
    provider = ScriptedProvider([text("hi")])
    Agent(provider, AssistantConfig(), registry).handle_turn("hi")
    names = [t["name"] for t in provider.tools_seen]
    assert {"save_note", "search_notes", "add_task", "list_tasks", "lookup_topic"} <= set(names)
    assert names == sorted(names)  # stable order keeps the prompt cache warm
    assert all(t["eager_input_streaming"] for t in provider.tools_seen)


def test_failing_tool_is_explained_not_crashed(tmp_path):
    registry = build_registry(tmp_path, simulate_failure=frozenset({"list_tasks"}))
    provider = ScriptedProvider(
        [tool_use("list_tasks", {"which": "today"})],
        [text("Sorry, I couldn't open your list just now.")],
    )
    result = Agent(provider, AssistantConfig(), registry).handle_turn("what's on my list for today?")

    assert result.ok and "couldn't" in result.text
    error = last_tool_results(provider)[0]
    assert error["is_error"] and "simulated failure" in error["content"]


def test_cut_off_tool_call_is_not_run(registry):
    provider = ScriptedProvider([tool_use("save_note", {"text": "half a no"})], stop_reasons=["max_tokens"])
    agent = Agent(provider, AssistantConfig(), registry)
    result = agent.handle_turn("note this")
    assert not result.ok and agent.history == []
    assert registry.run("search_notes", {"query": ""}).content == "There are no notes yet."


def test_endless_tool_loop_is_stopped(registry):
    provider = ScriptedProvider(*[[tool_use("get_current_datetime", {})] for _ in range(3)])
    agent = Agent(provider, AssistantConfig(), registry, max_tool_rounds=2)
    result = agent.handle_turn("loop")
    assert not result.ok and agent.history == []


def test_provider_failure_mid_turn_keeps_history(registry):
    class Flaky(ScriptedProvider):
        def respond(self, *a, **kw):
            if len(self.requests) == 1:
                raise ProviderError("network down")
            return super().respond(*a, **kw)

    agent = Agent(Flaky([tool_use("list_tasks", {"which": "open"})]), AssistantConfig(), registry)
    result = agent.handle_turn("list")
    assert not result.ok and result.text == "network down" and agent.history == []


# --- the registry -----------------------------------------------------------

def test_bad_input_is_rejected_before_running(registry):
    outcome = registry.run("add_task", {"title": "x", "priority": "high"})
    assert outcome.is_error and "unexpected field 'priority'" in outcome.content
    assert registry.run("list_tasks", {"which": "someday"}).is_error
    assert registry.run("complete_task", {"task_id": "3"}).is_error
    assert registry.run("save_note", {}).is_error
    assert registry.run("save_note", "just a string").is_error
    assert registry.run("list_tasks", {"which": "open"}).content == "No open tasks."  # nothing was added


def test_unknown_tool(registry):
    assert registry.run("send_email", {}).is_error


def test_consequential_tools_never_run_without_approval(registry):
    registry.run("add_task", {"title": "Old task"})
    refused = registry.run("delete_task", {"task_id": 1})
    assert refused.is_error and "confirmation" in refused.content
    assert "Old task" in registry.run("list_tasks", {"which": "open"}).content

    registry.approver = lambda tool, args, description: False
    assert registry.run("delete_task", {"task_id": 1}).is_error
    registry.approver = lambda tool, args, description: True
    assert not registry.run("delete_task", {"task_id": 1}).is_error
    assert registry.run("list_tasks", {"which": "open"}).content == "No open tasks."


def test_buggy_tool_is_contained():
    registry = Registry()

    def broken():
        return 1 / 0

    registry.register(Tool("broken", "x", {"type": "object", "properties": {}}, broken))
    outcome = registry.run("broken", {})
    assert outcome.is_error and "ZeroDivisionError" in outcome.content


def test_duplicate_tool_names_are_rejected(registry):
    with pytest.raises(ValueError):
        registry.register(Tool("save_note", "x", {"type": "object"}, lambda: ""))


def test_validate_does_not_treat_bools_as_ints():
    schema = {"properties": {"n": {"type": "integer"}}}
    assert validate({"n": True}, schema) and validate({"n": 2}, schema) is None


# --- capability 1: notes ----------------------------------------------------

def test_notes_save_and_search(registry, tmp_path):
    registry.run("save_note", {"text": "The Krebs cycle happens in the mitochondria", "topic": "biology"})
    registry.run("save_note", {"text": "Transformers use self-attention", "topic": "ml"})

    found = registry.run("search_notes", {"query": "where does the krebs cycle happen?"}).content
    assert "mitochondria" in found and "self-attention" not in found
    assert "No notes match" in registry.run("search_notes", {"query": "volcanoes"}).content
    # Stored as plain, readable JSON.
    stored = json.loads((tmp_path / "notes.json").read_text())
    assert stored[0]["topic"] == "biology"


def test_hand_corrupted_store_is_reported(registry, tmp_path):
    (tmp_path / "notes.json").write_text("[{oops")
    outcome = registry.run("search_notes", {"query": "x"})
    assert outcome.is_error and "isn't valid JSON" in outcome.content


# --- capability 2: tasks ----------------------------------------------------

def test_tasks_today_includes_overdue_and_complete_works(registry):
    from datetime import date, timedelta

    today = date.today()
    registry.run("add_task", {"title": "Overdue reading", "due": (today - timedelta(days=2)).isoformat()})
    registry.run("add_task", {"title": "Due today", "due": today.isoformat()})
    registry.run("add_task", {"title": "Next week", "due": (today + timedelta(days=7)).isoformat()})

    todays = registry.run("list_tasks", {"which": "today"}).content
    assert "Overdue reading" in todays and "Due today" in todays and "Next week" not in todays
    assert "1 overdue" in todays

    registry.run("complete_task", {"task_id": 2})
    assert "Due today" not in registry.run("list_tasks", {"which": "open"}).content
    assert "[done]" in registry.run("list_tasks", {"which": "all"}).content


def test_task_errors_are_plain_language(registry):
    bad_date = registry.run("add_task", {"title": "x", "due": "next friday"})
    assert bad_date.is_error and "YYYY-MM-DD" in bad_date.content
    missing = registry.run("complete_task", {"task_id": 99})
    assert missing.is_error and "no task #99" in missing.content


# --- capability 3: lookup ---------------------------------------------------

def lookup_registry(fetch):
    registry = Registry()
    lookup.register(registry, fetch=fetch)
    return registry


def test_lookup_returns_sourced_summary():
    def fetch(url):
        if "opensearch" in url:
            assert "Krebs+cycle" in url
            return ["Krebs cycle", ["Citric acid cycle"], [""], ["https://en.wikipedia.org/wiki/Citric_acid_cycle"]]
        assert url.endswith("/page/summary/Citric_acid_cycle")
        return {"title": "Citric acid cycle", "extract": "The citric acid cycle is a series of reactions.",
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Citric_acid_cycle"}}}

    content = lookup_registry(fetch).run("lookup_topic", {"topic": "Krebs cycle"}).content
    assert content.startswith("Source: Wikipedia") and "series of reactions" in content


def test_lookup_no_match():
    outcome = lookup_registry(lambda url: ["zzz", [], [], []]).run("lookup_topic", {"topic": "zzqx"})
    assert not outcome.is_error and "no article" in outcome.content


def test_lookup_network_failure_is_a_tool_error():
    def fetch(url):
        raise ToolError("couldn't reach Wikipedia (Tunnel connection failed)")

    outcome = lookup_registry(fetch).run("lookup_topic", {"topic": "Krebs cycle"})
    assert outcome.is_error and "couldn't reach Wikipedia" in outcome.content


def test_real_fetch_failure_becomes_tool_error():
    with pytest.raises(ToolError):
        lookup._get_json("http://127.0.0.1:9/nothing", timeout=2)


# --- the provider seam with tools ------------------------------------------

def test_provider_passes_tools_and_retries_malformed_tool_json():
    calls = []

    class Stream:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        @property
        def text_stream(self):
            if len(calls) == 1:
                raise ValueError("unparseable tool input")
            return iter([])

        def get_final_message(self):
            return SimpleNamespace(content=[], stop_reason="end_turn",
                                   usage=SimpleNamespace(input_tokens=1, output_tokens=1, cache_read_input_tokens=0))

    def stream(**kwargs):
        calls.append(kwargs)
        return Stream()

    provider = ClaudeProvider(ModelConfig())
    provider._client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream)))
    provider.respond("sys", [{"role": "user", "content": "hi"}], tools=[{"name": "x"}])
    assert len(calls) == 2 and calls[-1]["tools"] == [{"name": "x"}]
