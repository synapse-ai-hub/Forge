"""Endpoints of the persisted notifications (header bell)."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.agent.utils import notifications_helpers as notifications_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notifications"])


@router.get("/notifications")
async def get_notifications() -> JSONResponse:
    """Return every notification, newest first."""
    return JSONResponse(
        status_code=200,
        content={"status": "success", "notifications": notifications_db.list_notifications()},
    )


@router.post("/notifications/read")
async def read_notifications() -> JSONResponse:
    """Mark every notification as read (the user opened the bell)."""
    if not notifications_db.mark_all_read():
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "No se pudieron marcar las notificaciones."},
        )
    return JSONResponse(status_code=200, content={"status": "success"})


@router.delete("/notifications/{notification_id}")
async def delete_notification(notification_id: int) -> JSONResponse:
    """Delete one notification."""
    if not notifications_db.delete_notification(notification_id):
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "La notificación no existe."},
        )
    return JSONResponse(status_code=200, content={"status": "success"})


@router.delete("/notifications")
async def clear_notifications() -> JSONResponse:
    """Delete every notification ("Limpiar")."""
    if not notifications_db.clear_notifications():
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "No se pudieron limpiar las notificaciones."},
        )
    return JSONResponse(status_code=200, content={"status": "success"})
