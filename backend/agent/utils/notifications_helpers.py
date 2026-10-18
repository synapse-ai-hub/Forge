"""Persisted notifications of workflow runs and scheduled-task executions.

One table (``notifications``) holds both kinds. Exactly one of
``workflow_name`` / ``task_id`` is set (FK to the PK of each table). A new
notification is also pushed to the web UI through the event bus
(``notification`` event) so the header bell updates live.

All functions never raise and log failures. Timestamps are local time.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from backend.agent.utils.db import db_transaction, get_connection
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.queries import load_query

logger = logging.getLogger(__name__)


def _row_to_dict(row) -> dict[str, Any]:
    """Convert a ``notifications`` row into the public dict."""
    return {
        "id": row["id"],
        "kind": row["kind"],
        "workflow_name": row["workflow_name"],
        "task_id": row["task_id"],
        "run_id": row["run_id"],
        "title": row["title"],
        "status": row["status"],
        "message": row["message"] or "",
        "session_id": row["session_id"],
        "read": bool(row["read"]),
        "created_at": row["created_at"],
    }


def list_notifications() -> list[dict[str, Any]]:
    """Return every notification, newest first."""
    try:
        with get_connection() as conn:
            rows = conn.execute(load_query("notifications/list.sql")).fetchall()
            return [_row_to_dict(r) for r in rows]
    except Exception as exc:
        log_error(str(exc), source="notifications_helpers.py:list_notifications")
        return []


def get_notification(notification_id: int) -> dict[str, Any] | None:
    """Return one notification, or ``None`` when it does not exist."""
    try:
        with get_connection() as conn:
            row = conn.execute(load_query("notifications/get.sql"), (notification_id,)).fetchone()
            return _row_to_dict(row) if row else None
    except Exception as exc:
        log_error(str(exc), source="notifications_helpers.py:get_notification")
        return None


def add_notification(
    kind: str,
    title: str,
    status: str,
    message: str,
    run_id: str | None = None,
    session_id: str | None = None,
    workflow_name: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any] | None:
    """Persist a notification.

    Args:
        kind: ``"workflow"`` or ``"task"``.
        title: Workflow name or task name shown in the bell.
        status: ``"success"`` or ``"error"``.
        message: Plain-language result or explanation for the user.
        run_id: ``workflow_runs.id`` or ``task_runs.id`` (as text).
        session_id: Session holding the execution, to open it.
        workflow_name: FK to ``workflows.name`` (workflow kind only).
        task_id: FK to ``scheduled_tasks.id`` (task kind only).

    Returns:
        The stored notification, or ``None`` when it could not be stored.
    """
    try:
        now = datetime.now().isoformat()
        with db_transaction() as conn:
            cur = conn.execute(
                load_query("notifications/insert.sql"),
                (kind, workflow_name, task_id, run_id, title, status, message, session_id, now),
            )
            new_id = cur.lastrowid
        return get_notification(new_id)
    except Exception as exc:
        log_error(str(exc), source="notifications_helpers.py:add_notification")
        return None


async def notify(**kwargs: Any) -> dict[str, Any] | None:
    """Persist a notification and push it to the web UI.

    Takes the same keyword arguments as :func:`add_notification`.

    Returns:
        The stored notification, or ``None`` when it could not be stored.
    """
    stored = add_notification(**kwargs)
    if stored is None:
        return None
    try:
        from backend.event_bus import event_bus

        await event_bus.emit({"type": "notification", "content": stored})
    except Exception as exc:
        log_error(str(exc), source="notifications_helpers.py:notify(emit)")
        logger.warning("No se pudo emitir la notificación: %s", exc)
    return stored


def mark_all_read() -> bool:
    """Mark every notification as read. Returns ``True`` on success."""
    try:
        with db_transaction() as conn:
            conn.execute(load_query("notifications/mark_all_read.sql"))
        return True
    except Exception as exc:
        log_error(str(exc), source="notifications_helpers.py:mark_all_read")
        return False


def delete_notification(notification_id: int) -> bool:
    """Delete one notification. Returns ``True`` when a row was removed."""
    try:
        with db_transaction() as conn:
            cur = conn.execute(load_query("notifications/delete_one.sql"), (notification_id,))
            return (cur.rowcount or 0) > 0
    except Exception as exc:
        log_error(str(exc), source="notifications_helpers.py:delete_notification")
        return False


def clear_notifications() -> bool:
    """Delete every notification. Returns ``True`` on success."""
    try:
        with db_transaction() as conn:
            conn.execute(load_query("notifications/delete_all.sql"))
        return True
    except Exception as exc:
        log_error(str(exc), source="notifications_helpers.py:clear_notifications")
        return False


def delete_task_notifications(task_id: str) -> None:
    """Remove the notifications of a deleted scheduled task."""
    try:
        with db_transaction() as conn:
            conn.execute(load_query("notifications/delete_by_task.sql"), (task_id,))
    except Exception as exc:
        log_error(str(exc), source="notifications_helpers.py:delete_task_notifications")
