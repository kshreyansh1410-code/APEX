"""Tier 3 checks: voice adapters around the same agent core. No audio hardware or network."""

import io
import json
import queue
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from jarvis.config import AssistantConfig
from jarvis.core import Agent
from jarvis.provider import Reply
from jarvis.tools import build_registry
from jarvis.voice.audio import to_wav, tone
from jarvis.voice.ptt import PRESS, RELEASE, EnterToTalk
from jarvis.voice.session import VoiceSession
from jarvis.voice.speaker import SentenceSplitter, Speaker, clean_for_speech
from jarvis.voice.stt import DeepgramTranscriber, VoiceError
from jarvis.voice.tts import SAMPLE_RATE, ElevenLabsSynthesizer

ONE_SECOND = b"\x01\x00" * SAMPLE_RATE


def wait_for(condition, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


# --- sentence splitting -----------------------------------------------------

def test_sentences_are_released_as_soon_as_they_finish():
    s = SentenceSplitter()
    assert s.feed("Hello there") == []
    assert s.feed(".") == []  # could still be "3.5", so wait for the space
    assert s.feed(" How are") == ["Hello there."]
    assert s.feed(" you? I'm fine") == ["How are you?"]
    assert s.flush() == ["I'm fine"]
    assert s.flush() == []


def test_markdown_is_not_read_aloud():
    assert clean_for_speech("**Bold** and `code` and [a link](https://x.y)") == "Bold and code and a link"


def test_decimals_are_not_split():
    assert SentenceSplitter().feed("It costs 3.50 dollars. Ok") == ["It costs 3.50 dollars."]


# --- the speaker ------------------------------------------------------------

class FakeSynth:
    def __init__(self, delay=0.0):
        self.spoken: list[str] = []
        self.delay = delay

    def stream(self, text, should_stop):
        self.spoken.append(text)
        for _ in range(5):
            if should_stop():
                return
            time.sleep(self.delay)
            yield text.encode()[:2].ljust(2, b"_")


def make_speaker(delay=0.0):
    synth, played = FakeSynth(delay), []
    speaker = Speaker(synth, played.append, stop_playback=lambda: None, resume_playback=lambda: None,
                      on_error=lambda m: played.append(("error", m)))
    return speaker, synth, played


def test_speaker_says_sentences_in_order():
    speaker, synth, played = make_speaker()
    speaker.feed("One. Two")
    speaker.feed(" three. Four")
    speaker.finish()
    assert speaker.wait_until_done(3)
    assert synth.spoken == ["One.", "Two three.", "Four"]
    assert len(played) == 15


def test_interrupt_stops_speech_and_drops_the_queue():
    speaker, synth, played = make_speaker(delay=0.05)
    for i in range(5):
        speaker.say(f"Sentence {i}.")
    assert wait_for(lambda: len(played) >= 1)
    speaker.interrupt()
    assert speaker.wait_until_done(3)
    time.sleep(0.15)
    assert len(synth.spoken) == 1 and len(played) < 5  # cut off mid-sentence, rest never said
    speaker.reset()
    speaker.say("Fresh.")
    assert speaker.wait_until_done(3) and synth.spoken[-1] == "Fresh."


def test_speech_failure_is_reported_not_fatal():
    class Broken:
        def stream(self, text, should_stop):
            raise VoiceError("ElevenLabs rejected the request.")
            yield  # pragma: no cover

    errors = []
    speaker = Speaker(Broken(), lambda b: None, lambda: None, lambda: None, on_error=errors.append)
    speaker.say("Hi.")
    speaker.say("Again.")
    assert speaker.wait_until_done(3) and len(errors) == 2


# --- the voice session ------------------------------------------------------

class FakeRecorder:
    def __init__(self, pcm=ONE_SECOND):
        self.pcm, self.started = pcm, 0

    def start(self):
        self.started += 1

    def stop(self):
        return self.pcm


class FakeTranscriber:
    def __init__(self, *heard):
        self.heard = list(heard)
        self.wavs = []

    def transcribe(self, wav):
        self.wavs.append(wav)
        result = self.heard.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class SlowProvider:
    """Streams its reply a few words at a time; can be slowed down to test interrupts."""

    def __init__(self, reply="Sure. Here you go.", delay=0.0):
        self.reply, self.delay = reply, delay
        self.requests = []

    def respond(self, system, messages, tools=None, on_text=None):
        self.requests.append(list(messages))
        for word in self.reply.split(" "):
            time.sleep(self.delay)
            if on_text:
                on_text(word + " ")
        return Reply(self.reply, [{"type": "text", "text": self.reply}], "end_turn")


class FakePTT:
    hint = "fake"

    def __init__(self, fail=False):
        self.fail = fail

    def start(self):
        if self.fail:
            raise VoiceError("no keyboard")

    def stop(self):
        pass


def make_session(transcriber, provider, recorder=None, tmp_path=None, speaker_delay=0.0):
    agent = Agent(provider, AssistantConfig(), build_registry(tmp_path) if tmp_path else None)
    speaker, synth, played = make_speaker(speaker_delay)
    lines: list[str] = []
    session = VoiceSession(agent, transcriber, speaker, recorder or FakeRecorder(), FakePTT(), queue.Queue(),
                           write=lines.append)
    return session, agent, synth, lines


def wait_for_turn(session):
    assert session._worker is not None
    session._worker.join(3)
    assert not session._worker.is_alive()


def test_spoken_turn_uses_the_same_agent_core(tmp_path):
    provider = SlowProvider("Sure. Here you go.")
    session, agent, synth, lines = make_session(FakeTranscriber("what's on my list?"), provider, tmp_path=tmp_path)

    session.on_press()
    session.on_release()
    wait_for_turn(session)
    assert session.speaker.wait_until_done(3)

    output = "".join(lines)
    assert "you (heard) › what's on my list?" in output  # the transcript is visible
    assert provider.requests[0][-1] == {"role": "user", "content": "what's on my list?"}
    assert synth.spoken == ["Sure.", "Here you go."]  # spoken sentence by sentence
    assert len(agent.history) == 2


def test_audio_sent_to_transcriber_is_a_wav():
    transcriber = FakeTranscriber("hi")
    session, *_ = make_session(transcriber, SlowProvider())
    session.on_press()
    session.on_release()
    wait_for_turn(session)
    with wave.open(io.BytesIO(transcriber.wavs[0])) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (SAMPLE_RATE, 1, 2)


def test_pressing_again_interrupts_the_reply(tmp_path):
    provider = SlowProvider("One. Two. Three. Four. Five. Six.", delay=0.1)
    session, agent, synth, lines = make_session(FakeTranscriber("tell me a story", "stop"), provider, tmp_path=tmp_path)

    session.on_press()
    session.on_release()
    assert wait_for(lambda: synth.spoken)  # it has started talking
    first_turn = session._worker
    session.on_press()  # user cuts in
    first_turn.join(3)

    assert "(interrupted)" in "".join(lines)
    assert agent.history == []  # the cut-off reply was not kept
    assert len(synth.spoken) < 6

    provider.delay = 0
    session.on_release()
    wait_for_turn(session)
    assert [m["content"] for m in agent.history if m["role"] == "user"] == ["stop"]


def test_too_short_press_is_ignored():
    transcriber = FakeTranscriber()
    session, _, _, lines = make_session(transcriber, SlowProvider(), recorder=FakeRecorder(b"\x00\x00" * 100))
    session.on_press()
    session.on_release()
    assert session._worker is None and "too short" in "".join(lines)


def test_transcription_failure_is_said_and_shown():
    session, agent, synth, lines = make_session(FakeTranscriber(VoiceError("I couldn't reach Deepgram.")), SlowProvider())
    session.on_press()
    session.on_release()
    wait_for_turn(session)
    assert session.speaker.wait_until_done(3)
    assert "[I couldn't reach Deepgram.]" in "".join(lines)
    assert synth.spoken == ["I couldn't reach Deepgram."] and agent.history == []


def test_silence_is_handled():
    session, _, synth, lines = make_session(FakeTranscriber(""), SlowProvider())
    session.on_press()
    session.on_release()
    wait_for_turn(session)
    assert "didn't catch that" in "".join(lines)


def test_hold_to_talk_falls_back_to_enter(monkeypatch):
    session, *_ = make_session(FakeTranscriber(), SlowProvider())
    session.ptt = FakePTT(fail=True)
    monkeypatch.setattr(EnterToTalk, "start", lambda self: None)
    monkeypatch.setattr(session.events, "get", lambda timeout: (_ for _ in ()).throw(KeyboardInterrupt))
    session.run()
    assert isinstance(session.ptt, EnterToTalk)


def test_enter_to_talk_alternates_press_and_release(monkeypatch):
    events = queue.Queue()
    monkeypatch.setattr("sys.stdin", io.StringIO("\n\n\n"))
    EnterToTalk(events)._run()
    assert [events.get_nowait() for _ in range(3)] == [PRESS, RELEASE, PRESS]


# --- audio helpers ----------------------------------------------------------

def test_wav_and_tone():
    pcm = tone(880, 100)
    assert len(pcm) == SAMPLE_RATE // 10 * 2
    with wave.open(io.BytesIO(to_wav(pcm))) as w:
        assert w.getnframes() == SAMPLE_RATE // 10


# --- Deepgram and ElevenLabs over HTTP, against a local fake server ----------

class FakeService(BaseHTTPRequestHandler):
    requests: list = []
    status = 200
    body = b""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        FakeService.requests.append((self.path, dict(self.headers), self.rfile.read(length)))
        self.send_response(FakeService.status)
        self.end_headers()
        self.wfile.write(FakeService.body)

    def log_message(self, *args):
        pass


@pytest.fixture
def fake_service():
    FakeService.requests, FakeService.status, FakeService.body = [], 200, b""
    server = HTTPServer(("127.0.0.1", 0), FakeService)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_deepgram_request_and_parse(fake_service):
    FakeService.body = json.dumps(
        {"results": {"channels": [{"alternatives": [{"transcript": " What's on my list? "}]}]}}).encode()
    stt = DeepgramTranscriber("dg-key", model="nova-3", language="en")
    stt.base_url = fake_service

    assert stt.transcribe(b"RIFFwav") == "What's on my list?"
    path, headers, body = FakeService.requests[0]
    assert path.startswith("/v1/listen?") and "model=nova-3" in path and "smart_format=true" in path
    assert headers["Authorization"] == "Token dg-key" and headers["Content-Type"] == "audio/wav"
    assert body == b"RIFFwav"


def test_deepgram_bad_key(fake_service):
    FakeService.status = 401
    stt = DeepgramTranscriber("bad")
    stt.base_url = fake_service
    with pytest.raises(VoiceError, match="DEEPGRAM_API_KEY"):
        stt.transcribe(b"x")


def test_elevenlabs_request_and_whole_samples(fake_service):
    FakeService.body = b"\x01\x02" * 5000 + b"\x03"  # odd length: last half-sample must not be played
    tts = ElevenLabsSynthesizer("el-key", "wDsJlOXPqcvIUKdLXjDs", model="eleven_flash_v2_5")
    tts.base_url = fake_service

    chunks = list(tts.stream("Hello there.", should_stop=lambda: False))
    assert all(len(c) % 2 == 0 for c in chunks) and sum(map(len, chunks)) == 10000
    path, headers, body = FakeService.requests[0]
    assert path == "/v1/text-to-speech/wDsJlOXPqcvIUKdLXjDs/stream?output_format=pcm_16000"
    assert headers["Xi-Api-Key"] == "el-key"
    assert json.loads(body) == {"text": "Hello there.", "model_id": "eleven_flash_v2_5"}


def test_elevenlabs_unknown_voice(fake_service):
    FakeService.status = 404
    tts = ElevenLabsSynthesizer("k", "nope")
    tts.base_url = fake_service
    with pytest.raises(VoiceError, match="elevenlabs_voice_id"):
        list(tts.stream("hi", should_stop=lambda: False))


def test_services_unreachable():
    stt = DeepgramTranscriber("k", timeout=2)
    stt.base_url = "http://127.0.0.1:9"
    with pytest.raises(VoiceError, match="couldn't reach Deepgram"):
        stt.transcribe(b"x")
