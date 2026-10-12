"""Microphone and speaker access. `sounddevice` is imported lazily so text mode
and the tests never need audio hardware or PortAudio."""

import io
import math
import struct
import threading
import wave

from .stt import VoiceError
from .tts import SAMPLE_RATE


def _sounddevice():
    try:
        import sounddevice
    except ImportError:
        raise VoiceError("Voice needs extra packages: pip install -r requirements-voice.txt") from None
    except OSError:
        raise VoiceError("PortAudio isn't installed. On Linux: sudo apt install libportaudio2") from None
    return sounddevice


def to_wav(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buffer.getvalue()


def tone(freq: float, ms: int, volume: float = 0.15) -> bytes:
    """A short sine blip with a fade, used as an earcon."""
    n = SAMPLE_RATE * ms // 1000
    fade = max(1, n // 5)
    return b"".join(
        struct.pack("<h", int(32767 * volume * min(1, i / fade, (n - i) / fade) * math.sin(2 * math.pi * freq * i / SAMPLE_RATE)))
        for i in range(n)
    )


class Recorder:
    """Captures the microphone between start() and stop()."""

    def __init__(self):
        self._chunks: list[bytes] = []
        self._stream = None

    def start(self) -> None:
        sd = _sounddevice()
        self._chunks = []
        try:
            self._stream = sd.RawInputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                                             callback=lambda data, frames, time, status: self._chunks.append(bytes(data)))
            self._stream.start()
        except Exception as e:
            raise VoiceError(f"I couldn't open the microphone ({e}).") from None

    def stop(self) -> bytes:
        """Stop and return the captured audio as raw PCM."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        return b"".join(self._chunks)


class Player:
    """Plays raw PCM; stop() cuts playback off immediately."""

    def __init__(self):
        self._stream = None
        self._lock = threading.Lock()
        self.stopped = threading.Event()

    def _open(self):
        if self._stream is None:
            sd = _sounddevice()
            try:
                self._stream = sd.RawOutputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16")
                self._stream.start()
            except Exception as e:
                raise VoiceError(f"I couldn't open the speakers ({e}).") from None
        return self._stream

    def play(self, pcm: bytes) -> None:
        with self._lock:
            if self.stopped.is_set():
                return
            stream = self._open()
        try:
            stream.write(pcm)
        except Exception:
            if not self.stopped.is_set():  # aborting mid-write is expected on interrupt
                raise

    def stop(self) -> None:
        """Interrupt: drop whatever is queued in the sound card right now."""
        self.stopped.set()
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.abort()
            stream.close()

    def resume(self) -> None:
        self.stopped.clear()

    def drain(self) -> None:
        """Let queued audio finish playing, then release the device."""
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()
