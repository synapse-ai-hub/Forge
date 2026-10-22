"""Workflow endpoints: list, play, cancel, delete and run history.

Thin HTTP layer over :mod:`backend.agent.utils.workflow_service`. The play
button starts the run in the background and the result arrives as a
notification.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.agent.utils import workflow_db
from backend.agent.utils.config_dir import get_workflows_dir
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.workflow_service import workflow_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["workflows"])

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

_STATUS_BY_CODE = {
    "not_found": 404,
    "invalid": 400,
    "missing_refs": 400,
    "conflict": 409,
    "error": 500,
}


def _public_run(run: dict | None) -> dict | None:
    """Pick the fields of a run the UI needs.

    Args:
        run: The run row, or ``None``.

    Returns:
        The public fields, or ``None`` when there is no run.
    """
    if not run:
        return None
    return {
        "id": run["id"],
        "workflow_name": run["workflow_name"],
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
    """List every workflow with its running state and its latest run.

    Returns:
        JSON response with the workflows.
    """
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
    """Start a run of a workflow in the background (the play button).

    Args:
        name: Workflow name.

    Returns:
        JSON response with the run id, or the reason it could not start.
    """
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
                "data": {"run_id": started["run_id"]},
            },
        )
    except Exception as exc:
        log_error(str(exc), source="backend/routes/workflows.py:run")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "No se pudo ejecutar el workflow."},
        )


@router.delete("/workflows/{name}")
async def delete_workflow(name: str) -> JSONResponse:
    """Delete a workflow: its YAML, its runs, commits, spend and notifications.

    Args:
        name: Workflow name.

    Returns:
        JSON response with the result.
    """
    if not _NAME_RE.match(name):
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Nombre de workflow inválido."},
        )
    path = get_workflows_dir() / f"{name}.yaml"
    if not path.is_file():
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": f"Workflow '{name}' no encontrado."},
        )
    if workflow_service.is_running(name):
        return JSONResponse(
            status_code=409,
            content={"status": "error", "message": "El workflow se está ejecutando. Cancelalo antes de eliminarlo."},
        )
    try:
        path.unlink()
        if not workflow_db.delete_workflow(name):
            raise RuntimeError("No se pudieron borrar los registros del workflow.")
        return JSONResponse(
            status_code=200,
            content={"status": "success", "message": f"Workflow '{name}' eliminado."},
        )
    except Exception as exc:
        log_error(str(exc), source="backend/routes/workflows.py:delete")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"No se pudo eliminar el workflow '{name}'."},
        )


@router.post("/workflows/runs/{run_id}/cancel")
async def cancel_workflow_run(run_id: str) -> JSONResponse:
    """Cancel a running run (persisted as ``cancelled``).

    Args:
        run_id: Run identifier.

    Returns:
        JSON response with the result, or 404 when the run is not in progress.
    """
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
    """List the most recent runs, newest first (optionally of one workflow).

    Args:
        name: Restrict to one workflow, or ``None`` for all.
        limit: Maximum number of runs (1..200).

    Returns:
        JSON response with the runs.
    """
    runs = [_public_run(r) for r in workflow_db.list_runs(name, max(1, min(limit, 200)))]
    return JSONResponse(status_code=200, content={"status": "success", "runs": runs})
