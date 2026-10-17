"""Decision model catalog — System One models in SQLite.

Synced from ``https://models.dev/api.json?type=decision`` (any provider
with decision models). The ``decision_catalog`` table holds one row per
``(provider, model_id)``; the dropdowns (``GET /config/models/decision``)
read from this table. If the sync has not run yet (offline or first start),
the catalog is empty and no models are shown.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Ensure project root is in sys.path for absolute imports
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.utils.error_logger import log_error
from backend.agent.utils.db import get_connection
from backend.agent.utils.queries import load_query

logger = logging.getLogger(__name__)


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
        log_error(str(e), source="decision_catalog.py:_connect")
        logger.error("Could not open agent DB for decision catalog: %s", e)
        return None


def sync_catalog() -> dict:
    """Fetch ``models.dev?type=decision`` and upsert every decision model.

    Covers any provider (``openrouter``, ``nano-gpt``, ``vercel``,
    ``opencode``, ``cloudflare-workers-ai``, ...), not a curated pair.
    Rate-limited to once every 24 hours via ``config_kv``
    (``decision_catalog_sync``).

    Returns:
        ``{"status": "success", "models": count}`` or
        ``{"status": "error", "message": ...}``.
    """
    import json as _json
    import time as _time

    import requests

    conn = _connect()
    if conn is None:
        return {"status": "error", "message": "Could not open database."}
    try:
        try:
            row = conn.execute(
                "SELECT value FROM config_kv WHERE key = 'decision_catalog_sync'",
            ).fetchone()
            if row is not None and (_time.time() - float(row["value"])) < 86400:
                return {"status": "success", "message": "Catalog is fresh.", "models": 0}
        except Exception:
            pass
    finally:
        conn.close()

    try:
        resp = requests.get(
            "https://models.dev/api.json?type=decision",
            headers={"User-Agent": "synapseForge/1.0"},
            timeout=30,
        )
        resp.raise_for_status()
        catalog = resp.json()
    except Exception as e:
        log_error(str(e), source="decision_catalog.py:sync_catalog(fetch)")
        return {"status": "error", "message": f"Could not fetch models.dev: {e}"}

    now = datetime.now().isoformat()
    rows: list[dict[str, Any]] = []
    try:
        for provider_id, provider_data in (catalog or {}).items():
            if not isinstance(provider_data, dict):
                continue
            provider_api = provider_data.get("api")
            provider_npm = provider_data.get("npm")
            for model_id, model_data in (provider_data.get("models") or {}).items():
                if not isinstance(model_data, dict):
                    continue
                limit = model_data.get("limit") or {}
                cost = model_data.get("cost") or {}
                modalities = model_data.get("modalities") or {}
                reasoning_opts = model_data.get("reasoning_options") or []
                rows.append({
                    "provider": str(provider_id).strip().lower(),
                    "model_id": str(model_id),
                    "type": model_data.get("type") or "decision",
                    "name": model_data.get("name"),
                    "description": model_data.get("description"),
                    "family": model_data.get("family"),
                    "context_window": (limit or {}).get("context"),
                    "input_limit": (limit or {}).get("input"),
                    "output_limit": (limit or {}).get("output"),
                    "reasoning": 1 if model_data.get("reasoning") else 0,
                    "reasoning_options": _json.dumps(reasoning_opts) if reasoning_opts else None,
                    "tool_call": 1 if model_data.get("tool_call") else 0,
                    "attachment": 1 if model_data.get("attachment") else 0,
                    "temperature": 1 if model_data.get("temperature") else 0,
                    "structured_output": 1 if model_data.get("structured_output") else 0,
                    "modalities_input": _json.dumps(modalities.get("input")) if modalities.get("input") else None,
                    "modalities_output": _json.dumps(modalities.get("output")) if modalities.get("output") else None,
                    "cost_input": cost.get("input"),
                    "cost_output": cost.get("output"),
                    "cost_cache_read": cost.get("cache_read"),
                    "cost_cache_write": cost.get("cache_write"),
                    "open_weights": 1 if model_data.get("open_weights") else 0,
                    "status": model_data.get("status"),
                    "api": provider_api,
                    "npm": provider_npm,
                    "updated_at": now,
                })
    except Exception as e:
        log_error(str(e), source="decision_catalog.py:sync_catalog(extract)")
        return {"status": "error", "message": f"Could not parse catalog: {e}"}

    if not rows:
        return {"status": "error", "message": "No decision models in catalog."}

    conn = _connect()
    if conn is None:
        return {"status": "error", "message": "Could not open database."}
    try:
        with conn:
            conn.executemany(
                load_query("decision_catalog/upsert_model.sql"),
                rows,
            )
            conn.execute(
                "INSERT INTO config_kv (key, value) VALUES ('decision_catalog_sync', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(_time.time()),),
            )
        return {"status": "success", "models": len(rows)}
    except Exception as e:
        log_error(str(e), source="decision_catalog.py:sync_catalog(insert)")
        return {"status": "error", "message": f"Database error: {e}"}
    finally:
        conn.close()


def get_models(provider: str) -> list[str]:
    """Return the decision model IDs for a provider from the catalog.

    Args:
        provider: Provider id (e.g. ``"openrouter"``).

    Returns:
        Sorted list of model ID strings. Empty if not found.
    """
    conn = _connect()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            load_query("decision_catalog/list_models_by_provider.sql"),
            (provider.strip(),),
        ).fetchall()
        return [row["model_id"] for row in rows]
    except Exception as e:
        log_error(str(e), source="decision_catalog.py:get_models")
        return []
    finally:
        conn.close()


def get_api(provider: str) -> str | None:
    """Return the stored API base URL for a decision provider.

    Args:
        provider: Provider id (e.g. ``"nano-gpt"``).

    Returns:
        The ``api`` value from the catalog, or ``None`` when unknown.
    """
    conn = _connect()
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT api FROM decision_catalog WHERE provider = ? AND api IS NOT NULL LIMIT 1",
            (provider.strip().lower(),),
        ).fetchone()
        return str(row["api"]) if row and row["api"] else None
    except Exception as e:
        log_error(str(e), source="decision_catalog.py:get_api")
        return None
    finally:
        conn.close()


def get_model(provider: str, model_id: str) -> dict[str, Any] | None:
    """Return full details for a specific decision model from the catalog.

    Args:
        provider: Provider id.
        model_id: Model ID.

    Returns:
        Dict with all model fields, or ``None`` if not found.
    """
    conn = _connect()
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT * FROM decision_catalog WHERE provider = ? AND model_id = ?",
            (provider.strip().lower(), model_id),
        ).fetchone()
        return dict(row) if row is not None else None
    except Exception as e:
        log_error(str(e), source="decision_catalog.py:get_model")
        return None
    finally:
        conn.close()


def list_providers() -> list[str]:
    """Return the provider ids that have decision models in the catalog.

    Returns:
        Sorted list of provider id strings. Empty on failure.
    """
    conn = _connect()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            load_query("decision_catalog/list_providers.sql"),
        ).fetchall()
        return [row["provider"] for row in rows]
    except Exception as e:
        log_error(str(e), source="decision_catalog.py:list_providers")
        return []
    finally:
        conn.close()
