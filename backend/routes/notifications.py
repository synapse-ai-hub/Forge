"""Endpoints of the persisted notifications (header bell)."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.agent.utils import notifications_helpers as notifications_db
from backend.agent.utils import workflow_db
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notifications"])


@router.get("/notifications")
async def get_notifications() -> JSONResponse:
    """List every notification, newest first.

    Returns:
        JSON response with the notifications.
    """
    return JSONResponse(
        status_code=200,
        content={"status": "success", "notifications": notifications_db.list_notifications()},
    )


@router.post("/notifications/read")
async def read_notifications() -> JSONResponse:
    """Mark every notification as read (the user opened the bell).

    Returns:
        JSON response with the result.
    """
    if not notifications_db.mark_all_read():
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "No se pudieron marcar las notificaciones."},
        )
    return JSONResponse(status_code=200, content={"status": "success"})


def _full_output(notification: dict) -> str:
    """Get the complete result (or the failure explanation) behind a notification.

    The notification keeps a short text. The run keeps its whole result in
    ``workflow_runs`` (the answer of the run, or the explanation of its failure).

    Args:
        notification: Notification dict.

    Returns:
        The complete output, or the short text of the notification when it cannot be found.
    """
    try:
        if notification.get("run_id"):
            run = workflow_db.get_run(notification["run_id"]) or {}
            text = run.get("result") if run.get("status") == "success" else run.get("error_text")
            if text:
                return str(text)
    except Exception as exc:
        log_error(str(exc), source="backend/routes/notifications.py:_full_output")
    return notification.get("message") or ""


@router.get("/notifications/{notification_id}/detail")
async def notification_detail(notification_id: int) -> JSONResponse:
    """Return a notification with its complete output (what the modal shows).

    Args:
        notification_id: Notification id.

    Returns:
        JSON response with the notification and its output, or 404 when it does not exist.
    """
    notification = notifications_db.get_notification(notification_id)
    if notification is None:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "La notificación no existe."},
        )
    return JSONResponse(
        status_code=200,
        content={"status": "success", "notification": notification, "output": _full_output(notification)},
    )


@router.post("/notifications/{notification_id}/review")
async def review_notification(notification_id: int) -> JSONResponse:
    """Open a new conversation that already holds the output ("review with the agent").

    It is the only place where a workflow or a scheduled task leads to a session:
    the runs themselves never open one.

    Args:
        notification_id: Notification id.

    Returns:
        JSON response with the id of the new session, or 404 when the notification does not exist.
    """
    notification = notifications_db.get_notification(notification_id)
    if notification is None:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "La notificación no existe."},
        )
    try:
        from backend.instances import session_manager

        title = notification["title"]
        session_id = uuid.uuid4().hex
        created = session_manager.create_session(
            session_id, metadata={"source": "review", "notification_id": notification_id}
        )
        if created.get("status") != "success":
            raise RuntimeError(str(created.get("message")))
        session_manager.update_session_title(session_id, f"Revisión: {title}")
        session_manager.save_message(
            session_id, "user", content=f"Revisión de «{title}».", turn_number=1, step=None,
        )
        session_manager.save_message(
            session_id, "assistant", content=_full_output(notification),
            turn_number=1, step=1, status="success", message="",
        )
        return JSONResponse(status_code=200, content={"status": "success", "session_id": session_id})
    except Exception as exc:
        log_error(str(exc), source="backend/routes/notifications.py:review")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "No se pudo abrir la revisión con el agente."},
        )


@router.delete("/notifications/{notification_id}")
async def delete_notification(notification_id: int) -> JSONResponse:
    """Delete one notification.

    Args:
        notification_id: Notification id.

    Returns:
        JSON response with the result, or 404 when it does not exist.
    """
    if not notifications_db.delete_notification(notification_id):
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "La notificación no existe."},
        )
    return JSONResponse(status_code=200, content={"status": "success"})


@router.delete("/notifications")
async def clear_notifications() -> JSONResponse:
    """Delete every notification ("Clear").

    Returns:
        JSON response with the result.
    """
    if not notifications_db.clear_notifications():
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "No se pudieron limpiar las notificaciones."},
        )
    return JSONResponse(status_code=200, content={"status": "success"})
