"""Model catalog — fetches and caches model data from models.dev.

Single source of truth from ``https://models.dev/api.json``. The catalog
is persisted in the agent's SQLite database (``agent.db``) so queries are
fast (indexed B-tree) and the data survives process restarts.

Sync strategy:

- A sync is triggered automatically when the user saves an API key for a
  provider (see ``provider_keys.save_key``).
- Each provider sync is rate-limited to once every 24 hours.
- Only providers with a configured API key are synced (except Ollama,
  which is handled separately in ``model_resolver``).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Ensure project root is in sys.path for absolute imports
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.utils.error_logger import log_error
from backend.agent.utils.db import db_transaction, get_connection
from backend.agent.utils.queries import load_query

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MODELS_DEV_URL = "https://models.dev/api.json"
_SYNC_TTL_SECONDS = 86400  # 24 hours
_TIMEOUT_SECONDS = 30

# Sync logic version. Bump when the sync code changes (new types, new
# gap-fill sources) so the next startup re-syncs even within the TTL.
# Stored per provider in ``config_kv`` (key: ``catalog_sync_v_{provider}``).
_SYNC_CODE_VERSION = 2


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection | None:
    """Open a short-lived connection to the agent DB.

    Returns:
        A new ``sqlite3.Connection``, or ``None`` on failure.
    """
    try:
        conn = get_connection()
        from backend.agent.ddl_setup import setup_database

        setup_database(conn)
        return conn
    except Exception as e:
        log_error(str(e), source="model_catalog.py:_connect")
        logger.error("Could not open agent DB for model catalog: %s", e)
        return None


# ---------------------------------------------------------------------------
# TTL check
# ---------------------------------------------------------------------------

def should_sync(provider: str) -> bool:
    """Check whether the catalog for a provider needs refreshing.

    Uses the ``config_kv`` table to store the last sync timestamp per
    provider (key: ``catalog_sync_{provider}``) and the sync logic
    version (key: ``catalog_sync_v_{provider}``). A version mismatch
    forces exactly one re-sync after the sync code changes, even within
    the 24h TTL.

    Args:
        provider: Provider name (e.g. ``"openrouter"``).

    Returns:
        ``True`` if the catalog is stale, missing, empty for the
        provider, or synced with older sync logic.
    """
    conn = _connect()
    if conn is None:
        return True
    try:
        # Empty catalog (e.g. rows wiped by key deletion) must re-sync
        # even when the timestamp looks fresh.
        count_row = conn.execute(
            load_query("model_catalog/count_by_provider.sql"),
            (provider,),
        ).fetchone()
        if count_row is None or int(count_row["n"]) == 0:
            return True
        row = conn.execute(
            load_query("config/get_value.sql"),
            (f"catalog_sync_{provider}",),
        ).fetchone()
        if row is None:
            return True
        last_sync = float(row["value"])
        if (time.time() - last_sync) > _SYNC_TTL_SECONDS:
            return True
        version_row = conn.execute(
            load_query("config/get_value.sql"),
            (f"catalog_sync_v_{provider}",),
        ).fetchone()
        if version_row is None:
            return True
        try:
            return int(version_row["value"]) != _SYNC_CODE_VERSION
        except (TypeError, ValueError):
            return True
    except Exception:
        return True
    finally:
        conn.close()


def _set_sync_timestamp(provider: str) -> None:
    """Record the current time and sync logic version for a provider.

    Args:
        provider: Provider name.
    """
    conn = _connect()
    if conn is None:
        return
    try:
        with conn:
            conn.execute(
                load_query("config/upsert_value.sql"),
                (f"catalog_sync_{provider}", str(time.time())),
            )
            conn.execute(
                load_query("config/upsert_value.sql"),
                (f"catalog_sync_v_{provider}", str(_SYNC_CODE_VERSION)),
            )
    except Exception as e:
        log_error(str(e), source="model_catalog.py:_set_sync_timestamp")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Fetch from models.dev
# ---------------------------------------------------------------------------

def _fetch_models_dev(model_type: str | None = None) -> dict[str, Any]:
    """Download the full catalog from models.dev.

    Args:
        model_type: Optional models.dev type filter (e.g. ``"decision"``).
            ``None`` (default) fetches the default catalog, which omits
            specialized model types.

    Returns:
        The parsed JSON dict (provider → data).
    """
    import requests

    url = _MODELS_DEV_URL
    if model_type:
        url = f"{_MODELS_DEV_URL}?type={model_type}"
    resp = requests.get(
        url,
        headers={"User-Agent": "synapseForge/1.0"},
        timeout=_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()


def _extract_provider_models(catalog: dict, provider: str) -> list[dict]:
    """Extract model entries for a specific provider from the catalog.

    Args:
        catalog: The full models.dev catalog.
        provider: Provider ID (e.g. ``"openrouter"``).

    Returns:
        List of model dicts ready for DB insertion.
    """
    provider_data = catalog.get(provider)
    if not provider_data:
        return []

    provider_api = provider_data.get("api")
    provider_npm = provider_data.get("npm")
    models_raw = provider_data.get("models") or {}
    now = datetime.now().isoformat()
    rows: list[dict] = []

    for model_id, model_data in models_raw.items():
        if not isinstance(model_data, dict):
            continue

        limit = model_data.get("limit") or {}
        cost = model_data.get("cost")
        modalities = model_data.get("modalities") or {}
        reasoning_opts = model_data.get("reasoning_options") or []

        rows.append({
            "provider": provider,
            "model_id": model_id,
            "type": model_data.get("type"),
            "name": model_data.get("name"),
            "description": model_data.get("description"),
            "family": model_data.get("family"),
            "context_window": limit.get("context"),
            "input_limit": limit.get("input"),
            "output_limit": limit.get("output"),
            "reasoning": 1 if model_data.get("reasoning") else 0,
            "reasoning_options": json.dumps(reasoning_opts) if reasoning_opts else None,
            "tool_call": 1 if model_data.get("tool_call") else 0,
            "attachment": 1 if model_data.get("attachment") else 0,
            "temperature": 1 if model_data.get("temperature") else 0,
            "structured_output": 1 if model_data.get("structured_output") else 0,
            "modalities_input": json.dumps(modalities.get("input")) if modalities.get("input") else None,
            "modalities_output": json.dumps(modalities.get("output")) if modalities.get("output") else None,
            "cost_input": cost.get("input") if cost else None,
            "cost_output": cost.get("output") if cost else None,
            "cost_cache_read": cost.get("cache_read") if cost else None,
            "cost_cache_write": cost.get("cache_write") if cost else None,
            "open_weights": 1 if model_data.get("open_weights") else 0,
            "status": model_data.get("status"),
            "api": provider_api,
            "npm": provider_npm,
            "updated_at": now,
        })

    return rows


# ---------------------------------------------------------------------------
# OpenRouter supplement (models.dev has no embedding/speech/transcription
# entries for openrouter, so those models would never appear in the filter)
# ---------------------------------------------------------------------------

_OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# OpenRouter output modality -> our catalog ``type``. Text-only models are
# skipped: models.dev already covers them with richer data.
_OPENROUTER_MODALITY_TO_TYPE = {
    "image": "image",
    "video": "video",
    "speech": "speech",
    "transcription": "transcription",
    "audio": "audio",
    "embeddings": "embedding",
    "rerank": "reranking",
    "decisions": "decision",
}


def _openrouter_price_per_million(value: Any) -> float | None:
    """Convert an OpenRouter per-token price to USD per million tokens.

    Args:
        value: Price string/number from the OpenRouter API (per token).
            Negative sentinels (``-1`` dynamic routers) map to ``None``.

    Returns:
        Price in USD per million tokens, or ``None`` when unknown.
    """
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if price < 0:
        return None
    return price * 1_000_000


def _fetch_openrouter_models() -> list[dict]:
    """Fetch the full OpenRouter catalog (all output modalities).

    Uses the public OpenRouter Models API with ``output_modalities=all``
    and paginates until no more models are returned. Only non-text-output
    models are kept (text chat models already come from models.dev).

    Returns:
        List of model dicts ready for DB insertion (same keys as
        ``_extract_provider_models`` rows). Empty on any failure.
    """
    import requests

    rows: list[dict] = []
    now = datetime.now().isoformat()
    offset = 0
    try:
        while True:
            resp = requests.get(
                _OPENROUTER_MODELS_URL,
                params={"output_modalities": "all", "limit": 1000, "offset": offset},
                headers={"User-Agent": "synapseForge/1.0"},
                timeout=_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            items = (resp.json() or {}).get("data", []) or []
            if not items:
                break
            for item in items:
                if not isinstance(item, dict):
                    continue
                arch = item.get("architecture") or {}
                outputs = [str(m).strip().lower() for m in (arch.get("output_modalities") or [])]
                non_text = [m for m in outputs if m and m != "text"]
                if not non_text:
                    continue  # text chat: models.dev already covers it
                primary = non_text[0]
                mtype = _OPENROUTER_MODALITY_TO_TYPE.get(primary)
                if not mtype:
                    continue
                inputs = [str(m).strip().lower() for m in (arch.get("input_modalities") or [])]
                pricing = item.get("pricing") or {}
                supported = [str(p) for p in (item.get("supported_parameters") or [])]
                top = item.get("top_provider") or {}
                rows.append({
                    "provider": "openrouter",
                    "model_id": item.get("id"),
                    "type": mtype,
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "family": None,
                    "context_window": item.get("context_length"),
                    "input_limit": None,
                    "output_limit": top.get("max_completion_tokens"),
                    "reasoning": 1 if "reasoning" in supported else 0,
                    "reasoning_options": None,
                    "tool_call": 1 if "tools" in supported else 0,
                    "attachment": 1 if any(m != "text" for m in inputs) else 0,
                    "temperature": 1 if "temperature" in supported else 0,
                    "structured_output": 1 if "structured_outputs" in supported else 0,
                    "modalities_input": json.dumps(inputs) if inputs else None,
                    "modalities_output": json.dumps(outputs) if outputs else None,
                    "cost_input": _openrouter_price_per_million(pricing.get("prompt")),
                    "cost_output": _openrouter_price_per_million(pricing.get("completion")),
                    "cost_cache_read": None,
                    "cost_cache_write": None,
                    "open_weights": 0,
                    "status": None,
                    "api": "https://openrouter.ai/api/v1",
                    "npm": "@ai-sdk/openai-compatible",
                    "updated_at": now,
                })
            if len(items) < 1000:
                break
            offset += len(items)
    except Exception as e:
        log_error(str(e), source="model_catalog.py:_fetch_openrouter_models")
        return []
    return [r for r in rows if r.get("model_id")]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sync_catalog(provider: str) -> dict:
    """Fetch models.dev and upsert models for a provider into the DB.

    Fetches the default catalog plus the specialized ``image``,
    ``speech``, ``embedding``, ``video``, ``transcription``,
    ``decision`` and ``reranking`` catalogs so non-text outputs (image/TTS),
    embedding models and decision/rerank models are also synced.
    For ``openrouter`` the models.dev gaps (no embedding/speech/
    transcription entries) are filled from the OpenRouter Models API.
    Rate-limited to once every 24 hours per provider, plus a
    version-guard: when the sync logic changes, the next call re-syncs
    once even within the TTL.

    Args:
        provider: Provider ID (e.g. ``"openrouter"``, ``"google"``).

    Returns:
        ``{"status": "success", "models": count}`` or
        ``{"status": "error", "message": ...}``.
    """
    provider = (provider or "").strip()
    if not provider:
        return {"status": "error", "message": "Provider is empty."}

    if not should_sync(provider):
        logger.debug("Catalog for '%s' is fresh, skipping sync.", provider)
        return {"status": "success", "message": "Catalog is fresh.", "models": 0}

    merged: dict[str, dict] = {}
    try:
        for model_type in (
            None,
            "image",
            "speech",
            "embedding",
            "video",
            "transcription",
            "decision",
            "reranking",
        ):
            try:
                catalog = _fetch_models_dev(model_type)
            except Exception as e:
                log_error(str(e), source="model_catalog.py:sync_catalog(fetch)")
                if model_type is None:
                    return {"status": "error", "message": f"Could not fetch models.dev: {e}"}
                continue
            for row in _extract_provider_models(catalog, provider):
                merged[row["model_id"]] = row
        # OpenRouter gap fill: models.dev catalogs no embedding/speech/
        # transcription entries for openrouter. Supplement only adds model
        # ids models.dev does not know (setdefault: models.dev wins).
        if provider == "openrouter":
            try:
                for row in _fetch_openrouter_models():
                    merged.setdefault(row["model_id"], row)
            except Exception as e:
                log_error(str(e), source="model_catalog.py:sync_catalog(openrouter)")
    except Exception as e:
        log_error(str(e), source="model_catalog.py:sync_catalog(fetch)")
        return {"status": "error", "message": f"Could not fetch models.dev: {e}"}

    rows = list(merged.values())
    if not rows:
        return {
            "status": "error",
            "message": f"Provider '{provider}' not found in models.dev or has no models.",
        }

    conn = _connect()
    if conn is None:
        return {"status": "error", "message": "Could not open database."}

    try:
        with conn:
            conn.executemany(
                load_query("model_catalog/upsert_model.sql"),
                rows,
            )
        _set_sync_timestamp(provider)
        logger.info(
            "Synced %d model(s) for provider '%s' from models.dev.",
            len(rows),
            provider,
        )
        return {"status": "success", "models": len(rows)}
    except Exception as e:
        log_error(str(e), source="model_catalog.py:sync_catalog(insert)")
        return {"status": "error", "message": f"Database error: {e}"}
    finally:
        conn.close()


def get_models(provider: str) -> list[str]:
    """Return the list of model IDs for a provider from the catalog.

    Args:
        provider: Provider name (e.g. ``"openrouter"``).

    Returns:
        Sorted list of model ID strings. Empty if not found.
    """
    conn = _connect()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            load_query("model_catalog/list_models_by_provider.sql"),
            (provider.strip(),),
        ).fetchall()
        return [row["model_id"] for row in rows]
    except Exception as e:
        log_error(str(e), source="model_catalog.py:get_models")
        return []
    finally:
        conn.close()


def matches_model_type(
    model_type: str | None,
    modalities_output_json: str | None,
    wanted: str,
) -> bool:
    """Check whether a catalog row matches a model-type filter.

    Args:
        model_type: The ``type`` column value (may be ``None``).
        modalities_output_json: The ``modalities_output`` column value
            (JSON list, may be ``None``).
        wanted: One of ``"todos"``, ``"texto"``, ``"imagen"``, ``"audio"``,
            ``"video"``, ``"transcripcion"``, ``"embeddings"``,
            ``"decision"`` or ``"rerank"``.

    Returns:
        ``True`` when the row matches the filter.
    """
    wanted = (wanted or "todos").strip().lower()
    if wanted in ("", "todos", "all"):
        return True
    mtype = (model_type or "").strip().lower()
    try:
        outputs = json.loads(modalities_output_json) if modalities_output_json else []
    except (TypeError, ValueError):
        outputs = []
    if not isinstance(outputs, list):
        outputs = []
    outputs = [str(o).strip().lower() for o in outputs]
    if wanted == "texto":
        return mtype in ("", "chat", "text")
    if wanted == "imagen":
        return mtype == "image" or "image" in outputs
    if wanted == "audio":
        return mtype in ("speech", "audio") or "audio" in outputs
    if wanted == "video":
        return mtype == "video" or "video" in outputs
    if wanted in ("transcripcion", "transcription"):
        return mtype == "transcription"
    if wanted in ("embeddings", "embedding"):
        return mtype == "embedding" or "embedding" in outputs
    if wanted in ("decision", "decisions"):
        return mtype == "decision"
    if wanted in ("rerank", "reranking"):
        return mtype in ("rerank", "reranking")
    return False


def search_models(query: str) -> list[dict[str, Any]]:
    """Search catalog models by provider, id, name or description (case-insensitive).

    Args:
        query: Substring to match. Empty matches all.

    Returns:
        List of ``{"provider", "model_id", "type", "modalities_output"}``
        dicts ordered by provider and model id. Empty on DB errors.
    """
    escaped = (
        (query or "")
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    pattern = f"%{escaped}%"
    conn = _connect()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            load_query("model_catalog/search_models.sql"),
            (pattern, pattern, pattern, pattern),
        ).fetchall()
        return [
            {
                "provider": row["provider"],
                "model_id": row["model_id"],
                "type": row["type"],
                "modalities_output": row["modalities_output"],
            }
            for row in rows
        ]
    except Exception as e:
        log_error(str(e), source="model_catalog.py:search_models")
        return []
    finally:
        conn.close()


def get_model(provider: str, model_id: str) -> dict[str, Any] | None:
    """Return full details for a specific model from the catalog.

    Args:
        provider: Provider name.
        model_id: Model ID (e.g. ``"openai/gpt-oss-120b"``).

    Returns:
        Dict with all model fields, or ``None`` if not found.
    """
    conn = _connect()
    if conn is None:
        return None
    try:
        row = conn.execute(
            load_query("model_catalog/get_model.sql"),
            (provider.strip(), model_id),
        ).fetchone()
        if row is None:
            return None
        return dict(row)
    except Exception as e:
        log_error(str(e), source="model_catalog.py:get_model")
        return None
    finally:
        conn.close()


def get_context_window(provider: str, model_id: str) -> int | None:
    """Return the context window for a model.

    Args:
        provider: Provider name.
        model_id: Model ID.

    Returns:
        Context window in tokens, or ``None`` if unknown.
    """
    model = get_model(provider, model_id)
    if model is None:
        return None
    cw = model.get("context_window")
    return int(cw) if cw else None


def get_reasoning_options(provider: str, model_id: str) -> dict:
    """Return reasoning capabilities for a model.

    Translates the models.dev ``reasoning_options`` array into the format
    the frontend expects:

    - ``reasoning_supported``: bool | None
    - ``reasoning_options``: list of ``{"value": ..., "label": ...}``
    - ``reasoning_type``: ``"effort_levels"`` | ``"budget_tokens"`` |
      ``"toggle"`` | ``"boolean"``
    - ``response_format_supported``: bool | None (from models.dev
      ``structured_output`` flag)
    - ``model_type``: str | None (from models.dev ``type`` field, e.g.
      ``"chat"``, ``"image"``, ``"speech"``, ``"realtime"``)

    Args:
        provider: Provider name.
        model_id: Model ID.

    Returns:
        Dict with reasoning capability data.
    """
    result = {
        "reasoning_supported": None,
        "reasoning_options": [],
        "reasoning_type": None,
        "response_format_supported": None,
        "context_window": None,
        "input_limit": None,
        "output_limit": None,
        "input_modalities": None,
        "output_modalities": None,
        "model_type": None,
        "cost_input": None,
        "cost_output": None,
    }

    model = get_model(provider, model_id)
    if model is None:
        return result

    # Structured output support comes straight from models.dev.
    if model.get("structured_output") is not None:
        result["response_format_supported"] = bool(model.get("structured_output"))

    # Model family type decides which SDK call to use (chat vs image vs speech).
    if model.get("type") is not None:
        result["model_type"] = str(model.get("type"))

    # Add model info
    result["context_window"] = model.get("context_window")
    result["input_limit"] = model.get("input_limit")
    result["output_limit"] = model.get("output_limit")
    # Parse JSON modalities columns
    raw_input_mod = model.get("modalities_input")
    raw_output_mod = model.get("modalities_output")
    try:
        result["input_modalities"] = json.loads(raw_input_mod) if raw_input_mod else None
    except (json.JSONDecodeError, TypeError):
        result["input_modalities"] = None
    try:
        result["output_modalities"] = json.loads(raw_output_mod) if raw_output_mod else None
    except (json.JSONDecodeError, TypeError):
        result["output_modalities"] = None
    result["cost_input"] = model.get("cost_input")
    result["cost_output"] = model.get("cost_output")

    reasoning = model.get("reasoning")
    if not reasoning:
        result["reasoning_supported"] = False
        result["reasoning_options"] = [{"value": "default", "label": "Default"}]
        return result

    result["reasoning_supported"] = True
    raw_opts = model.get("reasoning_options")
    if not raw_opts:
        result["reasoning_options"] = [{"value": "default", "label": "Default"}]
        return result

    try:
        opts = json.loads(raw_opts) if isinstance(raw_opts, str) else raw_opts
    except (json.JSONDecodeError, TypeError):
        opts = []

    if not opts:
        result["reasoning_options"] = [{"value": "default", "label": "Default"}]
        return result

    effort_labels = {
        "max": "Máximo",
        "xhigh": "Muy alto",
        "high": "Alto",
        "medium": "Medio",
        "low": "Bajo",
        "minimal": "Mínimo",
        "none": "Ninguno",
    }

    # Collect all values first to check if "default" is already present.
    all_effort_values: list[str] = []
    budget_min: int | None = None
    budget_max: int | None = None
    has_toggle = False
    for opt in opts:
        if opt.get("type") == "effort":
            all_effort_values.extend(opt.get("values") or [])
        elif opt.get("type") == "budget_tokens":
            budget_min = opt.get("min")
            budget_max = opt.get("max")
        elif opt.get("type") == "toggle":
            has_toggle = True

    has_default = "default" in all_effort_values

    # Build budget_min/budget_max info for the frontend.
    budget_info: dict[str, Any] = {}
    if any(o.get("type") == "budget_tokens" for o in opts):
        budget_info["budget_min"] = budget_min
        budget_info["budget_max"] = budget_max

    # Add a single "Default" option at the top if models.dev doesn't include it.
    if not has_default:
        result["reasoning_options"].append(
            {"value": "default", "label": "Default"}
        )

    for opt in opts:
        opt_type = opt.get("type")

        if opt_type == "effort":
            result["reasoning_type"] = "effort_levels"
            values = opt.get("values") or []
            for v in values:
                # Map "none" to "Desactivado" instead of showing both.
                if v == "none":
                    result["reasoning_options"].append({
                        "value": "off",
                        "label": "Desactivado",
                    })
                else:
                    result["reasoning_options"].append({
                        "value": v,
                        "label": effort_labels.get(v, v),
                    })

        elif opt_type == "budget_tokens":
            result["reasoning_type"] = "budget_tokens"
            min_tok = budget_min
            max_tok = budget_max
            # Only show the text input hint, not preset values.
            result["reasoning_options"] = [
                {"value": "default", "label": "Default"}
            ]

        elif opt_type == "toggle":
            if result["reasoning_type"] is None:
                result["reasoning_type"] = "boolean"
            # Only show "Desactivado" — "Activado" is implied by
            # selecting any effort/budget level.
            result["reasoning_options"].append(
                {"value": "off", "label": "Desactivado"}
            )

    if not result["reasoning_type"]:
        result["reasoning_type"] = "boolean"

    if not result["reasoning_options"]:
        result["reasoning_options"] = [{"value": "default", "label": "Default"}]

    # Attach budget info so the frontend can render the text input.
    if budget_info:
        result["budget_min"] = budget_info.get("budget_min")
        result["budget_max"] = budget_info.get("budget_max")

    return result


def _resolve_gateway(provider: str) -> tuple[str, bool]:
    """Resolve the gateway type for reasoning translation.

    Uses the synced catalog first; falls back to ``PROVIDER_REGISTRY``
    so providers without synced models (e.g. missing from models.dev)
    still resolve to their registered API type.

    Args:
        provider: Provider name.

    Returns:
        Tuple ``(api_type, is_openrouter)`` where ``api_type`` is
        ``"openai-compatible"``, ``"google"``, ``"ollama"`` or
        ``"unknown"``, and ``is_openrouter`` flags the OpenRouter
        gateway (which uses the ``reasoning`` object shape).
    """
    try:
        api_type = get_provider_api_type(provider)
        if api_type == "unknown":
            try:
                from backend.agent.utils.provider_keys import PROVIDER_REGISTRY
            except ImportError:
                PROVIDER_REGISTRY = {}
            info = PROVIDER_REGISTRY.get((provider or "").strip(), {})
            api_type = str(info.get("api_type") or "unknown")
        return api_type, (provider or "").strip() == "openrouter"
    except Exception as e:
        log_error(str(e), source="model_catalog.py:_resolve_gateway")
        return "unknown", False


def _catalog_reasoning_shapes(model: dict[str, Any] | None) -> dict[str, Any] | None:
    """Summarize a catalog row's ``reasoning_options`` for translation.

    Args:
        model: Catalog row as returned by :func:`get_model`.

    Returns:
        Dict with ``effort_values`` (list of accepted level strings)
        and ``has_budget`` (bool). An empty options list yields empty
        shapes (model offers no caller control). ``None`` is returned
        only when the model is unknown (no row) or its options are
        missing, malformed, or not a list (gateway defaults apply).
    """
    try:
        if model is None:
            return None
        raw = model.get("reasoning_options")
        if not raw:
            return None
        opts = raw
        if isinstance(raw, str):
            try:
                opts = json.loads(raw)
            except json.JSONDecodeError:
                # Filas legacy guardadas con repr de Python en vez de JSON.
                import ast

                opts = ast.literal_eval(raw)
        if not isinstance(opts, list):
            return None
        effort_values: list[str] = []
        has_budget = False
        for opt in opts:
            if not isinstance(opt, dict):
                continue
            if opt.get("type") == "effort":
                for entry in opt.get("values") or []:
                    if isinstance(entry, str):
                        effort_values.append(entry.strip().lower())
            elif opt.get("type") == "budget_tokens":
                has_budget = True
        return {"effort_values": effort_values, "has_budget": has_budget}
    except Exception as e:
        log_error(str(e), source="model_catalog.py:_catalog_reasoning_shapes")
        return None


def translate_reasoning(
    provider: str,
    reasoning_value: str | bool | None,
    model_id: str | None = None,
    budget_tokens: int | None = None,
) -> dict[str, Any]:
    """Translate a user-facing reasoning value into provider-specific kwargs.

    The wire shape is decided by the gateway (API type): plain
    OpenAI-compatible gateways take ``reasoning_effort``, the OpenRouter
    gateway takes the ``reasoning`` object, and Google direct takes
    ``thinking_config``. When the model has a synced catalog row, its
    ``reasoning_options`` decide which values are sent; models without
    usable catalog data use the gateway default shape. A budget sent to
    Google always uses ``thinking_budget`` (Google maps it to a level
    internally on level-only models); a budget sent to OpenRouter uses
    ``max_tokens`` (ignored when the model does not support it) and an
    effort level sent to OpenRouter uses ``effort`` (converted
    automatically for budget-based models).

    Args:
        provider: Provider name (``"groq"``, ``"openrouter"``, ...).
        reasoning_value: User-selected value from DB/UI (``"default"``,
            ``"off"``, ``"low"``, ``"medium"``, ``"high"``, ``"max"``,
            ``"xhigh"``, ``"minimal"``, ``True``, ``False``, or ``None``).
        model_id: Optional model ID for catalog lookup.
        budget_tokens: Optional token budget (overrides effort levels).

    Returns:
        Dict of kwargs to merge into the API call.
    """
    try:
        prov = (provider or "").strip()
        if not prov:
            return {}
        val = reasoning_value

        # --- Normalize legacy boolean ---
        if val is None:
            return {}
        if val is True or val == "on" or val == "true":
            val = "default"
        if val is False or val == "off" or val == "false":
            val = "off"
        if val == "none":
            val = "off"

        api_type, is_openrouter = _resolve_gateway(provider)
        if api_type not in ("openai-compatible", "google"):
            return {}

        v = str(val).strip().lower()
        if not v:
            return {}

        # --- Catalog shapes (single lookup) ---
        shapes: dict[str, Any] | None = None
        if model_id:
            model = get_model(provider, model_id)
            if model is not None and not model.get("reasoning"):
                return {}
            shapes = _catalog_reasoning_shapes(model)

        # --- "off" wins over a configured budget ---
        if v == "off":
            if api_type == "google":
                if shapes is None or shapes["has_budget"]:
                    return {"thinking_config": {"thinking_budget": 0}}
                return {}
            if is_openrouter:
                return {"reasoning": {"exclude": True}}
            if shapes is None or "none" in shapes["effort_values"]:
                return {"reasoning_effort": "none"}
            return {}

        # --- Budget tokens take precedence when provided ---
        budget = None
        try:
            if budget_tokens is not None:
                budget = int(budget_tokens)
        except (TypeError, ValueError):
            budget = None
        if budget is not None and budget > 0:
            if api_type == "google":
                return {"thinking_config": {"thinking_budget": budget}}
            if is_openrouter:
                if (
                    shapes is not None
                    and not shapes["effort_values"]
                    and not shapes["has_budget"]
                ):
                    return {}
                return {"reasoning": {"max_tokens": budget}}
            # Plain gateways have no budget param: fall through to effort.

        # --- Default → don't pass reasoning param ---
        if v == "default":
            return {}

        # --- Effort level in gateway shape ---
        if api_type == "google":
            if shapes is None or v in shapes["effort_values"]:
                return {"thinking_config": {"thinking_level": v}}
            return {}
        if is_openrouter:
            if (
                shapes is not None
                and not shapes["effort_values"]
                and not shapes["has_budget"]
            ):
                return {}
            return {"reasoning": {"effort": v}}
        if shapes is None or v in shapes["effort_values"]:
            return {"reasoning_effort": v}
        return {}
    except Exception as e:
        log_error(str(e), source="model_catalog.py:translate_reasoning")
        return {}


def get_reasoning_streaming_config(provider: str) -> dict[str, Any]:
    """Get extra streaming kwargs for reasoning.

    Args:
        provider: Provider name (e.g. ``"openrouter"``).

    Returns:
        Empty dict. Reasoning travels in the request built by
        ``translate_reasoning``; streamed reasoning deltas are parsed
        from the response (``delta.reasoning`` or ``<think>`` tags).
    """
    return {}


def list_configured_providers() -> list[str]:
    """Return provider IDs that have models in the catalog.

    Returns:
        Sorted list of provider ID strings.
    """
    conn = _connect()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            load_query("model_catalog/list_providers.sql"),
        ).fetchall()
        return [row["provider"] for row in rows]
    except Exception as e:
        log_error(str(e), source="model_catalog.py:list_configured_providers")
        return []
    finally:
        conn.close()


_NPM_TO_API_TYPE: dict[str, str] = {
    "@ai-sdk/groq": "openai-compatible",
    "@openrouter/ai-sdk-provider": "openai-compatible",
    "@ai-sdk/openai": "openai-compatible",
    "@ai-sdk/openai-compatible": "openai-compatible",
    "@ai-sdk/deepseek": "openai-compatible",
    "@ai-sdk/xai": "openai-compatible",
    "@ai-sdk/togetherai": "openai-compatible",
    "@ai-sdk/fireworks": "openai-compatible",
    "@ai-sdk/cerebras": "openai-compatible",
    "@ai-sdk/mistral": "openai-compatible",
    "@ai-sdk/perplexity": "openai-compatible",
    "@ai-sdk/azure": "openai-compatible",
    "@ai-sdk/google": "google",
    "@ai-sdk/google-vertex": "google",
    "@ai-sdk/ollama": "ollama",
}
"""Map models.dev ``npm`` package → provider API type.

Providers whose ``npm`` is not listed here resolve to ``"unknown"``
and are rejected with a clear message instead of being assumed
OpenAI-compatible.
"""


def get_provider_api_type(provider: str) -> str:
    """Resolve the API type of a provider from the local catalog.

    Reads the ``npm`` package stored at sync time (no network) and maps
    it via ``_NPM_TO_API_TYPE``. ``LOCAL`` always resolves to
    ``"ollama"`` (Ollama is not in models.dev).

    Args:
        provider: Provider name (e.g. ``"openrouter"``, ``"LOCAL"``).

    Returns:
        ``"openai-compatible"``, ``"google"``, ``"ollama"`` or
        ``"unknown"`` (never assumed; unknown must be rejected by the
        caller with a clear message).
    """
    try:
        prov = (provider or "").strip()
        if not prov:
            return "unknown"
        if prov == "LOCAL":
            return "ollama"
        conn = _connect()
        if conn is None:
            return "unknown"
        try:
            row = conn.execute(
                load_query("model_catalog/get_npm.sql"),
                (prov,),
            ).fetchone()
        finally:
            conn.close()
        if row is None or not row["npm"]:
            return "unknown"
        return _NPM_TO_API_TYPE.get(str(row["npm"]).strip(), "unknown")
    except Exception as e:
        log_error(str(e), source="model_catalog.py:get_provider_api_type")
        return "unknown"
