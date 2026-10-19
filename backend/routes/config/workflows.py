"""Workflow endpoints: validate, save and generate."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.instances import agent, session_manager
from backend.agent.utils.error_logger import log_error

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/workflows/validate")
async def validate_workflow_endpoint(payload: dict[str, Any]) -> JSONResponse:
    """Dry-run validation of a workflow YAML without writing anything."""
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
    """Validate and save a workflow YAML as workflows/<name>.yaml (flat file)."""
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

@router.post("/workflows/generate")
async def generate_workflow_endpoint(payload: dict[str, Any]) -> JSONResponse:
    """Generate a workflow YAML with the agent from a description.

    The agent follows latency, cost and efficiency rules. The result is
    validated before returning. Nothing is written to disk.
    """
    try:
        import json as _json
        import re as _re
        import uuid as _uuid

        description = str((payload or {}).get("description", "")).strip()
        if not description:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Campo 'description' requerido."},
            )
        from backend.agent.loop import AgentLoop

        try:
            system_prompt = agent.prompt("generate_workflow")
        except FileNotFoundError:
            logger.exception("Prompt generate_workflow.md no encontrado.")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "No se pudo iniciar la generación."},
            )
        transient_id = f"workflow-generate:{_uuid.uuid4().hex[:8]}"
        try:
            create_res = session_manager.create_session(transient_id)
            if create_res.get("status") != "success":
                raise RuntimeError("transient session")
        except Exception as exc:
            log_error(str(exc), source="backend/routes/config.py:generate_workflow")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "No se pudo iniciar la generación."},
            )
        loop = AgentLoop(agent=agent, session_manager=session_manager)
        collected = ""
        try:
            async for sse in loop.run(
                session_id=transient_id,
                user_message=f"Descripción del workflow: {description}",
                system_prompt=system_prompt,
            ):
                if sse.strip() == "data: [DONE]":
                    break
                if sse.startswith("data: "):
                    try:
                        event = _json.loads(sse[len("data: "):].strip())
                    except (ValueError, TypeError):
                        continue
                    if event.get("type") == "chunk":
                        collected += event.get("content", "")
        except Exception as exc:
            log_error(str(exc), source="backend/routes/config.py:generate_workflow")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "El agente no pudo generar el workflow."},
            )
        match = _re.search(r"```yaml\s*(.*?)```", collected, _re.DOTALL)
        raw = match.group(1).strip() if match else collected.strip()
        if not raw:
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "El agente no devolvió YAML."},
            )
        import yaml as _yaml

        from backend.agent.utils.workflow_validator import validate_workflow

        try:
            data = _yaml.safe_load(raw)
        except Exception as exc:
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": f"El agente devolvió YAML inválido: {exc}", "data": {"yaml": raw}},
            )
        result = validate_workflow(data if isinstance(data, dict) else {})
        if result.get("status") != "success":
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": result.get("message", "YAML inválido."), "data": {"yaml": raw}},
            )
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Workflow generado.",
                "data": {"yaml": raw, "name": result["data"].get("name", "")},
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "total_time": 0},
            },
        )
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py:generate_workflow")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Error generando workflow."},
        )
