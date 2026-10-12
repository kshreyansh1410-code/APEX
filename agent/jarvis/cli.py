"""Text interface. Kept forever: it's how every later tier gets debugged."""

import sys

from .config import load_config
from .core import Agent
from .provider import ClaudeProvider

HELP = "Commands: /reset (forget this conversation), /quit (or Ctrl-D)."


def main() -> None:
    config = load_config()
    agent = Agent(ClaudeProvider(config.model), config.assistant)
    name = config.assistant.name
    tty = sys.stdout.isatty()

    print(f"{name} is ready. {HELP}\n")
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
            print(f"{name} › Fresh start. I've forgotten this conversation.\n")
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

        try:
            result = agent.handle_turn(user_text, on_text=on_text)
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


if __name__ == "__main__":
    main()
