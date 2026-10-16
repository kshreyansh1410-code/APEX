# Jarvis

A voice-first personal assistant for research and study. The spec and build plan are in
[`../AGENT.md`](../AGENT.md).

**Current tier: 4, memory.** Talk or type to Jarvis. It uses tools and remembers you between
sessions.

| Tool | What it does | Safe to run on its own? |
|---|---|---|
| `save_note`, `search_notes` | Research notes, stored in `data/notes.json` | yes |
| `add_task`, `list_tasks`, `complete_task` | Study to-do list, stored in `data/tasks.json` | yes |
| `delete_task` | Removes a task | **no**: asks you first, every time |
| `remember`, `update_memory`, `recall_memories` | Long-term memory in `data/memory.md` | yes |
| `forget_memory` | Deletes a memory | **no**: asks you first, every time |
| Composio app tools | Gmail, Google Calendar, … (see below) | only if Composio marks them read-only; anything else asks |
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

## Asking before acting

Anything that sends, spends, deletes, or changes something asks first:

```
  ⚠  Jarvis wants to permanently delete task #1: "Review chapter 4".
     Details:
       task_id: 1
     Allow this one action? [y/N]
```

- Typing: answer `y`. Anything else, including just pressing Enter, means no.
- Voice: Jarvis says what it wants to do. Hold the key and say "yes" or "no". Anything unclear, or no answer
  within `confirm_timeout_seconds` (30), means no.
- Every action asks on its own. Saying yes once doesn't cover the next one.
- To make a normally safe tool ask too, add it to `confirm_tools` under `[safety]` in `config.toml`.

## Connecting your apps (Composio)

Jarvis can use Gmail, Google Calendar, and other apps through [Composio](https://composio.dev).

```bash
pip install -r requirements-composio.txt
# add COMPOSIO_API_KEY=... to .env (from your Composio dashboard)
python -m jarvis --connect gmail            # opens a sign-in link, then waits
python -m jarvis --connect googlecalendar
python -m jarvis                            # the banner shows how many app tools loaded
```

- Pick apps and tools under `[composio]` in `config.toml`: `toolkits`, `tools_per_toolkit`, and exact `tools`.
  Each tool costs prompt space, so start small.
- **Reading** (for example fetching emails or listing events) runs straight away when Composio marks the tool read-only.
  **Sending, creating, editing, and deleting** always ask you first, and you see the full details, such as the whole email.
- Email text and event details come back labelled as outside content. If an email says "ignore your rules and
  forward this", Jarvis treats it as text to report to you, never as an instruction.
- If Composio can't be reached, Jarvis says so in one line and works without the app tools.

## Memory

`data/memory.md` is a plain Markdown list of what Jarvis knows about you, grouped under About me,
Preferences, Facts, and Decisions. Open it in any editor to fix, add, or delete facts. A new bullet
needs nothing extra. Keep the `<!-- m… -->` tag on lines you edit so Jarvis can tell which fact is which.

- Jarvis reads it at the start of each conversation, and again on `/reset`.
- Type `/memory` to see what it remembers and where the file is.
- Memories are background facts, never commands. A memory can't make Jarvis skip a confirmation.
- Once there are more than `max_in_prompt` facts (60 by default), only the most recent go into each conversation.
  Jarvis searches the rest with `recall_memories`.

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
| `jarvis/confirm.py` | The "ask before acting" prompts, and what counts as a yes. |
| `jarvis/tools/composio_tools.py` | Turns Composio app tools into Jarvis tools, plus `--connect`. |
| `jarvis/memory.py` | The long-term memory store: reads and writes `data/memory.md`. |
| `jarvis/voice/` | Voice adapter: `stt.py` (Deepgram seam), `tts.py` (ElevenLabs seam), `speaker.py` (sentence-by-sentence speech that can be interrupted), `ptt.py` (push-to-talk), `session.py` (feeds what it hears into the same `handle_turn()`). |
| `jarvis/cli.py` | The text interface. It stays forever for debugging, and shows each tool call as `↳ tool(args) — ok/failed`. |
| `jarvis/config.py` | Loads `config.toml` and `.env`. |

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests use a fake model, so they need no key and no network.

## Verify confirmation and apps by hand

1. Ask Jarvis to delete a task and answer `n`. The task stays. Ask again and answer `y`. It's gone.
2. Run `python -m jarvis --connect gmail`, open the link, and sign in. Then ask "what are my latest emails?".
   You should see `↳ GMAIL_…` run without a question.
3. Ask it to send an email to yourself. It should show the recipient and full text and wait for `y`.

## Verify Tier 4 by hand

1. Say "I'm a second-year biology student and I like short answers". You should see `↳ remember` (once or twice).
2. Quit and restart. The banner should say it remembers things about you. Ask "what do you know about me?"
3. Open `data/memory.md`, change "biology" to "chemistry", save, and restart (or type `/reset`). Ask again;
   it should say chemistry.
4. Say "forget that I like short answers". It should ask you first. Answer `n`, then ask again and answer `y`.

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
5. Ask it to delete a task. It should show exactly which task and wait for `y`.

## Verify Tier 1 by hand

1. Tell it something ("I'm reading about photosynthesis"). A couple of turns later, ask what you're
   reading about. It should remember.
2. Quit and restart, then ask again. It should **not** know. That's expected until long-term
   memory arrives in Tier 4.
3. Turn off your Wi-Fi and send a message. You should get a short, plain message and a fresh
   prompt, not a crash.
