"""Provider endpoints: model catalog sync, provider listing and API key management."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.instances import agent, session_manager
from backend.agent.utils.model_resolver import get_ollama_models
from backend.agent.utils import model_catalog
from backend.agent.utils.error_logger import log_error

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Available providers
# ---------------------------------------------------------------------------


def refresh_providers_cache() -> None:
    """Sync model catalog from models.dev for each provider with an API key.

    Called once at application startup.  For cloud providers (any curated
    provider with a stored key) the catalog is synced from models.dev into the
    ``model_catalog`` table.  For Ollama (LOCAL) the models are listed
    directly via ``ollama list`` and stored in the ``providers`` table.
    """
    cached: list[dict[str, Any]] = []

    from backend.agent.utils import provider_keys

    # Ollama — try ``ollama list``
    try:
        ollama_models = get_ollama_models()
        if ollama_models:
            cached.append(
                {"provider": "LOCAL", "label": "Ollama (local)", "models": ollama_models}
            )
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py:refresh_providers_cache(ollama)")
        logger.warning("No se pudieron listar modelos de Ollama: %s", exc)

    # Cloud providers — sync from models.dev for each configured key.
    _PROVIDER_LABELS = {
        entry["provider"]: entry["label"]
        for entry in provider_keys.list_supported()
    }
    for provider_id in list(_PROVIDER_LABELS):
        try:
            api_key = provider_keys.resolve_api_key(provider_id)
            if not api_key:
                continue
            # Sync catalog from models.dev (rate-limited to 24h).
            result = model_catalog.sync_catalog(provider_id)
            # Whether sync ran or was skipped (fresh catalog), get models.
            models = model_catalog.get_models(provider_id)
            if models:
                cached.append({
                    "provider": provider_id,
                    "label": _PROVIDER_LABELS.get(provider_id, provider_id),
                    "models": models,
                })
        except Exception as exc:
            log_error(str(exc), source=f"backend/routes/config.py:refresh_providers_cache({provider_id})")
            logger.warning("No se pudieron listar modelos de %s: %s", provider_id, exc)

    if session_manager is not None:
        session_manager.save_providers(cached)
    logger.info("Providers cache refreshed: %s", [p["provider"] for p in cached])

@router.get("/providers")
async def list_providers() -> JSONResponse:
    """Return the list of available providers from the startup cache.

    Providers and their model lists are resolved once at application startup
    and persisted in the ``providers`` table, so this endpoint serves them
    from SQLite without per-request network calls.
    """
    providers = session_manager.get_providers() if session_manager is not None else []
    available = [{"provider": p["provider"], "label": p["label"]} for p in providers]
    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "providers": available,
        },
    )

# ---------------------------------------------------------------------------
# Provider API keys (encrypted storage in SQLite)
# ---------------------------------------------------------------------------


@router.get("/providers/keys")
async def list_provider_keys() -> JSONResponse:
    """Return which providers have an API key configured.

    Only availability status is exposed — the key material never leaves
    the backend.
    """
    from backend.agent.utils import provider_keys

    try:
        keys = provider_keys.list_configured()
        # Include decision-only providers (same dropdown, same table).
        try:
            from backend.agent.utils import decision_catalog

            try:
                decision_catalog.sync_catalog()
            except Exception:
                pass
            seen = {k.get("provider") for k in keys}
            for pid in decision_catalog.list_providers():
                if pid in seen:
                    continue
                keys.append({
                    "provider": pid,
                    "configured": provider_keys.get_decision_key(pid) is not None,
                })
        except Exception as exc:
            log_error(str(exc), source="backend/routes/config.py:list_provider_keys(decision)")
        return JSONResponse(
            status_code=200,
            content={"status": "success", "keys": keys},
        )
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py:list_provider_keys")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Error consultando API keys: {exc}"},
        )

@router.put("/providers/{provider}/key")
async def save_provider_key(provider: str, data: dict[str, Any]) -> JSONResponse:
    """Validate, store (encrypted) and activate the API key for a provider.

    Body: ``{"api_key": "..."}``. Chat providers are validated against
    the live API first; decision-only providers (any catalog provider
    outside the chat registry) are stored directly — their gateways
    expose only System One, with nothing to validate against. Same
    table, same endpoint: a decision provider is just another provider.
    """
    from backend.agent.utils import provider_keys

    api_key = (data or {}).get("api_key", "")
    pid = (provider or "").strip().lower()
    if pid in provider_keys.PROVIDER_REGISTRY:
        validation = await asyncio.to_thread(provider_keys.validate_key, provider, api_key)
        if validation.get("status") != "success":
            return JSONResponse(status_code=400, content=validation)
        result = await asyncio.to_thread(provider_keys.save_key, provider, api_key)
        if result.get("status") != "success":
            return JSONResponse(status_code=400, content=result)
    elif provider_keys.is_decision_supported(pid):
        result = await asyncio.to_thread(provider_keys.save_decision_key, provider, api_key)
        if result.get("status") != "success":
            return JSONResponse(status_code=400, content=result)
        return JSONResponse(status_code=200, content=result)
    else:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": f"Provider inválido: '{provider}'."},
        )
    # Refresh the providers cache FIRST so the new provider becomes
    # selectable immediately even if the client rebuild below fails.
    await asyncio.to_thread(refresh_providers_cache)
    if agent is not None:
        rebuild = await asyncio.to_thread(agent.rebuild_provider_client, provider)
        if rebuild.get("status") != "success":
            return JSONResponse(status_code=500, content=rebuild)
    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": f"API key de {(provider or '').strip()} validada y guardada.",
        },
    )

@router.delete("/providers/{provider}/key")
async def delete_provider_key(provider: str) -> JSONResponse:
    """Remove the stored API key for a provider and rebuild its client.

    After deletion the client becomes unavailable and the providers cache
    is refreshed so the provider disappears from the selectable list.
    Decision-only providers are deleted from the same table.
    """
    from backend.agent.utils import provider_keys

    pid = (provider or "").strip().lower()
    if pid not in provider_keys.PROVIDER_REGISTRY:
        if provider_keys.is_decision_supported(pid):
            try:
                from backend.agent.utils.db import get_connection

                conn = get_connection()
                if conn is None:
                    return JSONResponse(
                        status_code=500,
                        content={"status": "error", "message": "No se pudo abrir la base de datos."},
                    )
                try:
                    with conn:
                        cursor = conn.execute(
                            "DELETE FROM provider_api_keys WHERE provider = ?",
                            (pid,),
                        )
                        deleted = cursor.rowcount > 0
                finally:
                    conn.close()
                message = (
                    f"API key de {pid} eliminada."
                    if deleted
                    else f"No había API key guardada para {pid}."
                )
                return JSONResponse(status_code=200, content={"status": "success", "message": message})
            except Exception as exc:
                log_error(str(exc), source="backend/routes/config.py:delete_provider_key(decision)")
                return JSONResponse(
                    status_code=500,
                    content={"status": "error", "message": f"Error eliminando la API key: {exc}"},
                )
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": f"Provider inválido: '{provider}'."},
        )

    result = await asyncio.to_thread(provider_keys.delete_key, provider)
    if result.get("status") != "success":
        return JSONResponse(status_code=400, content=result)
    # Refresh the providers cache FIRST so the removed provider disappears
    # even if the client rebuild below fails.
    await asyncio.to_thread(refresh_providers_cache)
    if agent is not None:
        rebuild = await asyncio.to_thread(agent.rebuild_provider_client, provider)
        if rebuild.get("status") != "success":
            return JSONResponse(status_code=500, content=rebuild)
    return JSONResponse(status_code=200, content=result)
