"""Voice adapter: push-to-talk in, speech out, around the *same* agent core.

press → stop talking, cancel any turn in flight, start recording
release → transcribe → show what was heard → Agent.handle_turn() → speak as it streams
"""

import queue
import sys
import threading
from typing import Callable

from ..core import Agent, TurnCancelled
from .audio import tone, to_wav
from .ptt import PRESS, RELEASE, EnterToTalk
from .speaker import Speaker
from .stt import Transcriber, VoiceError
from .tts import SAMPLE_RATE

MIN_SPEECH_SECONDS = 0.3


class VoiceSession:
    def __init__(self, agent: Agent, transcriber: Transcriber, speaker: Speaker, recorder, ptt,
                 events: queue.Queue, play_earcon: Callable[[bytes], None] | None = None,
                 write: Callable[[str], None] | None = None):
        self.agent, self.transcriber, self.speaker = agent, transcriber, speaker
        self.recorder, self.ptt, self.events = recorder, ptt, events
        self.play_earcon = play_earcon
        self._write = write or _stdout_write
        self.name = agent.assistant.name
        self._cancel = threading.Event()
        self._recording = False
        self._worker: threading.Thread | None = None

    def run(self) -> None:
        try:
            self.ptt.start()
        except VoiceError as e:
            if isinstance(self.ptt, EnterToTalk):
                raise
            self._line(f"[{e}] Falling back to Enter-to-talk.")
            self.ptt = EnterToTalk(self.events)
            self.ptt.start()
        self._line(f"{self.name} is listening for push-to-talk. {self.ptt.hint}")
        try:
            while True:
                try:
                    event = self.events.get(timeout=0.2)  # short wait so Ctrl-C is noticed
                except queue.Empty:
                    continue
                if event == PRESS:
                    self.on_press()
                elif event == RELEASE:
                    self.on_release()
        except KeyboardInterrupt:
            pass
        finally:
            self.interrupt()
            self.ptt.stop()
            self._line(f"{self.name} › Bye.")

    def interrupt(self) -> None:
        """Stop talking and abandon any turn still in progress."""
        self._cancel.set()
        self.speaker.interrupt()

    def on_press(self) -> None:
        self.interrupt()
        self.speaker.reset()
        self._cancel = threading.Event()
        self._earcon(tone(880, 60))
        try:
            self.recorder.start()
        except VoiceError as e:
            self._line(f"[{e}]")
            return
        self._recording = True
        self._line("● listening…")

    def on_release(self) -> None:
        if not self._recording:
            return
        self._recording = False
        pcm = self.recorder.stop()
        self._earcon(tone(660, 60))
        if len(pcm) < SAMPLE_RATE * 2 * MIN_SPEECH_SECONDS:
            self._line("(too short: hold the key the whole time you're speaking)")
            return
        # A sign of life the moment the key comes up, so silence never reads as "broken".
        self._line("… transcribing")
        self._worker = threading.Thread(target=self._turn, args=(pcm, self._cancel), daemon=True, name="turn")
        self._worker.start()

    def _turn(self, pcm: bytes, cancel: threading.Event) -> None:
        try:
            heard = self.transcriber.transcribe(to_wav(pcm))
        except VoiceError as e:
            self._fail(str(e), cancel)
            return
        if cancel.is_set():
            return
        if not heard:
            self._fail("Sorry, I didn't catch that.", cancel)
            return
        # Show what the ears heard, so a wrong answer can be traced to ears or brain.
        self._line(f"you (heard) › {heard}")

        def on_text(chunk: str) -> None:
            if cancel.is_set():
                raise TurnCancelled
            self._write(chunk)
            self.speaker.feed(chunk)

        def on_tool_start(name: str, args: dict) -> None:
            shown = ", ".join(f"{k}={v!r}" for k, v in (args or {}).items())
            self._line(f"\n  ↳ {name}({shown})")

        def on_tool_end(name: str, outcome) -> None:
            self._line("     " + (f"failed: {outcome.content}" if outcome.is_error else "ok"))

        self._write(f"{self.name} › ")
        result = self.agent.handle_turn(heard, on_text=on_text, on_tool_start=on_tool_start,
                                        on_tool_end=on_tool_end, cancel=cancel)
        if result.cancelled or cancel.is_set():
            self._line("\n(interrupted)")
            return
        self._line("")
        if result.ok:
            self.speaker.finish()
        else:
            self._fail(result.text, cancel)

    def _earcon(self, pcm: bytes) -> None:
        if self.play_earcon:
            try:
                self.play_earcon(pcm)
            except VoiceError:
                pass  # a missing beep must never stop a conversation

    def _fail(self, message: str, cancel: threading.Event) -> None:
        self._line(f"[{message}]")
        if not cancel.is_set():
            self.speaker.say(message)

    def _line(self, text: str) -> None:
        self._write(text + "\n")


def _stdout_write(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()
