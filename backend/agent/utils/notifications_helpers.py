"""Persisted notifications of workflow runs (played by the user or started by the scheduler).

One table (``notifications``) holds them; ``kind`` tells whether the run was played
(``workflow``) or started by the scheduler (``schedule``). A new notification is also
pushed to the web UI through the event bus (``notification`` event) so the header bell
updates live.

All functions never raise and log failures. Timestamps are local time.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from backend.agent.utils.db import db_transaction, get_connection
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.queries import load_query

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3

logger = logging.getLogger(__name__)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a ``notifications`` row into the public dict.

    Args:
        row: Row of the ``notifications`` table.

    Returns:
        The notification as a dict.
    """
    return {
        "id": row["id"],
        "kind": row["kind"],
        "workflow_name": row["workflow_name"],
        "run_id": row["run_id"],
        "title": row["title"],
        "status": row["status"],
        "message": row["message"] or "",
        "read": bool(row["read"]),
        "created_at": row["created_at"],
    }


def list_notifications() -> list[dict[str, Any]]:
    """List every notification, newest first.

    Returns:
        One dict per notification.
    """
    try:
        with get_connection() as conn:
            rows = conn.execute(load_query("notifications/list.sql")).fetchall()
            return [_row_to_dict(r) for r in rows]
    except Exception as exc:
        log_error(str(exc), source="notifications_helpers.py:list_notifications")
        return []


def get_notification(notification_id: int) -> dict[str, Any] | None:
    """Fetch one notification.

    Args:
        notification_id: Notification id.

    Returns:
        The notification, or ``None`` when it does not exist.
    """
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
    workflow_name: str | None = None,
) -> dict[str, Any] | None:
    """Persist a notification.

    Args:
        kind: ``"workflow"`` (played by the user) or ``"schedule"`` (started by the scheduler).
        title: Workflow name shown in the bell.
        status: ``"success"`` or ``"error"``.
        message: Plain-language result or explanation for the user.
        run_id: ``workflow_runs.run_id`` of the run.
        workflow_name: FK to ``workflows.name``; the notification is not stored without it.

    Returns:
        The stored notification, or ``None`` when it could not be stored.
    """
    try:
        now = datetime.now().isoformat()
        with db_transaction() as conn:
            cur = conn.execute(
                load_query("notifications/insert.sql"),
                (kind, workflow_name, run_id, title, status, message, now),
            )
            new_id = cur.lastrowid
        return get_notification(new_id)
    except Exception as exc:
        log_error(str(exc), source="notifications_helpers.py:add_notification")
        return None


async def notify(**kwargs: Any) -> dict[str, Any] | None:
    """Persist a notification and push it to the web UI.

    Args:
        **kwargs: Same keyword arguments as :func:`add_notification`.

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
    """Mark every notification as read.

    Returns:
        ``True`` on success.
    """
    try:
        with db_transaction() as conn:
            conn.execute(load_query("notifications/mark_all_read.sql"))
        return True
    except Exception as exc:
        log_error(str(exc), source="notifications_helpers.py:mark_all_read")
        return False


def delete_notification(notification_id: int) -> bool:
    """Delete one notification.

    Args:
        notification_id: Notification id.

    Returns:
        ``True`` when a row was removed.
    """
    try:
        with db_transaction() as conn:
            cur = conn.execute(load_query("notifications/delete_one.sql"), (notification_id,))
            return (cur.rowcount or 0) > 0
    except Exception as exc:
        log_error(str(exc), source="notifications_helpers.py:delete_notification")
        return False


def clear_notifications() -> bool:
    """Delete every notification.

    Returns:
        ``True`` on success.
    """
    try:
        with db_transaction() as conn:
            conn.execute(load_query("notifications/delete_all.sql"))
        return True
    except Exception as exc:
        log_error(str(exc), source="notifications_helpers.py:clear_notifications")
        return False


async def notify_telegram(status: str, prompt: str, detail: str, finished_local: str) -> None:
    """Send the result of a scheduled run to every allowed Telegram chat.

    Sent unconditionally (even when the bot toggle is off): the toggle only
    controls whether Telegram works as a chat channel, but scheduled-task
    notifications must always arrive.

    Args:
        status: ``"success"`` or ``"error"``.
        prompt: What the task does (the description of the workflow).
        detail: Result summary (final answer or error message).
        finished_local: Human-readable local finish timestamp.
    """
    try:
        from backend.telegram.instance import telegram_bot

        if not telegram_bot.token:
            return
        icon = "✅" if status == "success" else "❌"
        header = "Tarea programada ejecutada" if status == "success" else "Tarea programada fallida"
        lines = [
            f"{icon} {header}",
            f"Tarea: {prompt}",
            f"Fecha y hora: {finished_local}",
        ]
        if detail:
            summary = detail if len(detail) <= 500 else f"{detail[:500]}…"
            lines.append(f"Resultado: {summary}")
        text = "\n".join(lines)
        for chat_id in telegram_bot.allowed_chat_ids:
            await telegram_bot.send_message(chat_id, text)
    except Exception as exc:
        log_error(str(exc), source="notifications_helpers.py:notify_telegram")
        logger.warning("Failed to notify Telegram about a scheduled run: %s", exc)
