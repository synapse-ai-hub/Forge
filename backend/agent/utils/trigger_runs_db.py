"""Persistence helpers for trigger deliveries with resume after crashes.

Table ``trigger_runs`` holds one row per inbound delivery with ``status``
received, verified, mapped, launched, notified or error. A backend stop
leaves rows in progress; ``resume_interrupted`` fails their open stages
and retries up to ``MAX_ATTEMPTS`` with backoff, closing as error when
attempts run out.

Every function manages its own connection, never raises and logs failures
to ``error_log`` via ``log_error``. All timestamps are local time
(``datetime.now()``), never UTC.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any

from backend.agent.utils import trigger_steps_db
from backend.agent.utils.db import db_transaction, get_connection
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.queries import load_query

MAX_ATTEMPTS = 3
"""Total attempts of a delivery (the first execution counts as one)."""


def _now() -> str:
    """Return the current local time.

    Returns:
        The time in ISO format.
    """
    return datetime.now().isoformat()


def create_run(
    trigger_slug: str,
    workflow_name: str,
    idempotency_key: str | None = None,
    payload_hash: str | None = None,
) -> str | None:
    """Open a delivery in ``received`` state.

    Args:
        trigger_slug: Trigger that received the event.
        workflow_name: Workflow mapped to the trigger.
        idempotency_key: Client key for duplicate detection.
        payload_hash: Hash of the raw body for conflict detection.

    Returns:
        The new event id, or ``None`` when it could not be stored.
    """
    event_id = uuid.uuid4().hex
    try:
        with db_transaction() as conn:
            conn.execute(
                load_query("trigger_steps/insert_run.sql"),
                (event_id, trigger_slug, workflow_name, idempotency_key, payload_hash, _now()),
            )
        return event_id
    except Exception as exc:
        log_error(str(exc), source="trigger_runs_db.py:create_run")
        return None


def get_run(event_id: str) -> dict[str, Any] | None:
    """Fetch one delivery.

    Args:
        event_id: Delivery identifier.

    Returns:
        The delivery as a dict, or ``None`` when it does not exist.
    """
    try:
        with get_connection() as conn:
            row = conn.execute(
                load_query("trigger_steps/get_run.sql"), (event_id,)
            ).fetchone()
            return dict(row) if row else None
    except Exception as exc:
        log_error(str(exc), source="trigger_runs_db.py:get_run")
        return None


def get_run_by_key(
    trigger_slug: str, idempotency_key: str
) -> dict[str, Any] | None:
    """Fetch a delivery by its idempotency key.

    Args:
        trigger_slug: Trigger identifier.
        idempotency_key: Client key for duplicate detection.

    Returns:
        The delivery as a dict, or ``None`` when it does not exist.
    """
    try:
        with get_connection() as conn:
            row = conn.execute(
                load_query("trigger_steps/get_run_by_key.sql"),
                (trigger_slug, idempotency_key),
            ).fetchone()
            return dict(row) if row else None
    except Exception as exc:
        log_error(str(exc), source="trigger_runs_db.py:get_run_by_key")
        return None


def list_runs(
    trigger_slug: str, limit: int = 50, offset: int = 0
) -> list[dict[str, Any]]:
    """List the most recent deliveries of a trigger, newest first.

    Args:
        trigger_slug: Trigger identifier.
        limit: Maximum number of deliveries.
        offset: Number of deliveries to skip.

    Returns:
        One dict per delivery.
    """
    try:
        with get_connection() as conn:
            rows = conn.execute(
                load_query("trigger_steps/list_runs.sql"),
                (trigger_slug, int(limit), int(offset)),
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        log_error(str(exc), source="trigger_runs_db.py:list_runs")
        return []


def list_running_runs() -> list[dict[str, Any]]:
    """List the deliveries still in progress.

    Returns:
        One dict per delivery.
    """
    try:
        with get_connection() as conn:
            rows = conn.execute(
                load_query("trigger_steps/list_running.sql")
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        log_error(str(exc), source="trigger_runs_db.py:list_running_runs")
        return []


def set_run_attempt(event_id: str, attempt: int) -> None:
    """Start another attempt of a delivery (it goes back to ``received``).

    Args:
        event_id: Delivery identifier.
        attempt: Attempt number (1..3).
    """
    try:
        with db_transaction() as conn:
            conn.execute(
                load_query("trigger_steps/set_run_attempt.sql"), (attempt, event_id)
            )
    except Exception as exc:
        log_error(str(exc), source="trigger_runs_db.py:set_run_attempt")


def finish_run(
    event_id: str,
    status: str,
    result: str | None = None,
    error_text: str | None = None,
    workflow_run_id: str | None = None,
) -> None:
    """Close a delivery.

    Args:
        event_id: Delivery identifier.
        status: ``notified`` or ``error``.
        result: Final answer of the delivery.
        error_text: Plain-language explanation when it failed.
        workflow_run_id: Workflow run launched, if any.
    """
    try:
        with db_transaction() as conn:
            conn.execute(
                load_query("trigger_steps/finish_run.sql"),
                (status, _now(), result, error_text, workflow_run_id, event_id),
            )
    except Exception as exc:
        log_error(str(exc), source="trigger_runs_db.py:finish_run")


def resume_interrupted() -> int:
    """Resume the deliveries a backend stop or crash left in progress.

    The stages that were in flight are marked as failed. A delivery with
    attempts left goes back to ``received`` with ``attempt + 1`` after a
    backoff; a delivery with all attempts consumed is closed as error
    with a plain-language explanation.

    Returns:
        Number of deliveries resumed.
    """
    resumed = 0
    try:
        running = list_running_runs()
    except Exception as exc:
        log_error(str(exc), source="trigger_runs_db.py:resume_interrupted")
        return 0
    for run in running:
        event_id = str(run.get("event_id") or "")
        if not event_id:
            continue
        try:
            trigger_steps_db.fail_open_steps(
                event_id, "Interrumpido por el cierre del backend."
            )
            attempt = int(run.get("attempt") or 1)
            if attempt >= MAX_ATTEMPTS:
                finish_run(
                    event_id,
                    "error",
                    error_text="La entrega se interrumpió y ya no quedaban intentos.",
                )
                continue
            time.sleep(2 ** attempt)
            set_run_attempt(event_id, attempt + 1)
            resumed += 1
        except Exception as exc:
            log_error(str(exc), source="trigger_runs_db.py:resume_interrupted")
    return resumed
