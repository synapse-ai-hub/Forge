"""Model endpoints: list and select the chat model, and query its capabilities."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.instances import agent, session_manager
from backend.agent.utils import model_catalog
from backend.agent.utils.error_logger import log_error
from backend.routes.config.parameters import _PARAM_KEYS, _parse_optional_float, _persist_param
from backend.routes.config.runtime import _detect_and_persist_context_window

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model selection
# ---------------------------------------------------------------------------


def _effective_provider(provider: str | None = None) -> str:
    """Return the effective provider: query param, else persisted selection.

    No environment/default fallback: when nothing was explicitly selected
    the empty string is returned so callers treat it as "no provider chosen"
    (the UI then shows no provider pre-selected).

    Args:
        provider: Explicit provider from the query param, if any.

    Returns:
        Provider name as configured, or empty string when none was selected.
    """
    if provider:
        return provider.strip()

    if session_manager is not None:
        try:
            persisted = session_manager.get_config("selected_provider")
            if persisted:
                return persisted.strip()
        except Exception as exc:
            log_error(str(exc), source="backend/routes/config.py")
            logger.warning("No se pudo leer el proveedor persistido: %s", exc)

    return ""

@router.get("/models")
async def list_models(provider: str | None = None) -> JSONResponse:
    """List available models for the current provider.

    Uses the explicit ``provider`` query param if supplied. Otherwise it uses
    the selected provider from persisted config (never environment
    variables).

    - ``LOCAL`` → models from the startup cache (Ollama).
    - any curated cloud provider → models from the startup cache.

    No model is selected automatically: the user must pick one and apply it
    via ``POST /config/models/select``. The response carries ``model: null``
    until then (a previously persisted selection is still honored).

    Returns the list of model IDs/names and the selected model (or null).
    """
    provider = _effective_provider(provider)

    # Nothing selected yet: return empty lists so the UI shows no provider
    # and no model pre-selected. The user must pick both explicitly.
    if not provider:
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "provider": "",
                "provider_label": None,
                "models": [],
                "model": None,
            },
        )

    # Serve models from the startup cache (providers table) — no network calls.
    cached_providers = session_manager.get_providers() if session_manager is not None else []
    cached = next(
        (p for p in cached_providers if p["provider"] == provider),
        None,
    )
    if cached is None:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": f"Unknown PROVIDER: '{provider}'.",
            },
        )

    models = cached["models"]
    provider_label = cached["label"]

    previous_provider = agent.provider if agent is not None else None
    if agent is not None and agent.provider != provider:
        agent.provider = provider

    selected_model = None
    if agent is not None and previous_provider == provider:
        selected_model = agent._resolved_model

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "provider": provider,
            "provider_label": provider_label,
            "models": models,
            "model": agent._resolved_model if agent is not None else None,
        },
    )

@router.post("/models/select")
async def select_model(data: dict[str, Any]) -> JSONResponse:
    """Select a model and provider for the current session.

    Request body::

        {"model": "llama3.2", "provider": "LOCAL",
         "temperature": 0.7, "top_p": 0.9, "reasoning": true}

    ``temperature``, ``top_p``, ``reasoning``, ``budget_tokens`` and
    ``response_format`` are optional advanced
    parameters; ``null`` (or omitted) means "default" (the agent's
    frontmatter value, or the hardcoded fallback). The selection and the
    parameters are stored in the agent singleton / persisted in SQLite
    (``config_kv`` keys ``param_temperature``, ``param_top_p``,
    ``param_reasoning``, ``param_budget_tokens``,
    ``param_response_format``).

    If ``reasoning=true`` is sent for a model that declaratively does not
    support reasoning (per the provider catalog), the request is rejected
    with a contract error response.
    """
    model = data.get("model", "").strip()
    provider = data.get("provider", "").strip()

    if not model:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "model is required.",
            },
        )

    from backend.agent.utils import provider_keys

    if provider != "LOCAL" and not provider_keys.is_supported(provider):
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": f"Unknown provider: '{provider}'.",
            },
        )

    # --- Optional advanced parameters (None = default) ---
    temperature, temp_err = _parse_optional_float(data.get("temperature"), 0.0, 2.0)
    if temp_err:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": f"temperature {temp_err}"},
        )
    top_p, top_p_err = _parse_optional_float(data.get("top_p"), 0.0, 1.0)
    if top_p_err:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": f"top_p {top_p_err}"},
        )
    reasoning = data.get("reasoning", None)
    if reasoning is not None and not isinstance(reasoning, str):
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "reasoning must be a string or null (default).",
            },
        )
    response_format = data.get("response_format", None)
    if response_format is not None:
        if not isinstance(response_format, str):
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "response_format must be 'text', 'json' or null (default).",
                },
            )
        response_format = response_format.strip().lower()
        if response_format not in ("text", "json"):
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "response_format must be 'text', 'json' or null (default).",
                },
            )
    budget_tokens = data.get("budget_tokens", None)
    if budget_tokens is not None:
        try:
            budget_tokens = int(budget_tokens)
            if budget_tokens < 0:
                raise ValueError
        except (TypeError, ValueError):
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "budget_tokens must be a positive integer or null.",
                },
            )

    if agent is None:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "message": "Agent not initialised.",
            },
        )

    # --- Reasoning capacity validation (declarative catalog check) ---
    if reasoning and reasoning not in ("default", ""):
        try:
            if provider == "LOCAL":
                from backend.agent.utils.model_resolver import model_supports_reasoning
                supports_reasoning = await asyncio.to_thread(
                    model_supports_reasoning, provider, model
                )
            else:
                caps = await asyncio.to_thread(
                    model_catalog.get_reasoning_options,
                    provider.strip(),
                    model,
                )
                supports_reasoning = caps.get("reasoning_supported")
        except Exception as exc:
            log_error(str(exc), source="backend/routes/config.py:select_model(reasoning_check)")
            supports_reasoning = None
        if supports_reasoning is False:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": (
                        f"Model '{model}' does not support reasoning. "
                        "Set reasoning to default/no or pick another model."
                    ),
                },
            )

    # --- Structured output validation (declarative catalog check) ---
    if response_format == "json":
        try:
            if provider == "LOCAL":
                from backend.agent.utils.model_resolver import get_model_reasoning_options
                local_caps = await asyncio.to_thread(
                    get_model_reasoning_options, provider, model
                )
                supports_format = local_caps.get("response_format_supported")
            else:
                caps = await asyncio.to_thread(
                    model_catalog.get_reasoning_options,
                    provider.strip(),
                    model,
                )
                supports_format = caps.get("response_format_supported")
        except Exception as exc:
            log_error(str(exc), source="backend/routes/config.py:select_model(format_check)")
            supports_format = None
        if supports_format is False:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": (
                        f"Model '{model}' does not support structured output. "
                        "Set response_format to text/default or pick another model."
                    ),
                },
            )

    # Liberar modelo anterior si es LOCAL (Ollama) y cambió
    modelo_anterior = agent._resolved_model
    if modelo_anterior and modelo_anterior != model and agent.provider == "LOCAL":
        try:
            from backend.agent.utils.clean_memory import liberar_modelo
            await asyncio.to_thread(liberar_modelo, modelo_anterior)
            logger.info("Modelo anterior liberado: %s", modelo_anterior)
        except Exception as exc:
            log_error(str(exc), source="backend/routes/config.py:select_model")
            logger.warning("No se pudo liberar modelo anterior %s: %s", modelo_anterior, exc)

    agent._resolved_model = model
    agent.provider = provider

    try:
        if session_manager is not None:
            session_manager.set_config("selected_model", model)
            session_manager.set_config("selected_provider", provider)
            # Persist advanced parameters together with the model
            # ("null" = default / no override).
            _persist_param(_PARAM_KEYS["temperature"], temperature)
            _persist_param(_PARAM_KEYS["top_p"], top_p)
            _persist_param(_PARAM_KEYS["reasoning"], reasoning)
            _persist_param(_PARAM_KEYS["budget_tokens"], budget_tokens)
            _persist_param(_PARAM_KEYS["response_format"], response_format)
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py")
        logger.warning("No se pudo persistir el modelo o proveedor seleccionado: %s", exc)

    # Detect and persist the model's context window (tokens) — same helper used
    # by the first-startup default resolution, so both are always persisted
    # together.
    await asyncio.to_thread(_detect_and_persist_context_window, model, provider)

    # Broadcast the change so every frontend (and any other subscriber)
    # refreshes — the web UI path already dispatches a local event, but the
    # SSE broadcast makes Telegram↔Frontend bidirectional and keeps multiple
    # browser tabs in sync.
    try:
        from backend.event_bus import event_bus
        await event_bus.emit({
            "type": "model_changed",
            "content": {"model": model, "provider": provider},
        })
    except Exception as exc:
        logger.warning("No se pudo emitir model_changed: %s", exc)

    logger.info("Model selected: %s (%s)", model, provider)
    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": f"Model '{model}' selected.",
            "model": model,
            "provider": provider,
            "temperature": temperature,
            "top_p": top_p,
            "reasoning": reasoning,
            "budget_tokens": budget_tokens,
            "response_format": response_format,
        },
    )

@router.get("/models/capabilities")
async def get_model_capabilities(model: str, provider: str) -> JSONResponse:
    """Return reasoning capabilities for a specific model/provider.

    Query params:
        model: Model name/ID
        provider: Provider name (LOCAL or any curated cloud provider)

    Returns:
        reasoning_supported: boolean
        reasoning_options: array of {value, label} for the reasoning dropdown
        reasoning_type: "effort_levels" | "budget_tokens" | "boolean"
        response_format_supported: boolean (structured output support)
        temperature_supported: boolean
        tool_call_supported: boolean
        found: whether the model exists in the local catalog
    """
    if not model or not provider:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "model and provider query params are required.",
            },
        )

    provider_u = provider.strip()

    try:
        if provider_u == "LOCAL":
            # Ollama: use legacy model_resolver (no models.dev)
            from backend.agent.utils.model_resolver import get_model_reasoning_options

            caps = await asyncio.to_thread(
                get_model_reasoning_options, provider_u, model
            )
            found = True
            temperature_supported: bool | None = True
            tool_call_supported: bool | None = None
        else:
            # Cloud providers: use model_catalog from models.dev
            caps = await asyncio.to_thread(
                model_catalog.get_reasoning_options, provider.strip(), model
            )
            row = await asyncio.to_thread(
                model_catalog.get_model, provider.strip(), model
            )
            found = row is not None
            temperature_supported = bool(row.get("temperature")) if row else None
            tool_call_supported = bool(row.get("tool_call")) if row else None

        # Build response with only fields that have values
        response_data = {"status": "success", "found": found}
        for key, value in caps.items():
            if value is not None and value != []:
                response_data[key] = value
        if temperature_supported is not None:
            response_data["temperature_supported"] = temperature_supported
        if tool_call_supported is not None:
            response_data["tool_call_supported"] = tool_call_supported
        return JSONResponse(
            status_code=200,
            content=response_data,
        )
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py:get_model_capabilities")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Error obteniendo capacidades: {exc}"},
        )
