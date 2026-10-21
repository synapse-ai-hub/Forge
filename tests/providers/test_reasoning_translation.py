"""Unit tests for gateway x model reasoning translation.

Exercises the real ``translate_reasoning``, ``get_reasoning_options``
and ``get_reasoning_streaming_config`` from
``backend.agent.utils.model_catalog`` against an isolated SQLite
catalog seeded with representative models.dev rows (no network, no
mocks of the code under test).
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from backend.agent.ddl_setup import setup_database
from backend.agent.utils import model_catalog
from pathlib import Path
from typing import Any

_SEED_ROWS = [
    # (provider, model_id, reasoning, reasoning_options, npm)
    # Rows use representative reasoning_options shapes from models.dev.
    ("groq", "openai/gpt-oss-120b", 1,
     [{"type": "effort", "values": ["low", "medium", "high"]}],
     "@ai-sdk/groq"),
    ("groq", "qwen/qwen3.8-27b", 1,
     [{"type": "effort", "values": ["none", "default", "low", "medium", "high"]}],
     "@ai-sdk/groq"),
    ("groq", "llama-3.3-70b-versatile", 0, [], "@ai-sdk/groq"),
    ("openrouter", "openai/gpt-oss-120b", 1,
     [{"type": "effort", "values": ["low", "medium", "high"]}],
     "@openrouter/ai-sdk-provider"),
    ("openrouter", "qwen/qwen3.7-flash", 1,
     [{"type": "toggle"}, {"type": "budget_tokens"}],
     "@openrouter/ai-sdk-provider"),
    ("openrouter", "google/gemini-2.5-pro", 1,
     [{"type": "budget_tokens", "min": 128, "max": 32768}],
     "@openrouter/ai-sdk-provider"),
    ("openrouter", "google/gemini-3.1-pro-preview", 1,
     [{"type": "effort", "values": ["low", "medium", "high"]}],
     "@openrouter/ai-sdk-provider"),
    ("openrouter", "qwen/qwen3-235b-a22b", 1,
     [{"type": "toggle"}],
     "@openrouter/ai-sdk-provider"),
    ("openrouter", "deepseek/deepseek-r1", 1,
     [],
     "@openrouter/ai-sdk-provider"),
    ("google", "gemini-2.5-flash", 1,
     [{"type": "toggle"}, {"type": "budget_tokens", "min": 0, "max": 24576}],
     "@ai-sdk/google"),
    ("google", "gemini-3.1-pro-preview", 1,
     [{"type": "effort", "values": ["low", "medium", "high"]}],
     "@ai-sdk/google"),
    ("deepseek", "deepseek-flash", 1,
     [{"type": "toggle"}, {"type": "effort", "values": ["low", "high", "max"]}],
     "@ai-sdk/deepseek"),
    ("openai", "gpt-6-astra", 1,
     [{"type": "effort", "values": ["low", "medium", "high", "xhigh", "max"]}],
     "@ai-sdk/openai"),
    ("alibaba", "qwen3.8-max", 1,
     [{"type": "toggle"},
      {"type": "effort", "values": ["low", "medium", "xhigh"]},
      {"type": "budget_tokens", "min": 0, "max": 262144}],
     "@ai-sdk/openai-compatible"),
]


@pytest.fixture()
def catalog_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Create an isolated catalog DB and patch the module connection.

    Args:
        tmp_path: Temporary directory of the test.
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        The path of the isolated catalog database.
    """
    db_path = str(tmp_path / "test_catalog.db")
    conn = sqlite3.connect(db_path)
    try:
        setup_database(conn)
        conn.executemany(
            """INSERT INTO model_catalog
               (provider, model_id, reasoning, reasoning_options, npm, updated_at)
               VALUES (?, ?, ?, ?, ?, '2026-01-01T00:00:00')""",
            [
                (p, m, r, json.dumps(o), n)
                for p, m, r, o, n in _SEED_ROWS
            ],
        )
        conn.commit()
    finally:
        conn.close()

    def _fake_connect() -> sqlite3.Connection:
        """Open the isolated catalog database.

        Returns:
            A connection with ``sqlite3.Row`` rows.
        """
        fake = sqlite3.connect(db_path)
        fake.row_factory = sqlite3.Row
        return fake

    monkeypatch.setattr(model_catalog, "_connect", _fake_connect)
    return db_path


def tr(provider: str, value: Any, model: str = "", budget: int | None = None) -> Any:
    """Call the real translator with explicit kwargs.

    Args:
        provider: Provider id.
        value: Reasoning value the user chose.
        model: Model id.
        budget: Token budget for reasoning, if any.

    Returns:
        What ``model_catalog.translate_reasoning`` returns.
    """
    return model_catalog.translate_reasoning(
        provider=provider,
        reasoning_value=value,
        model_id=model,
        budget_tokens=budget,
    )


# --- Groq (plain OpenAI-compatible gateway) ---

def test_groq_effort_uses_string_shape(catalog_db: str) -> None:
    """Groq effort uses string shape.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("groq", "high", "openai/gpt-oss-120b") == {"reasoning_effort": "high"}


def test_groq_off_variants(catalog_db: str) -> None:
    # gpt-oss only accepts low/medium/high: "off" sends nothing.
    """Groq off variants.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    for value in ("off", "none", False, "false"):
        assert tr("groq", value, "openai/gpt-oss-120b") == {}
    # qwen on groq accepts "none": "off" maps to it.
    for value in ("off", "none", False, "false"):
        assert tr("groq", value, "qwen/qwen3.8-27b") == {
            "reasoning_effort": "none"
        }


def test_groq_default_variants_send_nothing(catalog_db: str) -> None:
    """Groq default variants send nothing.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    for value in (None, "default", "", True, "on", "true"):
        assert tr("groq", value, "openai/gpt-oss-120b") == {}


def test_groq_unlisted_value_sends_nothing(catalog_db: str) -> None:
    """Groq unlisted value sends nothing.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("groq", "auto", "openai/gpt-oss-120b") == {}
    assert tr("groq", "xhigh", "openai/gpt-oss-120b") == {}
    assert tr("groq", 1, "openai/gpt-oss-120b") == {}


def test_groq_non_reasoning_model_sends_nothing(catalog_db: str) -> None:
    """Groq non reasoning model sends nothing.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("groq", "high", "llama-3.3-70b-versatile") == {}


def test_groq_unknown_model_uses_gateway_fallback(catalog_db: str) -> None:
    """Groq unknown model uses gateway fallback.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("groq", "low", "some-future-model") == {"reasoning_effort": "low"}
    assert tr("groq", "off", "some-future-model") == {"reasoning_effort": "none"}


def test_translate_malformed_options_row_uses_gateway_default(catalog_db: str) -> None:
    """Translate malformed options row uses gateway default.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    conn = sqlite3.connect(catalog_db)
    try:
        conn.execute(
            "INSERT INTO model_catalog (provider, model_id, reasoning,"
            " reasoning_options, updated_at)"
            " VALUES ('groq', 'bad-model', 1, '{broken', '2026-01-01T00:00:00')"
        )
        conn.commit()
    finally:
        conn.close()
    assert tr("groq", "high", "bad-model") == {"reasoning_effort": "high"}


def test_translate_null_options_row_uses_gateway_default(catalog_db: str) -> None:
    """Translate null options row uses gateway default.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    conn = sqlite3.connect(catalog_db)
    try:
        conn.execute(
            "INSERT INTO model_catalog (provider, model_id, reasoning,"
            " reasoning_options, updated_at)"
            " VALUES ('groq', 'null-model', 1, NULL, '2026-01-01T00:00:00')"
        )
        conn.commit()
    finally:
        conn.close()
    assert tr("groq", "high", "null-model") == {"reasoning_effort": "high"}


# --- OpenRouter gateway (reasoning object) ---

def test_openrouter_effort_uses_object_shape(catalog_db: str) -> None:
    """Openrouter effort uses object shape.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("openrouter", "medium", "openai/gpt-oss-120b") == {
        "reasoning": {"effort": "medium"}
    }


def test_openrouter_off_excludes_reasoning(catalog_db: str) -> None:
    """Openrouter off excludes reasoning.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("openrouter", "off", "openai/gpt-oss-120b") == {
        "reasoning": {"exclude": True}
    }


def test_openrouter_budget_model(catalog_db: str) -> None:
    # Realistic call: default reasoning (True) + explicit budget.
    """Openrouter budget model.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("openrouter", True, "qwen/qwen3.7-flash", budget=5000) == {
        "reasoning": {"max_tokens": 5000}
    }
    assert tr("openrouter", "default", "qwen/qwen3.7-flash", budget=5000) == {
        "reasoning": {"max_tokens": 5000}
    }


def test_openrouter_off_wins_over_budget(catalog_db: str) -> None:
    """Openrouter off wins over budget.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("openrouter", "off", "qwen/qwen3.7-flash", budget=5000) == {
        "reasoning": {"exclude": True}
    }


def test_openrouter_budget_range_reaches_options(catalog_db: str) -> None:
    """Openrouter budget range reaches options.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    opts = model_catalog.get_reasoning_options("openrouter", "google/gemini-2.5-pro")
    assert opts["reasoning_type"] == "budget_tokens"
    assert opts["budget_min"] == 128
    assert opts["budget_max"] == 32768
    assert tr("openrouter", True, "google/gemini-2.5-pro", budget=2000) == {
        "reasoning": {"max_tokens": 2000}
    }


def test_openrouter_google_model_does_not_use_thinking_config(catalog_db: str) -> None:
    """Openrouter google model does not use thinking config.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    result = tr(
        "openrouter", "high", "google/gemini-3.1-pro-preview"
    )
    assert result == {"reasoning": {"effort": "high"}}
    assert "thinking_config" not in result


def test_openrouter_toggle_only_model(catalog_db: str) -> None:
    """Openrouter toggle only model.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("openrouter", "default", "qwen/qwen3-235b-a22b") == {}
    assert tr("openrouter", "off", "qwen/qwen3-235b-a22b") == {
        "reasoning": {"exclude": True}
    }


def test_openrouter_no_control_model_sends_nothing(catalog_db: str) -> None:
    # deepseek-r1 via OpenRouter declares no caller control ([]).
    """Openrouter no control model sends nothing.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("openrouter", "high", "deepseek/deepseek-r1") == {}
    assert tr("openrouter", True, "deepseek/deepseek-r1", budget=5000) == {}
    assert tr("openrouter", "off", "deepseek/deepseek-r1") == {
        "reasoning": {"exclude": True}
    }


def test_openrouter_unknown_model_uses_gateway_shape(catalog_db: str) -> None:
    """Openrouter unknown model uses gateway shape.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("openrouter", "high", "some-future-model") == {
        "reasoning": {"effort": "high"}
    }


def test_openrouter_effort_on_budget_only_model(catalog_db: str) -> None:
    # OpenRouter converts effort automatically for budget-based models.
    """Openrouter effort on budget only model.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("openrouter", "high", "google/gemini-2.5-pro") == {
        "reasoning": {"effort": "high"}
    }


def test_openrouter_budget_on_effort_only_model(catalog_db: str) -> None:
    # max_tokens is ignored when the model does not support it.
    """Openrouter budget on effort only model.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("openrouter", True, "openai/gpt-oss-120b", budget=5000) == {
        "reasoning": {"max_tokens": 5000}
    }


def test_openrouter_budget_on_toggle_only_model(catalog_db: str) -> None:
    """Openrouter budget on toggle only model.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("openrouter", True, "qwen/qwen3-235b-a22b", budget=5000) == {}


# --- Google direct gateway ---

def test_google_effort_uses_thinking_level(catalog_db: str) -> None:
    """Google effort uses thinking level.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("google", "high", "gemini-3.1-pro-preview") == {
        "thinking_config": {"thinking_level": "high"}
    }


def test_google_effort_outside_values_sends_nothing(catalog_db: str) -> None:
    """Google effort outside values sends nothing.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("google", "xhigh", "gemini-3.1-pro-preview") == {}


def test_google_budget_uses_thinking_budget(catalog_db: str) -> None:
    """Google budget uses thinking budget.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("google", True, "gemini-2.5-flash", budget=1000) == {
        "thinking_config": {"thinking_budget": 1000}
    }


def test_google_budget_on_level_model_uses_thinking_budget(catalog_db: str) -> None:
    """Google budget on level model uses thinking budget.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("google", True, "gemini-3.1-pro-preview", budget=1000) == {
        "thinking_config": {"thinking_budget": 1000}
    }


def test_google_effort_on_budget_model_sends_nothing(catalog_db: str) -> None:
    # Gemini 2.5 has no thinking_level control.
    """Google effort on budget model sends nothing.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("google", "high", "gemini-2.5-flash") == {}


def test_google_off_disables_thinking(catalog_db: str) -> None:
    """Google off disables thinking.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("google", "off", "gemini-2.5-flash") == {
        "thinking_config": {"thinking_budget": 0}
    }


def test_google_off_on_level_model_sends_nothing(catalog_db: str) -> None:
    """Google off on level model sends nothing.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("google", "off", "gemini-3.1-pro-preview") == {}


def test_google_default_sends_nothing(catalog_db: str) -> None:
    """Google default sends nothing.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("google", "default", "gemini-3.1-pro-preview") == {}
    assert tr("google", None, "gemini-3.1-pro-preview") == {}


def test_google_unknown_model_uses_gateway_shape(catalog_db: str) -> None:
    """Google unknown model uses gateway shape.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("google", "high", "some-future-model") == {
        "thinking_config": {"thinking_level": "high"}
    }
    assert tr("google", True, "some-future-model", budget=1000) == {
        "thinking_config": {"thinking_budget": 1000}
    }
    assert tr("google", "off", "some-future-model") == {
        "thinking_config": {"thinking_budget": 0}
    }


def test_google_invalid_budget_falls_back_to_effort(catalog_db: str) -> None:
    """Google invalid budget falls back to effort.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("google", "high", "gemini-2.5-flash", budget=0) == {}
    assert tr("google", "high", "gemini-2.5-flash", budget="junk") == {}
    assert tr("google", "high", "gemini-3.1-pro-preview", budget=-5) == {
        "thinking_config": {"thinking_level": "high"}
    }


# --- Other plain OpenAI-compatible gateways ---

def test_deepseek_effort_uses_string_shape(catalog_db: str) -> None:
    """Deepseek effort uses string shape.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("deepseek", "high", "deepseek-flash") == {"reasoning_effort": "high"}


def test_deepseek_off_sends_nothing(catalog_db: str) -> None:
    # deepseek-flash declares no "none" value.
    """Deepseek off sends nothing.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("deepseek", "off", "deepseek-flash") == {}


def test_alibaba_effort_in_values_uses_string_shape(catalog_db: str) -> None:
    """Alibaba effort in values uses string shape.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("alibaba", "medium", "qwen3.8-max") == {"reasoning_effort": "medium"}


def test_alibaba_effort_outside_values_sends_nothing(catalog_db: str) -> None:
    """Alibaba effort outside values sends nothing.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("alibaba", "high", "qwen3.8-max") == {}
    assert tr("alibaba", "off", "qwen3.8-max") == {}


def test_openai_extended_levels_pass_through(catalog_db: str) -> None:
    """Openai extended levels pass through.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("openai", "xhigh", "gpt-6-astra") == {"reasoning_effort": "xhigh"}


def test_plain_gateway_budget_has_no_generic_param(catalog_db: str) -> None:
    """Plain gateway budget has no generic param.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("alibaba", "default", "qwen3.8-max", budget=4000) == {}


def test_plain_gateway_effort_wins_over_budget(catalog_db: str) -> None:
    # Plain gateways have no budget param: an explicit effort level is
    # preserved instead of being dropped.
    """Plain gateway effort wins over budget.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("groq", "high", "openai/gpt-oss-120b", budget=5000) == {
        "reasoning_effort": "high"
    }


def test_provider_without_synced_models_uses_registry_fallback(catalog_db: str) -> None:
    """Provider without synced models uses registry fallback.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("togetherai", "medium", "some-model") == {"reasoning_effort": "medium"}


def test_unknown_provider_sends_nothing(catalog_db: str) -> None:
    """Unknown provider sends nothing.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("no-such-provider", "high", "any-model") == {}


def test_empty_provider_sends_nothing(catalog_db: str) -> None:
    """Empty provider sends nothing.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("", "high", "any-model") == {}


def test_invalid_budget_falls_back_to_effort(catalog_db: str) -> None:
    """Invalid budget falls back to effort.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("openrouter", "medium", "openai/gpt-oss-120b", budget=0) == {
        "reasoning": {"effort": "medium"}
    }
    assert tr("openrouter", "medium", "openai/gpt-oss-120b", budget=-5) == {
        "reasoning": {"effort": "medium"}
    }
    assert tr("groq", "low", "openai/gpt-oss-120b", budget="junk") == {
        "reasoning_effort": "low"
    }


# --- Provider normalization, model_id=None, LOCAL, int values ---

def test_provider_name_normalization(catalog_db: str) -> None:
    """Provider name normalization.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("groq", "high", "openai/gpt-oss-120b") == {"reasoning_effort": "high"}
    assert tr("  openrouter  ", "medium", "openai/gpt-oss-120b") == {
        "reasoning": {"effort": "medium"}
    }
    assert tr("google", "high", "gemini-3.1-pro-preview") == {
        "thinking_config": {"thinking_level": "high"}
    }


def test_model_id_none_skips_lookup(catalog_db: str) -> None:
    """Model id none skips lookup.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("groq", "high", None) == {"reasoning_effort": "high"}


def test_string_budget_coerced(catalog_db: str) -> None:
    """String budget coerced.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("openrouter", True, "qwen/qwen3.7-flash", budget="5000") == {
        "reasoning": {"max_tokens": 5000}
    }


def test_local_provider_sends_nothing(catalog_db: str) -> None:
    # Local reasoning is handled by model_resolver, never via API kwargs.
    """Local provider sends nothing.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert tr("LOCAL", "high", "llama3") == {}
    assert tr("ollama", "high", "llama3") == {}


# --- get_reasoning_options coverage ---

def test_options_non_reasoning_model(catalog_db: str) -> None:
    """Options non reasoning model.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    opts = model_catalog.get_reasoning_options("groq", "llama-3.3-70b-versatile")
    assert opts["reasoning_supported"] is False
    assert opts["reasoning_type"] is None


def test_options_effort_model(catalog_db: str) -> None:
    """Options effort model.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    opts = model_catalog.get_reasoning_options("groq", "openai/gpt-oss-120b")
    assert opts["reasoning_supported"] is True
    assert opts["reasoning_type"] == "effort_levels"
    assert [o["value"] for o in opts["reasoning_options"]] == [
        "default", "low", "medium", "high",
    ]


def test_options_toggle_model(catalog_db: str) -> None:
    """Options toggle model.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    opts = model_catalog.get_reasoning_options("openrouter", "qwen/qwen3-235b-a22b")
    assert opts["reasoning_supported"] is True
    assert opts["reasoning_type"] == "boolean"


def test_options_combined_model_reports_budget_range(catalog_db: str) -> None:
    """Options combined model reports budget range.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    opts = model_catalog.get_reasoning_options("alibaba", "qwen3.8-max")
    assert opts["reasoning_supported"] is True
    assert opts["reasoning_type"] == "budget_tokens"
    assert opts["budget_min"] == 0
    assert opts["budget_max"] == 262144
    assert [o["value"] for o in opts["reasoning_options"]] == ["default"]


def test_options_google_budget_range(catalog_db: str) -> None:
    """Options google budget range.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    opts = model_catalog.get_reasoning_options("google", "gemini-2.5-flash")
    assert opts["reasoning_supported"] is True
    assert opts["reasoning_type"] == "budget_tokens"
    assert opts["budget_min"] == 0
    assert opts["budget_max"] == 24576


def test_options_unknown_model(catalog_db: str) -> None:
    """Options unknown model.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    opts = model_catalog.get_reasoning_options("groq", "no-such-model")
    assert opts["reasoning_supported"] is None
    assert opts["reasoning_type"] is None
    assert opts["reasoning_options"] == []


def test_options_malformed_json_row(catalog_db: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Options malformed json row.

    Args:
        catalog_db: Path of the isolated catalog database.
        tmp_path: Temporary directory of the test.
        monkeypatch: Pytest monkeypatch fixture.
    """
    bad_path = str(tmp_path / "bad.db")
    conn = sqlite3.connect(bad_path)
    try:
        setup_database(conn)
        conn.execute(
            """INSERT INTO model_catalog
               (provider, model_id, reasoning, reasoning_options, npm, updated_at)
               VALUES ('groq', 'bad-model', 1, '{broken', '@ai-sdk/groq',
                       '2026-01-01T00:00:00')"""
        )
        conn.commit()
    finally:
        conn.close()

    def _bad_connect() -> sqlite3.Connection:
        """Open a database that is not a valid catalog.

        Returns:
            A connection with ``sqlite3.Row`` rows.
        """
        fake = sqlite3.connect(bad_path)
        fake.row_factory = sqlite3.Row
        return fake

    monkeypatch.setattr(model_catalog, "_connect", _bad_connect)
    opts = model_catalog.get_reasoning_options("groq", "bad-model")
    assert opts["reasoning_supported"] is True
    assert opts["reasoning_type"] is None
    assert [o["value"] for o in opts["reasoning_options"]] == ["default"]


# --- Streaming config ---

def test_streaming_config_is_empty(catalog_db: str) -> None:
    """Streaming config is empty.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    for provider in ("groq", "openrouter", "google", "deepseek", "unknown"):
        assert model_catalog.get_reasoning_streaming_config(provider) == {}


def test_streaming_config_ignores_argument(catalog_db: str) -> None:
    """Streaming config ignores argument.

    Args:
        catalog_db: Path of the isolated catalog database.
    """
    assert model_catalog.get_reasoning_streaming_config(None) == {}
    assert model_catalog.get_reasoning_streaming_config("") == {}
