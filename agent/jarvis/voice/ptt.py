"""Push-to-talk: turns a key into "press" / "release" events on a queue.

"hold" mode: hold a key (default Space) while you speak. Uses pynput, which listens
to the keyboard globally; on macOS your terminal app needs Accessibility /
Input Monitoring permission, and on Linux it needs an X11 session.
"enter" mode: press Enter to start talking and Enter again to stop. Works anywhere.
"""

import queue
import sys
import threading

from .stt import VoiceError

PRESS, RELEASE = "press", "release"


class EnterToTalk:
    hint = "Press Enter to talk, Enter again to stop. Ctrl-C quits."

    def __init__(self, events: queue.Queue):
        self.events = events
        self._down = False

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True, name="enter-ptt").start()

    def _run(self) -> None:
        for _ in sys.stdin:
            self.events.put(RELEASE if self._down else PRESS)
            self._down = not self._down

    def stop(self) -> None:
        pass


class HoldToTalk:
    def __init__(self, events: queue.Queue, key_name: str = "space"):
        self.events = events
        self.key_name = key_name
        self.hint = f"Hold {key_name} while you speak, release to send. Ctrl-C quits."
        self._down = False
        self._listener = None
        self._quiet = _QuietTerminal()

    def start(self) -> None:
        try:
            from pynput import keyboard
        except ModuleNotFoundError as e:
            if e.name == "pynput":
                raise VoiceError("Hold-to-talk needs pynput: pip install -r requirements-voice.txt") from None
            raise VoiceError(f"Hold-to-talk can't watch the keyboard here ({e}).") from None
        except Exception as e:  # e.g. no X display on Linux
            reason = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
            raise VoiceError(f"Hold-to-talk can't watch the keyboard here ({reason}).") from None

        target = getattr(keyboard.Key, self.key_name, None) or keyboard.KeyCode.from_char(self.key_name)

        def on_press(key):
            if key == target and not self._down:  # ignore key auto-repeat
                self._down = True
                self.events.put(PRESS)

        def on_release(key):
            if key == target and self._down:
                self._down = False
                self.events.put(RELEASE)
                self._quiet.discard_typed()

        self._quiet.enter()
        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
        self._quiet.exit()


class _QuietTerminal:
    """Holding Space would otherwise type spaces into the terminal; hide and discard them."""

    def __init__(self):
        self._saved = None

    def enter(self) -> None:
        try:
            import termios

            fd = sys.stdin.fileno()
            self._saved = termios.tcgetattr(fd)
            quiet = termios.tcgetattr(fd)
            quiet[3] &= ~(termios.ECHO | termios.ICANON)
            termios.tcsetattr(fd, termios.TCSADRAIN, quiet)
        except Exception:
            self._saved = None  # Windows, or not a real terminal

    def discard_typed(self) -> None:
        try:
            import termios

            termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
        except Exception:
            try:
                import msvcrt

                while msvcrt.kbhit():
                    msvcrt.getwch()
            except Exception:
                pass

    def exit(self) -> None:
        if self._saved is not None:
            import termios

            self.discard_typed()
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._saved)
            self._saved = None
