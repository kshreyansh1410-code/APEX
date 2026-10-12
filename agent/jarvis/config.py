"""Loads config.toml and the git-ignored .env file."""

import tomllib
from dataclasses import dataclass
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
class Config:
    assistant: AssistantConfig
    model: ModelConfig


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    """Read config.toml (missing keys fall back to defaults) and load .env into the environment."""
    load_dotenv(AGENT_DIR / ".env")
    data = tomllib.loads(path.read_text()) if path.exists() else {}
    return Config(
        assistant=AssistantConfig(**data.get("assistant", {})),
        model=ModelConfig(**data.get("model", {})),
    )
