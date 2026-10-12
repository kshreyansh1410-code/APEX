"""Speaks a streamed reply sentence by sentence, so Jarvis starts talking
before the model has finished writing. Can be cut off at any moment."""

import queue
import re
import threading
from typing import Callable

from .stt import VoiceError
from .tts import Synthesizer

_SENTENCE_END = re.compile(r"(?<=[.!?…])[\"')\]]*\s+|\n{2,}|\n(?=\s*[-*\d])")
_MARKDOWN = re.compile(r"[*_`#>]+|\[([^\]]*)\]\([^)]*\)")


def clean_for_speech(text: str) -> str:
    """Strip markdown symbols that sound silly read aloud; keep link text."""
    text = _MARKDOWN.sub(lambda m: m.group(1) or "", text)
    return re.sub(r"\s+", " ", text).strip()


class SentenceSplitter:
    """Collects streamed text and hands back complete sentences as they finish."""

    def __init__(self):
        self.buffer = ""

    def feed(self, chunk: str) -> list[str]:
        self.buffer += chunk
        sentences = []
        while (m := _SENTENCE_END.search(self.buffer)) is not None:
            sentences.append(self.buffer[: m.end()])
            self.buffer = self.buffer[m.end():]
        return [s for s in (clean_for_speech(s) for s in sentences) if s]

    def flush(self) -> list[str]:
        rest, self.buffer = clean_for_speech(self.buffer), ""
        return [rest] if rest else []


class Speaker:
    """A worker thread that synthesizes and plays queued sentences in order."""

    def __init__(self, synth: Synthesizer, play: Callable[[bytes], None], stop_playback: Callable[[], None],
                 resume_playback: Callable[[], None], on_error: Callable[[str], None] = print):
        self.synth, self.play = synth, play
        self.stop_playback, self.resume_playback = stop_playback, resume_playback
        self.on_error = on_error
        self.splitter = SentenceSplitter()
        self._queue: queue.Queue[tuple[int, str]] = queue.Queue()
        # Bumped on every interrupt; anything queued under an older generation is stale.
        self._generation = 0
        self._pending = 0  # sentences queued or being spoken
        self._done = threading.Condition()
        threading.Thread(target=self._run, daemon=True, name="speaker").start()

    # Feed streamed text in; whole sentences are queued as soon as they complete.
    def feed(self, chunk: str) -> None:
        for sentence in self.splitter.feed(chunk):
            self.say(sentence)

    def finish(self) -> None:
        for sentence in self.splitter.flush():
            self.say(sentence)

    def say(self, text: str) -> None:
        with self._done:
            self._pending += 1
        self._queue.put((self._generation, text))

    def interrupt(self) -> None:
        """Stop talking now and drop everything not yet said."""
        self._generation += 1
        self.splitter = SentenceSplitter()
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
            self._mark_done()
        self.stop_playback()

    def reset(self) -> None:
        """Ready for the next reply after an interrupt."""
        self.resume_playback()

    @property
    def speaking(self) -> bool:
        return self._pending > 0

    def wait_until_done(self, timeout: float | None = None) -> bool:
        with self._done:
            return self._done.wait_for(lambda: self._pending == 0, timeout)

    def _mark_done(self) -> None:
        with self._done:
            self._pending -= 1
            self._done.notify_all()

    def _run(self) -> None:
        while True:
            generation, text = self._queue.get()

            def stale(generation=generation) -> bool:
                return generation != self._generation

            try:
                if not stale():
                    for pcm in self.synth.stream(text, should_stop=stale):
                        if stale():
                            break
                        self.play(pcm)
            except VoiceError as e:
                self.on_error(str(e))
            except Exception as e:  # never let the speaker thread die
                self.on_error(f"Speech failed ({type(e).__name__}: {e})")
            self._mark_done()
