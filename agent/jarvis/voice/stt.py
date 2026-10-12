"""Speech-to-text seam: give it audio, get back text. Deepgram behind it."""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Protocol


class VoiceError(Exception):
    """A voice-service failure with a message safe to show the user."""


class Transcriber(Protocol):
    def transcribe(self, wav: bytes) -> str: ...


class DeepgramTranscriber:
    base_url = "https://api.deepgram.com"

    def __init__(self, api_key: str, model: str = "nova-3", language: str = "en", timeout: float = 15):
        self.api_key, self.model, self.language, self.timeout = api_key, model, language, timeout

    def transcribe(self, wav: bytes) -> str:
        query = urllib.parse.urlencode({"model": self.model, "language": self.language, "smart_format": "true"})
        request = urllib.request.Request(
            f"{self.base_url}/v1/listen?{query}",
            data=wav,
            method="POST",
            headers={"Authorization": f"Token {self.api_key}", "Content-Type": "audio/wav"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.load(response)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise VoiceError("Deepgram rejected the key. Check DEEPGRAM_API_KEY in agent/.env.") from None
            raise VoiceError(f"Deepgram couldn't transcribe that (HTTP {e.code}).") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise VoiceError("I couldn't reach Deepgram to hear you. Check your connection.") from None
        try:
            return body["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
        except (KeyError, IndexError, TypeError):
            raise VoiceError("Deepgram sent back an answer I couldn't read.") from None
