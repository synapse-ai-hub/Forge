"""Endpoint POST /api/create/workflow — crear workflows deterministas."""

from __future__ import annotations

import logging
import os
import re
import sys
from typing import Any, AsyncGenerator

from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Ensure project root for absolute imports
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(_current_dir)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.utils.config_dir import get_workflows_dir
from backend.agent.utils.workflows_helpers import (
    _listar_workflows_locales,
    _evaluar_si_existe as _evaluar_si_existe_workflow,
    _workflow_dir_path,
)
from backend.agent.utils.create_helpers import (
    stream_tool_calling_loop,
    stream_interview_loop,
    resolve_create_model_provider,
)
from backend.instances import agent
from backend.agent.utils.error_logger import log_error
from backend.routes.create.common import (
    _AGENT_TOOLS_PERMS,
    _formatear_mensajes,
    _sse,
    _try_parse_json,
    router,
)

logger = logging.getLogger(__name__)

_WORKFLOWS_DIR = get_workflows_dir()

_FRIENDLY_ERROR_WORKFLOW = "No se pudo crear el workflow. Ocurrió un error durante el proceso. Verificá la configuración e intentá de nuevo."


def _validar_nombre_workflow(name: str | None) -> str | None:
    """Validate a workflow name against the validator regex.

    Args:
        name: Raw workflow name from user or LLM.

    Returns:
        The stripped name if valid, else ``None``.
    """
    try:
        if not isinstance(name, str):
            return None
        clean = name.strip()
        if not re.match(r"^[a-z0-9][a-z0-9_-]*$", clean or ""):
            return None
        if ".." in clean or "/" in clean or "\\" in clean:
            return None
        return clean
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════
# POST /api/create/workflow — crear workflows deterministas
# ═══════════════════════════════════════════════════════════════════════


class CreateWorkflowRequest(BaseModel):
    """Request para crear un workflow con iteración."""

    descripcion: str
    name: str | None = None
    mensajes: list[dict] | None = None
    model: str | None = None
    provider: str | None = None
    iterate: bool = False


_WORKFLOW_INTERVIEW_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "responder_interview_workflow",
        "description": (
            "Llamar cuando tengas suficiente información para crear el workflow "
            "o cuando necesites hacer una pregunta al usuario."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["question", "create"],
                    "description": (
                        "'question' cuando necesitás más información. "
                        "'create' cuando ya tenés suficiente para diseñar el workflow."
                    ),
                },
                "question": {
                    "type": "string",
                    "description": "Tu pregunta para el usuario (solo si action='question').",
                },
                "task": {
                    "type": "string",
                    "description": "Descripción detallada del workflow (solo si action='create').",
                },
                "name": {
                    "type": "string",
                    "description": "Nombre en minúsculas con guiones (solo si action='create').",
                },
            },
            "required": ["action"],
        },
    },
}


@router.post("/workflow")
async def post_create_workflow_stream(req: CreateWorkflowRequest):
    """Streaming endpoint to create a workflow via an LLM interview.

    Same contract as ``POST /api/create/skill`` but emits ``workflow_action``
    and ``workflow_result_final`` events.

    Returns:
        A StreamingResponse with SSE events.
    """
    descripcion = (req.descripcion or "").strip()
    nombre = req.name.strip() if req.name else None
    mensajes = req.mensajes or []

    if not descripcion:
        return StreamingResponse(
            iter([_sse({"type": "error", "content": "El campo 'descripcion' es obligatorio."})]),
            media_type="text/event-stream",
        )

    async def event_stream() -> AsyncGenerator[str, None]:
        """Generate SSE events for the workflow creation flow."""
        try:
            _create_model, _create_provider = resolve_create_model_provider(req.model, req.provider)
        except Exception as exc:
            log_error(str(exc), source="create.py:workflow(resolve)")
            yield _sse({"type": "error", "content": _FRIENDLY_ERROR_WORKFLOW})
            return

        if req.iterate:
            yield _sse({"type": "workflow_action", "content": {"action": "iterating"}})
            try:
                iter_template = agent.prompt("iterate_workflow")
            except FileNotFoundError:
                logger.exception("Prompt iterate_workflow.md no encontrado.")
                yield _sse({"type": "error", "content": _FRIENDLY_ERROR_WORKFLOW})
                return
            valid_iter_name = _validar_nombre_workflow(nombre)
            if nombre and not valid_iter_name:
                yield _sse({"type": "error", "content": "Nombre inválido. Minúsculas, números, guiones."})
                return
            try:
                workflow_carpeta = str(_workflow_dir_path(valid_iter_name or "workflow"))
                iter_prompt = iter_template.format(
                    nombre=valid_iter_name or "(inferir)",
                    carpeta=workflow_carpeta,
                    conversacion=_formatear_mensajes(mensajes),
                )
            except Exception as exc:
                log_error(str(exc), source="create.py:workflow(iterate_format)")
                yield _sse({"type": "error", "content": _FRIENDLY_ERROR_WORKFLOW})
                return
            try:
                tools = list(agent.tools.tools_registry(_AGENT_TOOLS_PERMS))
            except Exception as exc:
                logger.exception("Error obteniendo tools: %s", exc)
                yield _sse({"type": "error", "content": _FRIENDLY_ERROR_WORKFLOW})
                return
            msgs: list[dict[str, Any]] = [
                {"role": "system", "content": iter_prompt},
                {"role": "user", "content": mensajes[-1]["content"] if mensajes else "Modificá el workflow."},
            ]
            async for event in stream_tool_calling_loop(
                msgs, tools, _FRIENDLY_ERROR_WORKFLOW, model=_create_model, provider=_create_provider
            ):
                yield _sse(event)
                if event["type"] == "error":
                    return
            try:
                from backend.agent.utils.workflow_validator import validate_workflow as _validate_iter
                import yaml as _yaml_iter

                iter_ok = False
                iter_error = "El workflow modificado no valida."
                if valid_iter_name:
                    try:
                        cand = _workflow_dir_path(valid_iter_name) / "workflow.yaml"
                        if cand.is_file():
                            data = _yaml_iter.safe_load(cand.read_text(encoding="utf-8"))
                            res = _validate_iter(data if isinstance(data, dict) else {})
                            if res.get("status") == "success":
                                iter_ok = True
                            else:
                                iter_error = str(res.get("message", iter_error))
                        else:
                            iter_error = f"Workflow '{valid_iter_name}' no tiene workflow.yaml."
                    except Exception as exc:
                        log_error(str(exc), source="create.py:workflow(iterate_validate)")
                        iter_error = str(exc)
                if not iter_ok:
                    yield _sse({"type": "error", "content": iter_error})
                    return
            except Exception as exc:
                log_error(str(exc), source="create.py:workflow(iterate_validate)")
                yield _sse({"type": "error", "content": _FRIENDLY_ERROR_WORKFLOW})
                return
            yield _sse({"type": "workflow_result_final", "content": {
                "status": "success",
                "message": f"Workflow '{valid_iter_name}' modificado exitosamente.",
                "data": {"exist": "Sí", "workflow": valid_iter_name, "workflow_path": workflow_carpeta},
            }})
            return

        try:
            _WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
            workflows_locales = _listar_workflows_locales()
            decision = await _evaluar_si_existe_workflow(descripcion, workflows_locales, req.model, req.provider)
            if decision and decision.get("exist") == "Sí":
                wf_name = decision.get("workflow")
                yield _sse({"type": "workflow_result_final", "content": {
                    "status": "success",
                    "message": f"Ya existe el workflow '{wf_name}' que cubre esta tarea.",
                    "data": {"exist": "Sí", "workflow": wf_name},
                }})
                return
        except Exception as exc:
            logger.exception("Error en evaluación inicial: %s", exc)

        try:
            template = agent.prompt("interview_workflow")
        except FileNotFoundError:
            logger.exception("Prompt interview_workflow.md no encontrado.")
            yield _sse({"type": "error", "content": _FRIENDLY_ERROR_WORKFLOW})
            return

        try:
            prompt = template.format(
                descripcion=descripcion,
                nombre=nombre or "(inferir)",
                mensajes=_formatear_mensajes(mensajes),
            )
        except Exception as exc:
            log_error(str(exc), source="create.py:workflow(interview_format)")
            yield _sse({"type": "error", "content": _FRIENDLY_ERROR_WORKFLOW})
            return

        collected_content = ""
        tool_calls_data = None

        async for event in stream_interview_loop(
            prompt=prompt,
            interview_tool=_WORKFLOW_INTERVIEW_TOOL,
            friendly_error=_FRIENDLY_ERROR_WORKFLOW,
            model=_create_model,
            provider=_create_provider,
        ):
            if event["type"] == "chunk":
                collected_content += event.get("content", "")
                yield _sse(event)
            elif event["type"] == "_interview_args":
                tool_calls_data = event.get("content") or {}
            elif event["type"] == "aborted":
                yield _sse(event)
                return
            else:
                yield _sse(event)

        if not tool_calls_data:
            parsed = _try_parse_json(collected_content)
            if parsed:
                tool_calls_data = parsed
            elif collected_content.strip():
                return
            else:
                yield _sse({"type": "error", "content": "El LLM no devolvió una respuesta válida."})
                return

        action = tool_calls_data.get("action")
        if action == "question":
            yield _sse({"type": "workflow_action", "content": {
                "action": "question", "question": tool_calls_data.get("question", ""),
            }})
            return
        if action != "create":
            logger.warning("Acción desconocida del LLM: %s", action)
            yield _sse({"type": "error", "content": _FRIENDLY_ERROR_WORKFLOW})
            return

        task = tool_calls_data.get("task", descripcion)
        raw_name = nombre or tool_calls_data.get("name")
        name = _validar_nombre_workflow(raw_name)
        if raw_name and not name:
            yield _sse({"type": "error", "content": "Nombre inválido. Minúsculas, números, guiones."})
            return

        yield _sse({"type": "workflow_action", "content": {"action": "creating"}})

        try:
            sys_prompt_template = agent.prompt("create_workflow")
        except FileNotFoundError:
            logger.exception("Prompt create_workflow.md no encontrado.")
            yield _sse({"type": "error", "content": _FRIENDLY_ERROR_WORKFLOW})
            return

        try:
            conversacion = _formatear_mensajes(mensajes) if mensajes else f"**Usuario**: {task}"
            carpeta = str(_workflow_dir_path(name or "workflow"))
            sys_prompt = sys_prompt_template.format(
                nombre=name or "(inferir del contexto)",
                descripcion=task,
                conversacion=conversacion,
                carpeta=carpeta,
            )
        except Exception as exc:
            log_error(str(exc), source="create.py:workflow(create_format)")
            yield _sse({"type": "error", "content": _FRIENDLY_ERROR_WORKFLOW})
            return

        user_msg = "Creá el workflow. Pasos OBLIGATORIOS en orden: 1) Creá la carpeta. 2) Escribí workflow.yaml con write. 3) Validá el YAML. 4) Cuando valide, pedime aprobación."

        try:
            tools = list(agent.tools.tools_registry(_AGENT_TOOLS_PERMS))
        except Exception as exc:
            logger.exception("Error obteniendo tools: %s", exc)
            yield _sse({"type": "error", "content": _FRIENDLY_ERROR_WORKFLOW})
            return

        msgs_create: list[dict[str, Any]] = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_msg},
        ]

        async for event in stream_tool_calling_loop(
            msgs_create, tools, _FRIENDLY_ERROR_WORKFLOW, model=_create_model, provider=_create_provider
        ):
            yield _sse(event)
            if event["type"] == "error":
                return

        try:
            from backend.agent.utils.workflow_validator import validate_workflow
            import time as _time
            import yaml as _yaml

            def _try_validate_dir(dir_name: str) -> tuple[str | None, str | None, str | None]:
                """Validate one workflow dir, returning (name, path, error)."""
                try:
                    candidate = _workflow_dir_path(dir_name) / "workflow.yaml"
                except ValueError as exc:
                    return None, None, str(exc)
                try:
                    if not candidate.is_file():
                        return None, None, f"Workflow '{dir_name}' no tiene workflow.yaml."
                    data = _yaml.safe_load(candidate.read_text(encoding="utf-8"))
                    result = validate_workflow(data if isinstance(data, dict) else {})
                    if result.get("status") == "success":
                        return dir_name, str(candidate), None
                    return None, None, str(result.get("message", "Workflow inválido."))
                except Exception as exc:
                    log_error(str(exc), source="create.py:workflow(validate)")
                    return None, None, str(exc)

            found_name = None
            found_path = None
            last_error = "El agente no generó un workflow válido."
            if name:
                ok_name, ok_path, err = _try_validate_dir(name)
                if ok_name:
                    found_name, found_path = ok_name, ok_path
                elif err:
                    last_error = err
            if not found_name and _WORKFLOWS_DIR.is_dir():
                try:
                    cutoff = _time.time() - 300
                    for entry in _WORKFLOWS_DIR.iterdir():
                        try:
                            if not entry.is_dir() or entry.name.startswith("."):
                                continue
                            if name and entry.name == name:
                                continue
                            try:
                                if entry.stat().st_mtime < cutoff:
                                    continue
                            except Exception:
                                continue
                            ok_name, ok_path, err = _try_validate_dir(entry.name)
                            if ok_name:
                                found_name, found_path = ok_name, ok_path
                                break
                            elif err:
                                last_error = err
                        except Exception:
                            continue
                except Exception as exc:
                    log_error(str(exc), source="create.py:workflow(scan)")
        except Exception as exc:
            log_error(str(exc), source="create.py:workflow(search)")
            found_name = None
            found_path = None
            last_error = "Error buscando el workflow creado."

        if not found_name or not found_path:
            yield _sse({"type": "error", "content": last_error})
            return
        yield _sse({"type": "workflow_result_final", "content": {
            "status": "success",
            "message": f"Workflow '{found_name}' creado exitosamente.",
            "data": {"exist": "No", "workflow": found_name, "workflow_path": found_path},
        }})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
