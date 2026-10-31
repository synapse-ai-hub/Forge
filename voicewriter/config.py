"""Runtime paths and LLM configuration for VoiceWriter."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "voicewriter"
PROFILES_SUBDIR = "profiles"
PREFS_FILENAME = "preferences.jsonl"


def home_dir() -> Path:
    """Return the VoiceWriter data directory, overridable via ``VOICEWRITER_HOME``."""
    env = os.environ.get("VOICEWRITER_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".config" / APP_NAME


def profiles_dir() -> Path:
    return home_dir() / PROFILES_SUBDIR


def prefs_path() -> Path:
    return home_dir() / PREFS_FILENAME


def ensure_dirs() -> None:
    profiles_dir().mkdir(parents=True, exist_ok=True)


@dataclass
class LlmConfig:
    provider: str = ""
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.7
    timeout: float = 120.0


def load_llm_config() -> LlmConfig:
    """Load LLM backend settings from ``VOICEWRITER_LLM_*`` environment variables."""
    provider = os.environ.get("VOICEWRITER_LLM_PROVIDER", "").strip().lower()
    base_url = os.environ.get("VOICEWRITER_LLM_BASE_URL", "").strip()
    api_key = os.environ.get("VOICEWRITER_LLM_API_KEY", "").strip()
    model = os.environ.get("VOICEWRITER_LLM_MODEL", "").strip()

    def _float(name: str, default: float) -> float:
        try:
            return float(os.environ.get(name, default))
        except ValueError:
            return default

    temperature = _float("VOICEWRITER_LLM_TEMPERATURE", 0.7)
    timeout = _float("VOICEWRITER_LLM_TIMEOUT", 120.0)

    if not provider:
        if base_url:
            provider = "openai"
        elif model:
            provider = "ollama"

    return LlmConfig(
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=temperature,
        timeout=timeout,
    )
