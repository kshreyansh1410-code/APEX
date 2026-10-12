"""Text-to-speech seam: give it text, get back streamed audio. ElevenLabs behind it."""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Iterator, Protocol

from .stt import VoiceError

SAMPLE_RATE = 16000  # all audio in Jarvis is 16 kHz, mono, 16-bit PCM


class Synthesizer(Protocol):
    def stream(self, text: str, should_stop: Callable[[], bool]) -> Iterator[bytes]:
        """Yield raw PCM chunks (16 kHz mono int16) as they arrive."""
        ...


class ElevenLabsSynthesizer:
    base_url = "https://api.elevenlabs.io"

    def __init__(self, api_key: str, voice_id: str, model: str = "eleven_flash_v2_5", timeout: float = 15):
        self.api_key, self.voice_id, self.model, self.timeout = api_key, voice_id, model, timeout

    def stream(self, text, should_stop):
        query = urllib.parse.urlencode({"output_format": f"pcm_{SAMPLE_RATE}"})
        request = urllib.request.Request(
            f"{self.base_url}/v1/text-to-speech/{urllib.parse.quote(self.voice_id)}/stream?{query}",
            data=json.dumps({"text": text, "model_id": self.model}).encode(),
            method="POST",
            headers={"xi-api-key": self.api_key, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                carry = b""
                while not should_stop():
                    chunk = response.read(4096)
                    if not chunk:
                        break
                    chunk = carry + chunk
                    # 16-bit samples: never hand the player half a sample.
                    cut = len(chunk) - (len(chunk) % 2)
                    carry = chunk[cut:]
                    yield chunk[:cut]
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise VoiceError("ElevenLabs rejected the request. Check ELEVENLABS_API_KEY, and that the voice is added to your account.") from None
            if e.code == 404:
                raise VoiceError(f"ElevenLabs doesn't know voice '{self.voice_id}'. Check elevenlabs_voice_id in config.toml.") from None
            raise VoiceError(f"ElevenLabs couldn't speak that (HTTP {e.code}).") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise VoiceError("I couldn't reach ElevenLabs to speak. Check your connection.") from None
