"""Runtime config: context window, verbose mode, setup flag and persisted-config loading."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.instances import agent, session_manager
from backend.agent.utils.model_resolver import (
    get_ollama_context_window,
    get_vram_gb,
    ollama_default_context,
)
from backend.agent.utils import model_catalog
from backend.agent.utils.error_logger import log_error

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Runtime config — defaults applied if the user never calls POST.
# ---------------------------------------------------------------------------

_context_window_turns: int = -1

"""Number of turns to keep in context.  ``-1`` = all.  Set via
``POST /config/context-window``."""

_context_window_tokens: int | None = None

"""Context window (tokens) of the selected model. Detected at model
selection (Ollama ``/api/show`` / OpenAI-compatible ``/models``) and persisted in
``config_kv`` as ``selected_model_context_window``."""

_vram_gb: int | None = None

"""Total VRAM in GB, detected once at startup and read from ``config_kv``."""

_verbose_mode: bool = False

"""Whether verbose mode (show tool / sub-agent cards) is enabled.
Set via ``POST /config/verbose-mode``."""

def _detect_and_persist_context_window(model: str, provider: str) -> int | None:
    """Resolve the model's context window, cache it and persist it in one place.

    Single source of truth for context-window detection. Every code path that
    sets the active model (first-startup default resolution, user model
    selection, background startup fix) calls this so ``selected_model`` and
    ``selected_model_context_window`` are always persisted together.

    Args:
        model: The model name/ID.
        provider: ``"LOCAL"`` or any curated cloud provider name.

    Returns:
        The context window in tokens, or ``None`` if it cannot be resolved.
    """
    global _context_window_tokens
    cw = None
    try:
        if provider == "LOCAL":
            cw = get_ollama_context_window(model)
        else:
            # Cloud providers: use model_catalog from models.dev
            cw = model_catalog.get_context_window(provider.strip(), model)
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py:_detect_and_persist_context_window")
        logger.warning("No se pudo detectar la context window de %s: %s", model, exc)
        return None
    if cw:
        _context_window_tokens = cw
        if agent is not None:
            agent._context_window = cw
        if session_manager is not None:
            session_manager.set_config("selected_model_context_window", str(cw))
        logger.info("Context window for %s: %d tokens", model, cw)
    else:
        logger.warning("No se pudo detectar la context window de %s", model)
    return cw

def detect_context_window_background() -> None:
    """Detect and persist the context window for the active model, if missing.

    Called once at application startup (like VRAM detection) so the active
    model's context window is resolved without blocking any request.
    """
    if agent is None or agent._resolved_model is None:
        return
    if session_manager is not None and session_manager.get_config("selected_model_context_window"):
        return
    _detect_and_persist_context_window(agent._resolved_model, agent.provider)

@router.get("/context-window")
async def get_context_window() -> JSONResponse:
    """Return the current context-window turn limit (``-1`` = all).

    Returns:
        JSON response with ``max_turns``.
    """
    vram = _vram_gb
    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "max_turns": _context_window_turns,
            "context_window_tokens": _context_window_tokens,
            "vram_gb": vram,
            "ollama_default_context": ollama_default_context(vram),
        },
    )

@router.post("/context-window")
async def set_context_window(data: dict[str, Any]) -> JSONResponse:
    """Set the context-window turn limit.

    Request body::

        {"max_turns": 10}

    ``-1`` means *all turns*. The value must be ``-1`` or a positive integer.

    Args:
        data: Request body.

    Returns:
        JSON response with the stored value, or the validation error.
    """
    try:
        value = int(data.get("max_turns", -1))
    except (ValueError, TypeError) as e:
        log_error(str(e), source="backend/routes/config.py")
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "max_turns must be an integer (-1 = all turns).",
            },
        )

    if value < -1 or value == 0:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "max_turns must be -1 (all) or a positive integer.",
            },
        )

    global _context_window_turns
    _context_window_turns = value

    try:
        if session_manager is not None:
            session_manager.set_config("context_window_turns", str(value))
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py")
        logger.warning("No se pudo persistir la ventana de contexto: %s", exc)

    logger.info("Context window set to %d turns", value)
    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": f"Context window set to {value} turn(s).",
            "max_turns": value,
        },
    )

# ---------------------------------------------------------------------------
# Verbose mode
# ---------------------------------------------------------------------------


@router.get("/verbose-mode")
async def get_verbose_mode() -> JSONResponse:
    """Return the current verbose-mode flag.

    Returns:
        JSON response with ``verbose_mode``.
    """
    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "verbose_mode": _verbose_mode,
        },
    )

@router.post("/verbose-mode")
async def set_verbose_mode(data: dict[str, Any]) -> JSONResponse:
    """Set the verbose-mode flag.

    Request body::

        {"verbose_mode": true}

    Args:
        data: Request body.

    Returns:
        JSON response with the stored flag.
    """
    raw = data.get("verbose_mode", False)
    if not isinstance(raw, bool):
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "verbose_mode must be a boolean.",
            },
        )
    value = raw

    global _verbose_mode
    _verbose_mode = value

    try:
        if session_manager is not None:
            session_manager.set_config("verbose_mode", str(value))
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py")
        logger.warning("No se pudo persistir verbose_mode: %s", exc)

    logger.info("Verbose mode set to %s", value)
    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": f"Verbose mode set to {value}.",
            "verbose_mode": value,
        },
    )

@router.get("/setup-completed")
async def get_setup_completed() -> JSONResponse:
    """Return whether the initial provider-setup screen was completed.

    The flag is persisted in ``config_kv`` and set when the user saves a
    valid API key or skips the initial setup screen, so the screen is only
    shown on first launch (regardless of whether Ollama is available).

    Returns:
        JSON response with ``completed``.
    """
    completed = False
    if session_manager is not None:
        try:
            raw = session_manager.get_config("setup_completed")
            completed = (raw or "").strip().lower() == "true"
        except Exception as exc:
            log_error(str(exc), source="backend/routes/config.py")
            logger.warning("No se pudo leer setup_completed: %s", exc)
    return JSONResponse(
        status_code=200,
        content={"status": "success", "completed": completed},
    )

@router.post("/setup-completed")
async def set_setup_completed() -> JSONResponse:
    """Mark the initial provider-setup screen as completed (or skipped).

    Returns:
        JSON response with the result.
    """
    try:
        if session_manager is not None:
            session_manager.set_config("setup_completed", "true")
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py")
        logger.warning("No se pudo persistir setup_completed: %s", exc)
    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": "Setup marked as completed.",
        },
    )

# ---------------------------------------------------------------------------
# Persisted config loading (SQLite -> in-memory state)
# ---------------------------------------------------------------------------


def load_persisted_config() -> None:
    """Load persisted model and context-window config from SQLite.

    Reads the ``selected_model`` and ``selected_provider`` and
    ``context_window_turns`` keys from the session manager's key-value store
    and applies them to the in-memory state (``agent._resolved_model``, the
    runtime provider, and the module-level ``_context_window_turns`` global).
    Each load is guarded so a failure in one does not prevent the other from
    being applied.
    """
    if session_manager is None:
        return

    try:
        model = session_manager.get_config("selected_model")
        provider = session_manager.get_config("selected_provider")
        if provider and agent is not None:
            agent.provider = provider.strip()
            logger.info("Proveedor persistido cargado desde SQLite: %s", provider)
        if model and agent is not None:
            agent._resolved_model = model
            logger.info("Modelo persistido cargado desde SQLite: %s", model)
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py")
        logger.warning("No se pudo cargar el modelo o proveedor persistidos: %s", exc)

    try:
        cw = session_manager.get_config("context_window_turns")
        if cw is not None:
            global _context_window_turns
            _context_window_turns = int(cw)
            logger.info("Ventana de contexto persistida cargada: %s", cw)
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py")
        logger.warning("No se pudo cargar la ventana de contexto: %s", exc)

    try:
        cwt = session_manager.get_config("selected_model_context_window")
        if cwt is not None:
            global _context_window_tokens
            _context_window_tokens = int(cwt)
            if agent is not None:
                agent._context_window = _context_window_tokens
            logger.info("Context window de modelo persistida cargada: %s", cwt)
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py")
        logger.warning("No se pudo cargar la context window de modelo: %s", exc)

    try:
        vm = session_manager.get_config("verbose_mode")
        if vm is not None:
            global _verbose_mode
            _verbose_mode = vm.lower() == "true"
            logger.info("Verbose mode persistido cargado: %s", _verbose_mode)
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py")
        logger.warning("No se pudo cargar verbose_mode: %s", exc)

    try:
        dprovider = session_manager.get_config("decision_provider")
        dmodel = session_manager.get_config("decision_model")
        denabled = session_manager.get_config("decision_enabled")
        if agent is not None:
            if dprovider:
                agent.decision_provider = dprovider.strip()
            if dmodel:
                agent.decision_model = dmodel
            agent.decision_enabled = (
                denabled.strip().lower() == "true" if denabled else False
            )
            logger.info(
                "Selección de decisión persistida cargada: %s/%s (enabled=%s)",
                agent.decision_provider, agent.decision_model,
                agent.decision_enabled,
            )
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py")
        logger.warning("No se pudo cargar la selección de decisión: %s", exc)

# Detect VRAM once at startup (it does not change while the app runs).
    # The result is cached in model_resolver and persisted in config_kv.
    try:
        global _vram_gb
        _vram_gb = get_vram_gb()
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py:load_persisted_config(vram)")
