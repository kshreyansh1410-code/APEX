# Jarvis

A voice-first personal assistant for research and study. The spec and build plan are in
[`../AGENT.md`](../AGENT.md).

**Current tier: 3, ears and mouth.** Talk to Jarvis by holding a key, or type to it. Both use the
same brain and tools. It has no long-term memory yet.

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

## Voice (on your own computer, not Codespaces)

```bash
pip install -r requirements-voice.txt     # Linux also needs: sudo apt install libportaudio2
```

Add `DEEPGRAM_API_KEY` and `ELEVENLABS_API_KEY` to `.env`. If your ElevenLabs voice came from the
public Voice Library, add it to your account (on its page) first.

```bash
python -m jarvis --voice-check   # checks speakers, ElevenLabs, mic and Deepgram, one step at a time
python -m jarvis --voice         # hold Space, speak, release
```

- You'll hear a high beep when the mic opens and a low one when it closes. `… transcribing` shows straight away,
  then `you (heard) › …` shows what Jarvis heard, so you can tell whether a wrong answer came from mishearing
  or from the brain.
- Jarvis starts speaking after its first sentence, while the rest is still being written.
- **To interrupt, press the key again.** Jarvis stops talking at once, drops that reply, and listens.
- **macOS:** the first time, allow your terminal app under System Settings → Privacy & Security → **Accessibility**
  and **Input Monitoring** (to see the key) and **Microphone**. Then restart the terminal.
- **Linux:** hold-to-talk needs an X11 session. On Wayland, or anywhere the key can't be watched, Jarvis switches
  to Enter-to-talk automatically. You can also choose it with `ptt_mode = "enter"`.
- Change the key, voice, models or beeps under `[voice]` in `config.toml`.
- Text mode (`python -m jarvis`) still works exactly as before.

## Layout

| File | Job |
|---|---|
| `jarvis/provider.py` | The only code that talks to the model SDK. Swap models, retries, and costs here. |
| `jarvis/core.py` | `Agent.handle_turn()`, the single entry point that typed, spoken, and heartbeat turns all use. |
| `jarvis/tools/` | The tool registry plus one module per capability. **New capability = new module + one line in `tools/__init__.py`.** |
| `jarvis/voice/` | Voice adapter: `stt.py` (Deepgram seam), `tts.py` (ElevenLabs seam), `speaker.py` (sentence-by-sentence speech that can be interrupted), `ptt.py` (push-to-talk), `session.py` (feeds what it hears into the same `handle_turn()`). |
| `jarvis/cli.py` | The text interface. It stays forever for debugging, and shows each tool call as `↳ tool(args) — ok/failed`. |
| `jarvis/config.py` | Loads `config.toml` and `.env`. |

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests use a fake model, so they need no key and no network.

## Verify Tier 3 by hand

1. Run `python -m jarvis --voice-check` and confirm every line says `ok`.
2. Run `python -m jarvis --voice`, hold Space and ask "what's on my list for today?", then release. You should see
   `you (heard) › …`, then `↳ list_tasks`, and hear the answer in your chosen voice.
3. Ask for something long ("explain photosynthesis in detail"), then press Space while it's talking. It should
   stop at once and listen.
4. Run `python -m jarvis` and confirm typing still works.

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
