# Jarvis — spec

The single source of truth for what we're building and why. Update this file when a decision changes.

## Identity

| | |
|---|---|
| **Name** | Jarvis |
| **Wake phrase** | "Hey Jarvis" |
| **What it's for** | A voice-first assistant for my research and educational work: helping me learn, keep track of what I'm studying, and find things out. |
| **Who it's for** | Just me (single user). *(default, assumed)* |
| **Personality** | Warm, plain-spoken, and brief. Explains clearly, like a patient tutor, and admits when it doesn't know. *(default, assumed)* |

## First three capabilities *(assumed from "research and educational purposes"; change freely)*

1. **Research notes**: save a note and search or recall my notes later ("note that the Krebs cycle happens in the mitochondria", "what did I note about transformers?").
2. **Study reminders and tasks**: keep a small list of things to read, review, or do, with optional due dates ("remind me to review chapter 4 on Friday", "what's on my list today?").
3. **Look things up**: fetch a short, sourced summary of a topic from a public reference such as Wikipedia, so answers can cite where they came from.

These become the first tools (Tier 2) and the first test cases.

## Stack and model *(defaults, assumed)*

- **Language:** Python 3.11+, small and readable, no heavy framework. Lives in `agent/`, separate from the REVLUME landing page that also lives in this repo.
- **Brain:** Claude via the official `anthropic` SDK, default model `claude-opus-5-5`. Set in `agent/config.toml` and kept behind a thin provider seam (`agent/jarvis/provider.py`) so it can be swapped.
- **Speech-to-text:** Deepgram, behind its own seam (Tier 3).
- **Text-to-speech:** ElevenLabs, behind its own seam (Tier 3). Voice: [`wDsJlOXPqcvIUKdLXjDs`](https://elevenlabs.io/voices/wDsJlOXPqcvIUKdLXjDs), my choice, stored as `elevenlabs_voice_id` in `agent/config.toml`.
- **Where it runs:** laptop first. The background "heartbeat" loop (Tier 5) is kept separate so it can move to an always-on host without a rewrite.

## How I talk to it

1. **Typing** (Tier 1). This path stays forever for debugging.
2. **Push-to-talk** (Tier 3): hold a key, speak, release.
3. **"Hey Jarvis" open-mic wake word**: later, after everything else is solid. openWakeWord ships a pretrained `hey_jarvis` model we can use.

## Never without asking *(default list)*

Jarvis must get my explicit "yes", every time and for each action, before it:

- sends any message (email, chat, post),
- spends money,
- deletes data (including notes, tasks, and memories),
- changes a setting.

Enforced by a hard confirmation gate in Tier 6. Since Tier 2 every tool is flagged safe or consequential, and consequential tools (so far only `delete_task`) **refuse to run** until that gate exists.

## Proactivity

Yes, but **quiet by default**. Jarvis has to earn the right to interrupt. Most findings go to a calm log I can check when I like. Notices are held until I'm back, never dropped. Quiet hours default to **22:00–08:00, local time**, and are configurable.

## Secrets

API keys live only in environment variables or a git-ignored `agent/.env` file (`ANTHROPIC_API_KEY`, `DEEPGRAM_API_KEY`, `ELEVENLABS_API_KEY`). They never go in source files or chat.

## Build plan

| Tier | What | Status |
|---|---|---|
| 0 | Interview + this spec | done |
| 1 | Brain: streaming text conversation loop | built; hand check pending (needs your API key) |
| 2 | Hands: tool registry + the three tools above | built; hand check pending |
| 3 | Ears and mouth: push-to-talk, Deepgram, ElevenLabs | |
| 4 | Memory: durable, human-editable facts | |
| 5 | Heartbeat: quiet-by-default proactive checks | |
| 6 | Rails: confirmation gate, injection defense, config, audit log, kill switch | |
