"""Thumbs up / down on assistant answers.

An answer is identified by ``(session_id, turn_number)``: the same id the
history endpoint gives it (``turn-N``). The feedback lives in ``agent.db``
(``message_feedback``) and is local to the installation.

Endpoints:
- ``GET /api/feedback/{session_id}`` — Feedback of every answer of a session.
- ``PUT /api/feedback/{session_id}/{turn_number}`` — Save or change the feedback.
- ``DELETE /api/feedback/{session_id}/{turn_number}`` — Remove the feedback.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body

from backend.agent.utils.contract import (
    make_error_response,
    make_success_response,
    validate_response,
    zero_usage,
)
from backend.agent.utils.db import db_transaction
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.queries import load_query
from backend.instances import session_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"])

_FEEDBACK_TYPES = ("up", "down")


def _session_exists(session_id: str) -> bool:
    """Check that a session exists.

    Args:
        session_id: Session identifier.

    Returns:
        ``True`` when the session exists.
    """
    with db_transaction() as conn:
        return conn.execute(load_query("sessions/exists.sql"), (session_id,)).fetchone() is not None


@router.get("/feedback/{session_id}")
async def get_session_feedback(session_id: str) -> dict:
    """Return the feedback of every answer of a session.

    Args:
        session_id: Session identifier.

    Returns:
        A contract response whose ``data`` maps ``turn_number`` to ``"up"`` or ``"down"``.
    """
    try:
        with db_transaction() as conn:
            rows = conn.execute(load_query("feedback/list_for_session.sql"), (session_id,)).fetchall()
        return validate_response(
            make_success_response(
                message="Feedback obtenido",
                data={str(row["turn_number"]): row["feedback_type"] for row in rows},
                usage=zero_usage(),
            )
        )
    except Exception as exc:
        log_error(str(exc), source="feedback.py:get_session_feedback")
        logger.exception("Error loading feedback of session %s: %s", session_id, exc)
        return make_error_response(message="Error al obtener el feedback")


@router.put("/feedback/{session_id}/{turn_number}")
async def set_feedback(session_id: str, turn_number: int, data: dict[str, Any] = Body(...)) -> dict:
    """Save the feedback of an answer, or change it if it already has one.

    Args:
        session_id: Session of the answer.
        turn_number: Turn of the answer.
        data: Body ``{"feedback_type": "up" | "down"}``.

    Returns:
        A contract response indicating success or failure.
    """
    feedback_type = data.get("feedback_type")
    if feedback_type not in _FEEDBACK_TYPES:
        return make_error_response(message="feedback_type debe ser 'up' o 'down'")
    try:
        if not _session_exists(session_id):
            return make_error_response(message="Sesión no encontrada")
        answer = session_manager.get_last_assistant_message(session_id, turn_number)
        if answer is None:
            return make_error_response(message="Respuesta no encontrada")
        now = datetime.now().isoformat()
        with db_transaction() as conn:
            conn.execute(
                load_query("feedback/upsert.sql"),
                (session_id, turn_number, feedback_type, answer.get("model"), answer.get("provider"), now, now),
            )
        return validate_response(
            make_success_response(message="Feedback guardado", usage=zero_usage())
        )
    except Exception as exc:
        log_error(str(exc), source="feedback.py:set_feedback")
        logger.exception("Error saving feedback of %s/%s: %s", session_id, turn_number, exc)
        return make_error_response(message="Error al guardar el feedback")


@router.delete("/feedback/{session_id}/{turn_number}")
async def delete_feedback(session_id: str, turn_number: int) -> dict:
    """Remove the feedback of an answer (nothing happens if it has none).

    Args:
        session_id: Session identifier.
        turn_number: Turn of the answer.

    Returns:
        A contract response indicating success or failure.
    """
    try:
        with db_transaction() as conn:
            conn.execute(load_query("feedback/delete.sql"), (session_id, turn_number))
        return validate_response(
            make_success_response(message="Feedback eliminado", usage=zero_usage())
        )
    except Exception as exc:
        log_error(str(exc), source="feedback.py:delete_feedback")
        logger.exception("Error deleting feedback of %s/%s: %s", session_id, turn_number, exc)
        return make_error_response(message="Error al eliminar el feedback")
