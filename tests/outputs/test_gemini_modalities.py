"""Unit tests for Gemini response-modality derivation.

Exercises ``resolve_gemini_response_modalities``,
``gemini_needs_speech_config`` and ``build_gemini_speech_config`` from
``backend.agent.llm.outputs`` with catalog-shaped modality lists.

No network, no provider keys, no mocks of the code under test.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from backend.agent.llm.outputs import (
    build_gemini_speech_config,
    gemini_needs_speech_config,
    resolve_gemini_response_modalities,
)


def test_tts_only_audio_returns_audio() -> None:
    """TTS-only models (["audio"]) must request ["AUDIO"] exclusively."""
    assert resolve_gemini_response_modalities(["audio"]) == ["AUDIO"]


def test_tts_never_requests_text() -> None:
    """Requesting TEXT on a TTS-only model fails with 400 (live verified)."""
    resolved = resolve_gemini_response_modalities(["audio"])
    assert resolved is not None
    assert "TEXT" not in [m.upper() for m in resolved]


def test_image_model_returns_text_image() -> None:
    """Image models (["text", "image"]) get ["TEXT", "IMAGE"]."""
    assert resolve_gemini_response_modalities(["text", "image"]) == ["TEXT", "IMAGE"]


def test_audio_text_model_returns_text_audio() -> None:
    """Mixed audio+text models get ["TEXT", "AUDIO"]."""
    assert resolve_gemini_response_modalities(["text", "audio"]) == ["TEXT", "AUDIO"]


def test_text_only_returns_none_default() -> None:
    """Text-only models use the SDK default (None = TEXT)."""
    assert resolve_gemini_response_modalities(["text"]) is None
    assert resolve_gemini_response_modalities([]) is None
    assert resolve_gemini_response_modalities(None) is None


def test_json_format_suppresses_modalities() -> None:
    """JSON mode must not set response_modalities (mime type rules)."""
    assert resolve_gemini_response_modalities(["text", "image"], "json") is None
    assert resolve_gemini_response_modalities(["audio"], "json") is None


def test_case_insensitive_modalities() -> None:
    """Catalog values may vary in case; matching is case-insensitive."""
    assert resolve_gemini_response_modalities(["Audio"]) == ["AUDIO"]
    assert resolve_gemini_response_modalities(["TEXT", "IMAGE"]) == ["TEXT", "IMAGE"]


def test_needs_speech_config_only_for_audio() -> None:
    """Only audio-output models need a speech_config with a voice."""
    assert gemini_needs_speech_config(["audio"]) is True
    assert gemini_needs_speech_config(["text", "audio"]) is True
    assert gemini_needs_speech_config(["text", "image"]) is False
    assert gemini_needs_speech_config(["text"]) is False
    assert gemini_needs_speech_config(None) is False


def test_build_speech_config_has_voice() -> None:
    """SpeechConfig carries a prebuilt voice (default + custom)."""
    cfg = build_gemini_speech_config()
    voice = cfg.voice_config.prebuilt_voice_config.voice_name
    assert isinstance(voice, str) and len(voice) > 0
    cfg2 = build_gemini_speech_config("Aoede")
    assert cfg2.voice_config.prebuilt_voice_config.voice_name == "Aoede"
