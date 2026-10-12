# Jarvis

A voice-first personal assistant for research and study. The spec and build plan are in
[`../AGENT.md`](../AGENT.md).

**Current tier: 1, the brain.** A streaming text conversation that remembers earlier turns
in the same session. It has no tools, voice, or long-term memory yet.

## Run it

```bash
cd agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then put your Anthropic API key in .env
python -m jarvis
```

Type to talk. `/reset` forgets the conversation, and `/quit` or Ctrl-D exits. Ctrl-C while
Jarvis is answering stops that answer and discards the turn.

Settings such as the model, effort, and personality are in `config.toml`. Keys go only in `.env`,
which git ignores.

## Layout

| File | Job |
|---|---|
| `jarvis/provider.py` | The only code that talks to the model SDK. Swap models, retries, and costs here. |
| `jarvis/core.py` | `Agent.handle_turn()`, the single entry point that typed, spoken, and heartbeat turns all use. |
| `jarvis/cli.py` | The text interface. It stays forever for debugging. |
| `jarvis/config.py` | Loads `config.toml` and `.env`. |

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests use a fake model, so they need no key and no network.

## Verify Tier 1 by hand

1. Tell it something ("I'm reading about photosynthesis"). A couple of turns later, ask what you're
   reading about. It should remember.
2. Quit and restart, then ask again. It should **not** know. That's expected until long-term
   memory arrives in Tier 4.
3. Turn off your Wi-Fi and send a message. You should get a short, plain message and a fresh
   prompt, not a crash.
