"""Workflow run endpoints: list, play, cancel and history.

Thin HTTP layer over :mod:`backend.agent.utils.workflow_service`. The play
button starts the run in the background and the result arrives as a
notification.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.agent.utils import workflow_db
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.workflow_service import workflow_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["workflows"])

_STATUS_BY_CODE = {
    "not_found": 404,
    "invalid": 400,
    "missing_refs": 400,
    "conflict": 409,
    "error": 500,
}


def _public_run(run: dict | None) -> dict | None:
    """Return the fields of a run the UI needs."""
    if not run:
        return None
    return {
        "id": run["id"],
        "workflow_name": run["workflow_name"],
        "session_id": run.get("session_id"),
        "source": run.get("source"),
        "status": run["status"],
        "attempt": run.get("attempt"),
        "started_at": run["started_at"],
        "finished_at": run.get("finished_at"),
        "result": run.get("result"),
        "error_text": run.get("error_text"),
    }


@router.get("/workflows")
async def list_workflows_with_state() -> JSONResponse:
    """List every workflow with its running state and its latest run."""
    try:
        from backend.agent.utils.workflows_helpers import _listar_workflows_locales

        last_runs = workflow_db.list_last_runs()
        items = []
        for entry in _listar_workflows_locales():
            name = entry["name"]
            active_id = workflow_service.active_run_id(name)
            items.append({
                "name": name,
                "description": entry.get("description", ""),
                "running": active_id is not None,
                "run_id": active_id,
                "last_run": _public_run(last_runs.get(name)),
            })
        return JSONResponse(status_code=200, content={"status": "success", "workflows": items})
    except Exception as exc:
        log_error(str(exc), source="backend/routes/workflows.py:list")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "No se pudieron listar los workflows."},
        )


@router.post("/workflows/{name}/run")
async def run_workflow(name: str) -> JSONResponse:
    """Start a run of a workflow in the background (the play button)."""
    try:
        started = await workflow_service.start_run(name, source="play")
        if not started.get("ok"):
            return JSONResponse(
                status_code=_STATUS_BY_CODE.get(started.get("code", "error"), 500),
                content={"status": "error", "message": started.get("message", "")},
            )
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": f"Workflow «{name}» en ejecución.",
                "data": {"run_id": started["run_id"], "session_id": started["session_id"]},
            },
        )
    except Exception as exc:
        log_error(str(exc), source="backend/routes/workflows.py:run")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "No se pudo ejecutar el workflow."},
        )


@router.post("/workflows/runs/{run_id}/cancel")
async def cancel_workflow_run(run_id: str) -> JSONResponse:
    """Cancel a running run (persisted as ``cancelled``)."""
    try:
        if not await workflow_service.cancel(run_id):
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "La ejecución no está en curso."},
            )
        return JSONResponse(
            status_code=200,
            content={"status": "success", "message": "Ejecución cancelada."},
        )
    except Exception as exc:
        log_error(str(exc), source="backend/routes/workflows.py:cancel")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "No se pudo cancelar la ejecución."},
        )


@router.get("/workflows/runs")
async def list_workflow_runs(name: str | None = None, limit: int = 50) -> JSONResponse:
    """Return the most recent runs, newest first (optionally of one workflow)."""
    runs = [_public_run(r) for r in workflow_db.list_runs(name, max(1, min(limit, 200)))]
    return JSONResponse(status_code=200, content={"status": "success", "runs": runs})
