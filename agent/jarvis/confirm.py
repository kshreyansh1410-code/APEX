"""Asking the user for a yes before a consequential action. Unclear always means no."""

import re
import sys
from typing import Callable

_YES = {"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm", "confirmed", "approve", "approved", "y"}
_YES_PHRASES = ("go ahead", "do it", "please do")
_NO = {"no", "nope", "nah", "don't", "dont", "do not", "stop", "cancel", "wait", "not", "never", "n"}


def parse_yes(answer: str) -> bool:
    """True only for a clear yes. "yes", "yeah go ahead" → True; "no", "maybe", "yes, no wait" → False."""
    text = answer.lower().strip()
    words = re.findall(r"[a-z']+", text)
    if not words:
        return False
    if any(w in _NO for w in words) or "do not" in text:
        return False
    return words[0] in _YES or any(text.startswith(p) for p in _YES_PHRASES)


def text_approver(read: Callable[[str], str] = input, write: Callable[[str], None] | None = None):
    """An approver for the typed interface: show exactly what will happen, wait for y/N."""
    write = write or (lambda s: (sys.stdout.write(s), sys.stdout.flush()))

    def approve(tool, args, description: str) -> bool:
        write(f"\n\n  ⚠  Jarvis wants to {description}.\n")
        if args:  # always show everything, e.g. the full text of an email about to be sent
            details = "\n".join(f"       {k}: {v}" for k, v in args.items())
            write(f"     Details:\n{details}\n")
        try:
            answer = read("     Allow this one action? [y/N] ")
        except (EOFError, KeyboardInterrupt):
            answer = ""
        approved = parse_yes(answer)
        write("     → approved\n" if approved else "     → not approved, nothing was done\n")
        return approved

    return approve
