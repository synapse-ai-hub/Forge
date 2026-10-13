"""Decision model catalog — curated System One models in SQLite.

models.dev does not catalog our decision providers (``openrouter`` and
``typesafe`` are absent from ``api.json?type=decision``, verified), so
there is no catalog sync here. The ``decision_catalog`` table holds the
verified decision model ids per provider, seeded from the curated list in
``provider_keys.DECISION_PROVIDERS``. The dropdowns (``GET
/config/models/decision``) read from this table, so adding a model is a
seed change, not a code change anywhere else.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
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


def ensure_seeded() -> dict:
    """Insert the curated decision models if missing (idempotent).

    Returns:
        ``{"status": "success", "models": count}`` or
        ``{"status": "error", "message": ...}``.
    """
    try:
        from backend.agent.utils import provider_keys
    except Exception as e:
        log_error(str(e), source="decision_catalog.py:ensure_seeded(import)")
        return {"status": "error", "message": f"Could not load providers: {e}"}

    now = datetime.now(timezone.utc).isoformat()
    costs: dict[str, dict[str, float | None]] = {
        # Verified costs (input/output USD per 1M tokens).
        "inception/mercury-decide:free": {"input": 0.0, "output": 0.0},
        "jev-latest": {"input": 0.042, "output": 0.0},
    }
    rows: list[dict[str, Any]] = []
    for pid, info in (provider_keys.DECISION_PROVIDERS or {}).items():
        for model_id in info.get("models") or []:
            cost = costs.get(str(model_id), {"input": None, "output": None})
            rows.append({
                "provider": pid,
                "model_id": model_id,
                "type": "decision",
                "name": None,
                "description": None,
                "family": None,
                "context_window": None,
                "input_limit": None,
                "output_limit": None,
                "reasoning": 0,
                "reasoning_options": None,
                "tool_call": 0,
                "attachment": 0,
                "temperature": 0,
                "structured_output": 0,
                "modalities_input": None,
                "modalities_output": None,
                "cost_input": cost["input"],
                "cost_output": cost["output"],
                "cost_cache_read": None,
                "cost_cache_write": None,
                "open_weights": 0,
                "status": None,
                "api": None,
                "npm": None,
                "updated_at": now,
            })
    if not rows:
        return {"status": "error", "message": "No curated decision models."}

    conn = _connect()
    if conn is None:
        return {"status": "error", "message": "Could not open database."}
    try:
        with conn:
            conn.executemany(
                load_query("decision_catalog/upsert_model.sql"),
                rows,
            )
        return {"status": "success", "models": len(rows)}
    except Exception as e:
        log_error(str(e), source="decision_catalog.py:ensure_seeded(insert)")
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
