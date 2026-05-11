"""Centralised settings: .env + config.toml."""
from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ANTHROPIC_API_KEY: str = ""
    ELEVENLABS_API_KEY: str = ""
    ELEVENLABS_VOICE_ID_AI: str = "21m00Tcm4TlvDq8ikWAM"
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    PEXELS_API_KEY: str = ""
    PIXABAY_API_KEY: str = ""
    FAL_KEY: str = ""
    YOUTUBE_DATA_API_KEY: str = ""
    SUNO_API_KEY: str = ""

    PIPELINE_MODE: str = "auto"
    DEFAULT_MODEL_TIER: str = "sonnet"
    PROJECTS_DIR: str = "projects"


@lru_cache
def env() -> EnvSettings:
    return EnvSettings()


@lru_cache
def config() -> dict[str, Any]:
    path = REPO_ROOT / "config.toml"
    with path.open("rb") as f:
        return tomllib.load(f)


def has_key(name: str) -> bool:
    return bool(getattr(env(), name, ""))


def effective_mode() -> str:
    """Returns 'auto' only if minimal keys are available, else 'mock'."""
    if env().PIPELINE_MODE == "mock":
        return "mock"
    return "auto" if has_key("ANTHROPIC_API_KEY") else "mock"
