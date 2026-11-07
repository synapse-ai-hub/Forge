"""Persistence helpers for trigger delivery steps with resume support.

Table ``trigger_run_steps`` mirrors ``workflow_run_steps``: one row per
dispatched stage with ``state`` open, done, failed or stale. A cut delivery
resumes from its committed stages instead of running everything again.

Every function manages its own connection, never raises and logs failures
to ``error_log`` via ``log_error``. All timestamps are local time
(``datetime.now()``), never UTC.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from backend.agent.utils.db import db_transaction, get_connection
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.queries import load_query


def _now() -> str:
    """Return the current local time.

    Returns:
        The time in ISO format.
    """
    return datetime.now().isoformat()


def open_step(
    event_id: str,
    attempt: int,
    step: int,
    substep: int,
    node_id: str,
    node_type: str,
    args: dict[str, Any] | None = None,
) -> int | None:
    """Record a dispatched stage as an open commit row.

    Args:
        event_id: Delivery identifier.
        attempt: Attempt that dispatches the stage.
        step: Stage number.
        substep: Position of the stage inside its step.
        node_id: Stage id.
        node_type: ``received``, ``verified``, ``mapped``, ``launched`` or ``notified``.
        args: Arguments of the stage.

    Returns:
        The commit row id, or ``None`` when it could not be stored.
    """
    try:
        now = _now()
        with db_transaction() as conn:
            cur = conn.execute(
                load_query("trigger_steps/insert_step.sql"),
                (
                    event_id, attempt, step, substep, node_id, node_type,
                    json.dumps(args or {}, ensure_ascii=False), now, now,
                ),
            )
            return cur.lastrowid
    except Exception as exc:
        log_error(str(exc), source="trigger_steps_db.py:open_step")
        return None


def commit_step(row_id: int | None, result: str) -> None:
    """Commit the complete result of a stage (the row goes to ``done``).

    Args:
        row_id: Commit row id (``None`` is ignored).
        result: Complete output of the stage.
    """
    if row_id is None:
        return
    try:
        with db_transaction() as conn:
            conn.execute(
                load_query("trigger_steps/mark_step_done.sql"),
                (result, _now(), row_id),
            )
    except Exception as exc:
        log_error(str(exc), source="trigger_steps_db.py:commit_step")


def fail_step(row_id: int | None, error: str) -> None:
    """Mark a stage as failed with its technical error.

    Args:
        row_id: Commit row id (``None`` is ignored).
        error: Failure message.
    """
    if row_id is None:
        return
    try:
        with db_transaction() as conn:
            conn.execute(
                load_query("trigger_steps/mark_step_failed.sql"),
                (error, _now(), row_id),
            )
    except Exception as exc:
        log_error(str(exc), source="trigger_steps_db.py:fail_step")


def fail_open_steps(event_id: str, reason: str) -> None:
    """Mark the stages left in flight by a cut as failed.

    Args:
        event_id: Delivery identifier.
        reason: Failure message to store.
    """
    try:
        with db_transaction() as conn:
            conn.execute(
                load_query("trigger_steps/fail_open_steps.sql"), (reason, _now(), event_id)
            )
    except Exception as exc:
        log_error(str(exc), source="trigger_steps_db.py:fail_open_steps")


def load_done_steps(event_id: str) -> list[dict[str, Any]]:
    """List the committed stages of a delivery.

    Args:
        event_id: Delivery identifier.

    Returns:
        One dict per committed stage, in execution order.
    """
    try:
        with get_connection() as conn:
            rows = conn.execute(
                load_query("trigger_steps/list_done_steps.sql"), (event_id,)
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        log_error(str(exc), source="trigger_steps_db.py:load_done_steps")
        return []


def invalidate_steps_after(event_id: str, step: int) -> None:
    """Mark as stale the committed stages after a step (they run again).

    Args:
        event_id: Delivery identifier.
        step: Last step that stays valid.
    """
    try:
        with db_transaction() as conn:
            conn.execute(
                load_query("trigger_steps/stale_steps_after.sql"), (_now(), event_id, step)
            )
    except Exception as exc:
        log_error(str(exc), source="trigger_steps_db.py:invalidate_steps_after")


def list_steps(event_id: str) -> list[dict[str, Any]]:
    """List every stage execution of a delivery.

    Args:
        event_id: Delivery identifier.

    Returns:
        One dict per execution, in order.
    """
    try:
        with get_connection() as conn:
            rows = conn.execute(
                load_query("trigger_steps/list_steps.sql"), (event_id,)
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        log_error(str(exc), source="trigger_steps_db.py:list_steps")
        return []


def delete_run_steps(event_id: str) -> bool:
    """Delete the stage commits of a delivery that finished well.

    Nothing is left to resume, so what ended is removed.

    Args:
        event_id: Delivery identifier.

    Returns:
        ``True`` when the rows were deleted.
    """
    try:
        with db_transaction() as conn:
            conn.execute(load_query("trigger_steps/delete_run_steps.sql"), (event_id,))
        return True
    except Exception as exc:
        log_error(str(exc), source="trigger_steps_db.py:delete_run_steps")
        return False
