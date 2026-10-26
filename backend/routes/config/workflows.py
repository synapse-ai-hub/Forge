"""Workflow endpoints: validate and save."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.agent.utils.error_logger import log_error

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/workflows/validate")
async def validate_workflow_endpoint(payload: dict[str, Any]) -> JSONResponse:
    """Dry-run validation of a workflow YAML without writing anything.

    Args:
        payload: Request body with the YAML text of the workflow.

    Returns:
        A JSONResponse with the validation result.
    """
    try:
        import yaml as _yaml

        from backend.agent.utils.workflow_validator import validate_workflow

        raw = str((payload or {}).get("yaml", ""))
        if not raw.strip():
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Campo 'yaml' requerido."},
            )
        try:
            data = _yaml.safe_load(raw)
        except Exception as exc:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": f"YAML inválido: {exc}"},
            )
        result = validate_workflow(data if isinstance(data, dict) else {})
        code = 200 if result.get("status") == "success" else 400
        return JSONResponse(status_code=code, content=result)
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py:validate_workflow")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Error validando workflow."},
        )

@router.post("/workflows/save")
async def save_workflow_endpoint(payload: dict[str, Any]) -> JSONResponse:
    """Validate and save a workflow YAML as workflows/<name>.yaml (flat file).

    Args:
        payload: Request body with the YAML text of the workflow.

    Returns:
        A JSONResponse with the result.
    """
    try:
        import os as _os
        import re as _re

        import yaml as _yaml

        from backend.agent.utils.config_dir import get_workflows_dir
        from backend.agent.utils.workflow_validator import validate_workflow

        name = str((payload or {}).get("name", "")).strip()
        raw = str((payload or {}).get("yaml", ""))
        if not _re.match(r"^[a-z0-9][a-z0-9_-]*$", name or ""):
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Nombre inválido. Minúsculas, números, guiones."},
            )
        if not raw.strip():
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Campo 'yaml' requerido."},
            )
        try:
            data = _yaml.safe_load(raw)
        except Exception as exc:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": f"YAML inválido: {exc}"},
            )
        result = validate_workflow(data if isinstance(data, dict) else {})
        if result.get("status") != "success":
            return JSONResponse(status_code=400, content=result)
        if str(result["data"].get("name", "")) != name:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "El 'name' del YAML debe coincidir con el nombre."},
            )
        workflows_dir = get_workflows_dir()
        base = _os.path.realpath(workflows_dir)
        target = _os.path.realpath(workflows_dir / f"{name}.yaml")
        if not target.startswith(base + _os.sep):
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Ruta no permitida."},
            )
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(raw if raw.endswith("\n") else raw + "\n")
        from backend.agent.utils.workflow_db import ensure_workflow

        ensure_workflow(name)
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": f"Workflow '{name}' guardado.",
                "data": {"name": name},
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "total_time": 0},
            },
        )
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py:save_workflow")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Error guardando workflow."},
        )

