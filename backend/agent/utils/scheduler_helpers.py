"""Scheduler (agenda): the workflows that have a ``schedule`` block, and the clock that starts them.

A scheduled task is a workflow whose YAML has a ``schedule`` block (see
:func:`~backend.agent.utils.workflow_validator.normalize_schedule`). It is run by the
workflow engine like any other workflow, so its runs, steps, spend, judge and
notifications are the ones of :mod:`backend.agent.utils.workflow_service`; the only
difference is ``source = "schedule"``. A task can also be played by hand.

This module has two parts:

- The view of the scheduled workflows the routes and Telegram use (``list_tasks``,
  ``get_task``, ``update_task``, ``delete_task``, ``list_runs``).
- :class:`SchedulerService`, the loop started from the application lifespan: every
  :data:`CHECK_INTERVAL_SECONDS` it looks for the slots that match the current minute
  and starts the run of their workflow.

Timezone: the system local time is used directly (no configuration).
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.agent.utils import workflow_db, workflow_loader
from backend.agent.utils.db import get_connection
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.queries import load_query
from backend.agent.utils.workflow_loader import list_scheduled, save_schedule
from backend.agent.utils.workflow_validator import normalize_schedule

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 20
"""How often the loop checks for due tasks (must stay below one minute)."""

_EDIT_UNAVAILABLE = (
    "El nombre, la descripción, los permisos y los parámetros de una tarea programada "
    "se cambian en su workflow, no desde la agenda."
)


def _slugify(text: str) -> str:
    """Convert arbitrary text into a lowercase slug suitable for a workflow name.

    Keeps only ``[a-z0-9]``, replacing spaces and special characters with
    hyphens.  Leading/trailing hyphens are stripped.  Falls back to a
    UUID fragment when the input produces nothing usable.

    Args:
        text: Text to convert.

    Returns:
        The slug.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug if slug else uuid.uuid4().hex[:8]


def _task_view(item: dict[str, Any]) -> dict[str, Any]:
    """Describe a scheduled workflow as the task the agenda shows.

    Args:
        item: Scheduled workflow from :func:`~backend.agent.utils.workflow_loader.list_scheduled`.

    Returns:
        The task: the first slot is the main time, the others are the repetitions.
    """
    name = item["name"]
    slots = item["schedule"]["slots"]
    try:
        stamp = datetime.fromtimestamp((workflow_loader.get_workflows_dir() / f"{name}.yaml").stat().st_mtime).isoformat()
    except OSError:
        stamp = ""
    return {
        "id": name,
        "name": name,
        "prompt": item.get("description", ""),
        "time": slots[0]["time"],
        "days": slots[0]["days"],
        "enabled": bool(item["schedule"]["enabled"]),
        "repetitions": slots[1:],
        "created_at": stamp,
        "updated_at": stamp,
    }


def list_tasks() -> list[dict[str, Any]]:
    """Return the scheduled tasks (workflows with a schedule) sorted by time.

    Returns:
        List of task dicts (possibly empty on error).
    """
    try:
        return sorted(
            (_task_view(item) for item in list_scheduled()),
            key=lambda task: (task["time"], task["name"]),
        )
    except Exception as exc:
        log_error(str(exc), source="backend/agent/utils/scheduler_helpers.py:list_tasks")
        logger.warning("Failed to list scheduled tasks: %s", exc)
        return []


def get_task(task_id: str) -> dict[str, Any] | None:
    """Fetch a single scheduled task.

    Args:
        task_id: Task identifier (the name of its workflow).

    Returns:
        The task, or ``None`` if it does not exist.
    """
    for task in list_tasks():
        if task["id"] == task_id:
            return task
    return None


def get_task_by_name(name: str) -> dict[str, Any] | None:
    """Fetch a scheduled task by the name of its workflow.

    Args:
        name: Workflow name.

    Returns:
        The task, or ``None`` if the workflow has no schedule.
    """
    return get_task(name)


def update_task(
    task_id: str,
    name: str | None = None,
    prompt: str | None = None,
    time_str: str | None = None,
    days: list[int] | None = None,
    enabled: bool | None = None,
    tool_permissions: dict[str, Any] | None = None,
    skill_permissions: dict[str, Any] | None = None,
    parameters: dict[str, Any] | None = None,
    repetitions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Update the schedule of a task (its ``schedule`` block is written in the workflow YAML).

    Args:
        task_id: Task identifier (the name of its workflow).
        name: Not editable here.
        prompt: Not editable here.
        time_str: New main time in ``HH:MM``.
        days: New main weekdays, 0=Sunday .. 6=Saturday.
        enabled: Pause (``False``) or resume (``True``) the task.
        tool_permissions: Not editable here.
        skill_permissions: Not editable here.
        parameters: Not editable here.
        repetitions: New additional slots; replaces the current ones.

    Returns:
        Contract-style dict with ``status``, ``message`` and, on success, ``task``.
    """
    if any(value is not None for value in (name, prompt, tool_permissions, skill_permissions, parameters)):
        return {"status": "error", "message": _EDIT_UNAVAILABLE}
    task = get_task(task_id)
    if task is None:
        return {"status": "error", "message": "La tarea no existe."}
    slots = [{
        "time": time_str if time_str is not None else task["time"],
        "days": days if days is not None else task["days"],
    }]
    slots += repetitions if repetitions is not None else task["repetitions"]
    schedule, error = normalize_schedule({
        "enabled": enabled if enabled is not None else task["enabled"],
        "slots": slots,
    })
    if error or schedule is None:
        return {"status": "error", "message": error or "Horario inválido."}
    saved = save_schedule(task["name"], schedule)
    if saved["status"] != "success":
        return saved
    return {"status": "success", "message": "Tarea actualizada.", "task": get_task(task_id)}


def delete_task(task_id: str) -> dict[str, str]:
    """Delete a scheduled task: its workflow YAML and its runs, commits and notifications.

    Args:
        task_id: Task identifier (the name of its workflow).

    Returns:
        Contract-style dict with ``status`` and ``message``.
    """
    from backend.agent.utils.workflow_service import workflow_service

    task = get_task(task_id)
    if task is None:
        return {"status": "error", "message": "La tarea no existe."}
    if workflow_service.is_running(task["name"]):
        return {"status": "error", "message": "La tarea se está ejecutando. Cancelala antes de eliminarla."}
    try:
        path = Path(workflow_loader.get_workflows_dir()) / f"{task['name']}.yaml"
        path.unlink(missing_ok=True)
        if not workflow_db.delete_workflow(task["name"]):
            raise RuntimeError("No se pudieron borrar los registros de la tarea.")
        return {"status": "success", "message": "Tarea eliminada."}
    except Exception as exc:
        log_error(str(exc), source="backend/agent/utils/scheduler_helpers.py:delete_task")
        logger.warning("Failed to delete scheduled task %s: %s", task_id, exc)
        return {"status": "error", "message": "No se pudo eliminar la tarea."}


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent runs started by the scheduler (newest first).

    Args:
        limit: Maximum number of runs to return.

    Returns:
        List of run dicts (``id``, ``task_id``, ``name``, ``prompt``,
        ``status``, ``detail``, ``started_at``, ``finished_at``), possibly empty.
    """
    try:
        with get_connection() as conn:
            rows = conn.execute(load_query("scheduler/list_runs.sql"), (int(limit),)).fetchall()
            return [dict(row) for row in rows]
    except Exception as exc:
        log_error(str(exc), source="backend/agent/utils/scheduler_helpers.py:list_runs")
        logger.warning("Failed to list scheduled runs: %s", exc)
        return []


class SchedulerService:
    """Async loop that looks for due slots and starts the run of their workflow."""

    def __init__(self) -> None:
        """Create the service with no loop running."""
        self._task: asyncio.Task | None = None
        self._running = False
        self._attempted: set[tuple[str, str]] = set()

    async def start(self) -> None:
        """Start the background check loop (idempotent)."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Scheduler service started.")

    async def stop(self) -> None:
        """Stop the background loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Scheduler service stopped.")

    async def _loop(self) -> None:
        """Periodically check the schedules and start the runs that are due."""
        while self._running:
            try:
                await self._check_due_tasks()
            except Exception as exc:
                log_error(str(exc), source="backend/agent/utils/scheduler_helpers.py:_loop")
                logger.warning("Scheduler loop error: %s", exc)
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

    async def _check_due_tasks(self) -> None:
        """Start the run of every enabled workflow with a slot that matches the current minute.

        A slot is due when its time is the current minute and today is one of its days.
        A workflow already has its run for that minute when ``workflow_runs`` holds a
        scheduled run that started in it, so a slot never starts twice. A start that
        fails (missing resources, workflow already running) is tried once per minute.
        """
        from backend.agent.utils.workflow_service import workflow_service

        now = datetime.now()
        minute = now.strftime("%Y-%m-%dT%H:%M")
        current_time = now.strftime("%H:%M")
        # JS-style weekday (0=Sunday .. 6=Saturday) to match the UI convention.
        js_weekday = (now.weekday() + 1) % 7
        self._attempted = {key for key in self._attempted if key[1] == minute}

        for item in list_scheduled():
            schedule = item["schedule"]
            if not schedule["enabled"]:
                continue
            name = item["name"]
            due = any(
                slot["time"] == current_time and js_weekday in slot["days"]
                for slot in schedule["slots"]
            )
            if not due or (name, minute) in self._attempted:
                continue
            self._attempted.add((name, minute))
            if workflow_db.scheduled_run_exists(name, minute):
                continue
            logger.info("Starting scheduled workflow: %s", name)
            started = await workflow_service.start_run(name, source="schedule")
            if not started.get("ok"):
                message = str(started.get("message") or "No se pudo iniciar la tarea programada.")
                log_error(message, source="backend/agent/utils/scheduler_helpers.py:_check_due_tasks")
                logger.warning("Scheduled workflow %s not started: %s", name, message)


# Module-level singleton used by the lifespan and the routes.
scheduler_service = SchedulerService()
