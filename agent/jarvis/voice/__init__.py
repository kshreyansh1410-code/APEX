"""Voice in and out (Tier 3). A thin adapter around the same Agent the text CLI uses."""

import os
import queue
import time

from ..config import Config, VoiceConfig
from ..core import Agent
from .audio import Player, Recorder, _sounddevice, tone, to_wav
from .ptt import EnterToTalk, HoldToTalk
from .session import VoiceSession
from .speaker import Speaker
from .stt import DeepgramTranscriber, VoiceError
from .tts import SAMPLE_RATE, ElevenLabsSynthesizer


def _keys() -> tuple[str, str]:
    missing = [k for k in ("DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY") if not os.environ.get(k)]
    if missing:
        raise VoiceError(f"Voice needs {' and '.join(missing)} in agent/.env.")
    return os.environ["DEEPGRAM_API_KEY"], os.environ["ELEVENLABS_API_KEY"]


def _services(voice: VoiceConfig):
    if not voice.elevenlabs_voice_id:
        raise VoiceError("Set elevenlabs_voice_id under [voice] in config.toml.")
    deepgram_key, elevenlabs_key = _keys()
    return (DeepgramTranscriber(deepgram_key, voice.stt_model, voice.language),
            ElevenLabsSynthesizer(elevenlabs_key, voice.elevenlabs_voice_id, voice.tts_model))


def build_session(agent: Agent, config: Config) -> VoiceSession:
    voice = config.voice
    transcriber, synth = _services(voice)
    _sounddevice()  # fail now, with a clear message, if audio isn't available at all
    player = Player()
    speaker = Speaker(synth, player.play, player.stop, player.resume,
                      on_error=lambda msg: print(f"\n[{msg}]", flush=True))
    events: queue.Queue = queue.Queue()
    if voice.ptt_mode == "enter":
        ptt = EnterToTalk(events)
    elif voice.ptt_mode == "hold":
        ptt = HoldToTalk(events, voice.ptt_key)
    else:
        raise VoiceError(f"ptt_mode must be 'hold' or 'enter', not '{voice.ptt_mode}'.")
    return VoiceSession(agent, transcriber, speaker, Recorder(), ptt, events,
                        play_earcon=player.play if voice.earcons else None)


def voice_check(config: Config) -> bool:
    """Step-by-step check of every voice stage, so problems are easy to locate."""
    ok = True

    def step(label, fn):
        nonlocal ok
        print(f"• {label} … ", end="", flush=True)
        try:
            result = fn()
            print(f"ok{': ' + result if result else ''}")
        except VoiceError as e:
            ok = False
            print(f"FAILED — {e}")

    def devices():
        sd = _sounddevice()
        try:
            inp, out = sd.query_devices(kind="input"), sd.query_devices(kind="output")
        except Exception as e:
            raise VoiceError(f"no default microphone/speaker ({e})") from None
        return f"mic = {inp['name']}, speakers = {out['name']}"

    def beep():
        player = Player()
        player.play(tone(660, 250))
        player.drain()
        return "you should have heard a beep"

    def speak():
        _, synth = _services(config.voice)
        player = Player()
        started = time.monotonic()
        first = None
        for pcm in synth.stream(f"Hello, I'm {config.assistant.name}. Voice is working.", should_stop=lambda: False):
            first = first or time.monotonic() - started
            player.play(pcm)
        player.drain()
        return f"first audio after {first:.2f}s" if first else "no audio came back"

    def listen():
        transcriber, _ = _services(config.voice)
        recorder = Recorder()
        recorder.start()
        print("speak now for 4 seconds … ", end="", flush=True)
        time.sleep(4)
        pcm = recorder.stop()
        if len(pcm) < SAMPLE_RATE:
            raise VoiceError("the microphone recorded almost nothing")
        heard = transcriber.transcribe(to_wav(pcm))
        return f"heard {heard!r}" if heard else "heard nothing (check the mic and its permission)"

    step("audio devices", devices)
    step("speaker beep", beep)
    step("ElevenLabs voice", speak)
    step("Deepgram transcription", listen)
    print("All voice checks passed." if ok else "Some checks failed; fix those first.")
    return ok


__all__ = ["VoiceError", "build_session", "voice_check"]
