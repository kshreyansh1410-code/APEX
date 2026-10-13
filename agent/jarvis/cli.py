"""Text interface. Kept forever: it's how every later tier gets debugged."""

import argparse
import sys

from .config import Config, load_config
from .core import Agent
from .memory import MemoryStore
from .provider import ClaudeProvider
from .tools import build_registry

HELP = "Commands: /memory (what I remember), /reset (new conversation), /quit (or Ctrl-D)."


def build_agent(config: Config) -> Agent:
    """The one agent core, shared by the text and voice interfaces."""
    memory = MemoryStore(config.memory_path)
    registry = build_registry(config.data_dir, frozenset(config.debug.fail_tools), memory)
    return Agent(ClaudeProvider(config.model), config.assistant, registry, config.tools.max_rounds,
                 memory=memory, max_memories_in_prompt=config.memory.max_in_prompt)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m jarvis")
    parser.add_argument("--voice", action="store_true", help="talk with push-to-talk instead of typing")
    parser.add_argument("--voice-check", action="store_true", help="test mic, speakers, Deepgram and ElevenLabs")
    args = parser.parse_args()
    config = load_config()

    if args.voice or args.voice_check:
        from .voice import VoiceError, build_session, voice_check

        if args.voice_check:
            sys.exit(0 if voice_check(config) else 1)
        try:
            session = build_session(build_agent(config), config)
            session.run()
        except VoiceError as e:
            print(f"[{e}]\nText mode still works: python -m jarvis")
            sys.exit(1)
        return

    run_text(build_agent(config), config)


def run_text(agent: Agent, config: Config) -> None:
    name = config.assistant.name
    tty = sys.stdout.isatty()

    remembered = len(agent.memory.load()) if agent.memory else 0
    known = f" I remember {remembered} thing{'s' if remembered != 1 else ''} about you." if remembered else ""
    print(f"{name} is ready.{known} {HELP}\n")
    while True:
        try:
            user_text = input("you › ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_text:
            continue
        if user_text in ("/quit", "/exit"):
            break
        if user_text == "/reset":
            agent.reset()
            print(f"{name} › Fresh start. I've forgotten this conversation (but not my long-term memory).\n")
            continue
        if user_text == "/memory":
            show_memory(agent, config)
            continue

        # Show a sign of life right away, then replace it with the streamed reply.
        sys.stdout.write(f"{name} › " + ("thinking…" if tty else ""))
        sys.stdout.flush()
        started = False

        def on_text(chunk: str) -> None:
            nonlocal started
            if not started and tty:
                sys.stdout.write(f"\r\033[K{name} › ")
            started = True
            sys.stdout.write(chunk)
            sys.stdout.flush()

        def on_tool_start(tool: str, args: dict) -> None:
            nonlocal started
            shown = ", ".join(f"{k}={v!r}" for k, v in (args or {}).items())
            prefix = "\r\033[K" if tty and not started else ("\n" if started else "")
            sys.stdout.write(f"{prefix}  ↳ {tool}({shown})")
            sys.stdout.flush()

        def on_tool_end(tool: str, outcome) -> None:
            nonlocal started
            status = f"failed: {outcome.content}" if outcome.is_error else "ok"
            sys.stdout.write(f" — {status}\n{name} › ")
            sys.stdout.flush()
            started = True

        try:
            result = agent.handle_turn(user_text, on_text=on_text, on_tool_start=on_tool_start, on_tool_end=on_tool_end)
        except KeyboardInterrupt:
            print("\n(stopped — that turn was discarded)\n")
            continue
        except Exception as e:  # last resort: a bug must never end the session
            print(f"\n[Something went wrong on my side ({type(e).__name__}: {e}). That turn was discarded.]\n")
            continue

        if not result.ok:
            if tty and not started:
                sys.stdout.write(f"\r\033[K{name} › ")
            elif started:
                # The stream died partway; the partial reply was not kept.
                sys.stdout.write("\n")
            print(f"[{result.text}]\n")
        else:
            print("\n")

    print(f"{name} › Bye.")


def show_memory(agent: Agent, config: Config) -> None:
    memories = agent.memory.load() if agent.memory else []
    print(f"Long-term memory ({len(memories)}) — edit by hand at {config.memory_path}")
    for m in memories:
        print(f"  {m.line()}")
    print("Hand edits take effect on /reset or the next start.\n")


if __name__ == "__main__":
    main()
