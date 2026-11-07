"""Notify trigger deliveries when they finish.

Builds a short summary from the delivery steps and persists it
as a notification. Every failure is logged to ``error_log``.

All functions never raise. Timestamps are local time.
"""

from __future__ import annotations

from typing import Any

from backend.agent.utils import trigger_runs_db, trigger_steps_db
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.notifications_helpers import add_notification


def build_summary(event_id: str) -> str:
    """Build a summary of a delivery from its steps.

    Args:
        event_id: Delivery identifier.

    Returns:
        A short summary with the delivery status and step count.
        It never raises.
    """
    try:
        run = trigger_runs_db.get_run(event_id)
        if run is None:
            return "Entrega no encontrada."
        status = str(run.get("status") or "unknown")
        try:
            done = trigger_steps_db.load_done_steps(event_id)
        except Exception as exc:
            log_error(str(exc), source="trigger_notify.py:build_summary")
            done = []
        try:
            steps = trigger_steps_db.list_steps(event_id)
        except Exception as exc:
            log_error(str(exc), source="trigger_notify.py:build_summary")
            steps = []
        total = len(steps) if isinstance(steps, list) else 0
        finished = len(done) if isinstance(done, list) else 0
        result = str(run.get("result") or "")
        error_text = str(run.get("error_text") or "")
        detail = error_text or result or "sin detalle"
        return f"Entrega {status}: {finished}/{total} pasos. {detail}"
    except Exception as exc:
        log_error(str(exc), source="trigger_notify.py:build_summary")
        return "No se pudo resumir la entrega."


def notify_finished(event_id: str) -> dict[str, Any] | None:
    """Persist a notification when a delivery finishes.

    Args:
        event_id: Delivery identifier.

    Returns:
        The stored notification, or ``None`` when it could not
        be stored. It never raises.
    """
    try:
        run = trigger_runs_db.get_run(event_id)
        if run is None:
            return None
        summary = build_summary(event_id)
        status = str(run.get("status") or "")
        ok = status in ("done", "notified", "success")
        workflow_name = str(run.get("workflow_name") or "")
        if not workflow_name:
            return None
        return add_notification(
            kind="webhook",
            title=workflow_name,
            status="success" if ok else "error",
            message=summary,
            run_id=str(run.get("workflow_run_id") or event_id),
            workflow_name=workflow_name,
        )
    except Exception as exc:
        log_error(str(exc), source="trigger_notify.py:notify_finished")
        return None
