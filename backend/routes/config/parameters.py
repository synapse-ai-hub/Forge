"""Advanced model parameters (temperature, top_p, reasoning, ...) persisted in ``config_kv``."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.instances import agent, session_manager
from backend.agent.utils import model_catalog
from backend.agent.utils.error_logger import log_error

router = APIRouter()

# ---------------------------------------------------------------------------
# Advanced parameters (temperature / top_p / reasoning)
# ---------------------------------------------------------------------------

_PARAM_KEYS = {
    "temperature": "param_temperature",
    "top_p": "param_top_p",
    "reasoning": "param_reasoning",
    "budget_tokens": "param_budget_tokens",
    "response_format": "param_response_format",
}

"""Mapping of parameter name → ``config_kv`` key. Persisted values use the
literal string ``"null"`` for "default" (no override)."""

def _parse_optional_float(raw: Any, low: float, high: float) -> tuple[float | None, str | None]:
    """Parse an optional float parameter (``None`` = default).

    Args:
        raw: Raw value from the request body (float, int or ``None``).
        low: Minimum accepted value (inclusive).
        high: Maximum accepted value (inclusive).

    Returns:
        Tuple ``(value, error)`` — exactly one of the two is ``None``.
    """
    if raw is None:
        return None, None
    if isinstance(raw, bool):
        return None, f"must be a number between {low} and {high}, or null."
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None, f"must be a number between {low} and {high}, or null."
    if value < low or value > high:
        return None, f"must be a number between {low} and {high}, or null."
    return value, None

def _persist_param(key: str, value: Any) -> None:
    """Persist one advanced parameter in ``config_kv``.

    Args:
        key: ``config_kv`` key (see ``_PARAM_KEYS``).
        value: Parameter value; ``None`` is stored as the literal string
            ``"null"`` (= default / no override).
    """
    if session_manager is None:
        return
    stored = "null" if value is None else str(value)
    session_manager.set_config(key, stored)

def _read_param(key: str) -> Any:
    """Read one advanced parameter from ``config_kv``.

    Args:
        key: ``config_kv`` key (see ``_PARAM_KEYS``).

    Returns:
        The parsed value (``float`` for temperature/top_p, ``str`` for
        reasoning/response_format, ``int`` for budget_tokens) or ``None``
        when unset/"null" (default).
    """
    if session_manager is None:
        return None
    raw = session_manager.get_config(key)
    if raw is None or raw.strip().lower() == "null":
        return None
    try:
        if key == _PARAM_KEYS["reasoning"]:
            return raw.strip().lower()
        if key == _PARAM_KEYS["response_format"]:
            return raw.strip().lower()
        if key == _PARAM_KEYS["budget_tokens"]:
            return int(float(raw))
        return float(raw)
    except (TypeError, ValueError):
        return None

@router.get("/parameters")
async def get_parameters() -> JSONResponse:
    """Return the persisted advanced parameters (``null`` = default).

    Also reports whether the currently selected model declaratively supports
    reasoning (``reasoning_supported``) and structured output
    (``response_format_supported``): ``true``/``false`` per the provider
    catalog, or ``null`` when capability is unknown.
    """
    try:
        current_model = agent._resolved_model if agent is not None else None
        current_provider = agent.provider if agent is not None else ""
        reasoning_supported: bool | None = None
        response_format_supported: bool | None = None
        if current_model and current_provider:
            if current_provider == "LOCAL":
                from backend.agent.utils.model_resolver import (
                    get_model_reasoning_options,
                    model_supports_reasoning,
                )
                reasoning_supported = await asyncio.to_thread(
                    model_supports_reasoning, current_provider, current_model
                )
                local_caps = await asyncio.to_thread(
                    get_model_reasoning_options, current_provider, current_model
                )
                response_format_supported = local_caps.get("response_format_supported")
            else:
                caps = await asyncio.to_thread(
                    model_catalog.get_reasoning_options,
                    current_provider.strip(),
                    current_model,
                )
                reasoning_supported = caps.get("reasoning_supported")
                response_format_supported = caps.get("response_format_supported")
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "temperature": _read_param(_PARAM_KEYS["temperature"]),
                "top_p": _read_param(_PARAM_KEYS["top_p"]),
                "reasoning": _read_param(_PARAM_KEYS["reasoning"]),
                "budget_tokens": _read_param(_PARAM_KEYS["budget_tokens"]),
                "response_format": _read_param(_PARAM_KEYS["response_format"]),
                "model": current_model,
                "provider": current_provider or "",
                "reasoning_supported": reasoning_supported,
                "response_format_supported": response_format_supported,
            },
        )
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py:get_parameters")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Error leyendo parámetros: {exc}"},
        )
