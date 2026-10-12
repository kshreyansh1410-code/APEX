"""Loads config.toml and the git-ignored .env file."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

AGENT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = AGENT_DIR / "config.toml"


@dataclass(frozen=True)
class AssistantConfig:
    name: str = "Jarvis"
    wake_phrase: str = "Hey Jarvis"
    purpose: str = "help me with my research and studies"
    personality: str = "Warm, plain-spoken, and brief."


@dataclass(frozen=True)
class ModelConfig:
    name: str = "claude-opus-5-5"
    effort: str = "medium"
    max_tokens: int = 16000
    timeout_seconds: float = 60
    fallbacks: bool = True


@dataclass(frozen=True)
class ToolsConfig:
    data_dir: str = "data"
    max_rounds: int = 8


@dataclass(frozen=True)
class DebugConfig:
    fail_tools: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class VoiceConfig:
    ptt_mode: str = "hold"
    ptt_key: str = "space"
    earcons: bool = True
    stt_model: str = "nova-3"
    language: str = "en"
    elevenlabs_voice_id: str = ""
    tts_model: str = "eleven_flash_v2_5"


@dataclass(frozen=True)
class Config:
    assistant: AssistantConfig
    model: ModelConfig
    tools: ToolsConfig
    debug: DebugConfig
    voice: VoiceConfig

    @property
    def data_dir(self) -> Path:
        return AGENT_DIR / self.tools.data_dir


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    """Read config.toml (missing keys fall back to defaults) and load .env into the environment."""
    load_dotenv(AGENT_DIR / ".env")
    data = tomllib.loads(path.read_text()) if path.exists() else {}
    return Config(
        assistant=AssistantConfig(**data.get("assistant", {})),
        model=ModelConfig(**data.get("model", {})),
        tools=ToolsConfig(**data.get("tools", {})),
        debug=DebugConfig(**data.get("debug", {})),
        voice=VoiceConfig(**data.get("voice", {})),
    )
