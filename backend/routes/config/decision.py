"""Decision-model endpoints: catalog listing, selection, enable switch and model capabilities."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.instances import agent, session_manager
from backend.agent.utils.error_logger import log_error

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/models/decision")
async def list_decision_models() -> JSONResponse:
    """List decision providers and the current decision selection.

    Decision models (System One API) are selected independently from chat
    models: the user first enables the decision section, then picks a
    provider + model and applies it via ``POST
    /config/models/decision/select``. Until then the response carries
    ``model: null`` and decision calls stay gracefully unavailable.

    Returns:
        JSON response with the decision providers (with their model ids from
        the ``decision_catalog`` table) and the current selection (or nulls).
    """
    from backend.agent.utils import provider_keys

    providers = provider_keys.list_decision_providers()
    current_provider = agent.decision_provider if agent is not None else None
    current_model = agent.decision_model if agent is not None else None
    enabled = bool(agent.decision_enabled) if agent is not None else False
    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "providers": providers,
            "provider": current_provider,
            "model": current_model,
            "enabled": enabled,
        },
    )

@router.post("/models/decision/select")
async def select_decision_model(data: dict[str, Any]) -> JSONResponse:
    """Select a decision provider + model for the current session.

    Request body::

        {"model": "inception/mercury-decide:free", "provider": "openrouter"}

    The model must exist in the ``decision_catalog`` table for the given
    provider (the lists in ``GET /config/models/decision`` read from it).

    Args:
        data: Request body.

    Returns:
        JSON response with the selection, or the reason it was rejected.
    """
    model = str(data.get("model") or "").strip()
    provider = str(data.get("provider") or "").strip()

    if not model:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "model is required.",
            },
        )

    from backend.agent.utils import decision_catalog, provider_keys

    if not provider_keys.is_decision_supported(provider):
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": f"Unknown decision provider: '{provider}'.",
            },
        )

    if model not in decision_catalog.get_models(provider):
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": f"Unknown decision model '{model}' for provider '{provider}'.",
            },
        )

    if provider_keys.get_decision_key(provider) is None:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": f"Guardá primero la API key de '{provider}' abajo.",
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

    provider_id = provider.strip().lower()
    agent.decision_provider = provider_id
    agent.decision_model = model

    try:
        if session_manager is not None:
            session_manager.set_config("decision_provider", provider_id)
            session_manager.set_config("decision_model", model)
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py")
        logger.warning("No se pudo persistir el modelo de decisión: %s", exc)

    logger.info("Decision model selected: %s (%s)", model, provider_id)
    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": f"Decision model '{model}' selected.",
            "model": model,
            "provider": provider_id,
        },
    )

@router.post("/models/decision/enabled")
async def set_decision_enabled(data: dict[str, Any]) -> JSONResponse:
    """Enable or disable the decision section.

    Request body::

        {"enabled": true}

    The flag is stored in the agent singleton / persisted in SQLite
    (``config_kv`` key ``decision_enabled``). When disabled (or when no
    provider + model is selected), decision calls stay gracefully
    unavailable.

    Args:
        data: Request body.

    Returns:
        JSON response with the new flag.
    """
    enabled = data.get("enabled")
    if not isinstance(enabled, bool):
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "enabled must be a boolean.",
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

    agent.decision_enabled = enabled

    try:
        if session_manager is not None:
            session_manager.set_config(
                "decision_enabled", "true" if enabled else "false"
            )
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py")
        logger.warning("No se pudo persistir decision_enabled: %s", exc)

    logger.info("Decision enabled: %s", enabled)
    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": f"Decision {'enabled' if enabled else 'disabled'}.",
            "enabled": enabled,
        },
    )

@router.get("/models/decision/capabilities")
async def get_decision_capabilities(model: str, provider: str) -> JSONResponse:
    """Return catalog info for a specific decision model/provider.

    Same row layout as the chat "Info del modelo" (modalities, context,
    limits, costs), read from the ``decision_catalog`` table synced from
    ``models.dev?type=decision``.

    Args:
        model: Decision model ID.
        provider: Provider name.

    Returns:
        JSON response with the catalog row, or 404 when the model is not in the catalog.
    """
    if not model or not provider:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "model and provider query params are required.",
            },
        )
    try:
        from backend.agent.utils import decision_catalog

        row = await asyncio.to_thread(
            decision_catalog.get_model, provider.strip(), model
        )
        if row is None:
            return JSONResponse(
                status_code=200,
                content={"status": "success", "found": False},
            )
        import json as _json

        def _parse_list(raw: object) -> list[str] | None:
            """Parse a JSON list column of the catalog.

            Args:
                raw: The stored value (JSON text or a list).

            Returns:
                The list of strings, or None when it cannot be read.
            """
            if not raw:
                return None
            try:
                val = _json.loads(raw) if isinstance(raw, str) else raw
                return list(val) if isinstance(val, list) else None
            except (ValueError, TypeError):
                return None

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "found": True,
                "context_window": row.get("context_window"),
                "input_limit": row.get("input_limit"),
                "output_limit": row.get("output_limit"),
                "input_modalities": _parse_list(row.get("modalities_input")),
                "output_modalities": _parse_list(row.get("modalities_output")),
                "cost_input": row.get("cost_input"),
                "cost_output": row.get("cost_output"),
            },
        )
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py:get_decision_capabilities")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Error obteniendo capacidades: {exc}"},
        )
