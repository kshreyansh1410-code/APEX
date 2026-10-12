# Jarvis

A voice-first personal assistant for research and study. The spec and build plan are in
[`../AGENT.md`](../AGENT.md).

**Current tier: 2, the hands.** A streaming text conversation that can use tools. It has no
voice or long-term memory yet.

| Tool | What it does | Safe to run on its own? |
|---|---|---|
| `save_note`, `search_notes` | Research notes, stored in `data/notes.json` | yes |
| `add_task`, `list_tasks`, `complete_task` | Study to-do list, stored in `data/tasks.json` | yes |
| `delete_task` | Removes a task | **no**: refuses until the Tier 6 confirmation gate exists |
| `get_current_datetime` | Today's date, for due dates | yes |
| `lookup_topic` | Short sourced summary from Wikipedia | yes (read-only) |

`data/` holds your personal data as plain JSON you can open and edit. Git ignores it.

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
| `jarvis/tools/` | The tool registry plus one module per capability. **New capability = new module + one line in `tools/__init__.py`.** |
| `jarvis/cli.py` | The text interface. It stays forever for debugging, and shows each tool call as `↳ tool(args) — ok/failed`. |
| `jarvis/config.py` | Loads `config.toml` and `.env`. |

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests use a fake model, so they need no key and no network.

## Verify Tier 2 by hand

1. Say "remind me to review chapter 4 tomorrow", then "what's on my list?". You should see
   `↳ get_current_datetime`, `↳ add_task`, then `↳ list_tasks`, and a natural reply that uses the result.
2. Say "note that the Krebs cycle happens in the mitochondria", then "what did I note about the Krebs cycle?".
3. Ask "look up the Krebs cycle". The answer should name Wikipedia as its source.
4. Make a tool fail on purpose: set `fail_tools = ["list_tasks"]` under `[debug]` in `config.toml`,
   restart, and ask what's on your list. Jarvis should explain the problem rather than crash.
   Set it back to `[]` afterwards.
5. Ask it to delete a task. It should tell you it can't do that without your confirmation.

## Verify Tier 1 by hand

1. Tell it something ("I'm reading about photosynthesis"). A couple of turns later, ask what you're
   reading about. It should remember.
2. Quit and restart, then ask again. It should **not** know. That's expected until long-term
   memory arrives in Tier 4.
3. Turn off your Wi-Fi and send a message. You should get a short, plain message and a fresh
   prompt, not a crash.
