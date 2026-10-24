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

from backend.agent.utils.config_dir import get_workflow_prompts_dir, get_workflows_dir, get_workspace_dir
from backend.agent.utils.workflow_validator import normalize_schedule
from backend.agent.utils.workflows_helpers import (
    _listar_workflows_locales,
    _evaluar_si_existe as _evaluar_si_existe_workflow,
    _workflow_file_path,
)
from backend.agent.utils.create_helpers import (
    build_resource_context,
    stream_tool_calling_loop,
    stream_interview_loop,
    resolve_create_model_provider,
)
from backend.instances import agent
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.create_review import is_creation_complete
from backend.agent.utils.creators import track_creator_run
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
    """Request to create a workflow with iteration."""

    descripcion: str
    name: str | None = None
    mensajes: list[dict] | None = None
    model: str | None = None
    provider: str | None = None
    iterate: bool = False
    creator_id: str | None = None
    agentes: list[str] | None = None
    tools: list[str] | None = None
    rag: list[str] | None = None
    tool_args: dict[str, dict[str, Any]] | None = None
    """Arguments the user filled for the tools they picked."""
    schedule: dict[str, Any] | None = None
    """Schedule of a scheduled task (``{"enabled", "slots"}``); the workflow is created with this block."""


_MAX_CORRECTIONS = 2
"""Times the creator gets back what the system found wrong in the workflow, to fix it."""


def _problemas_del_workflow(path: str) -> list[str]:
    """Check a workflow file against the rules and the system (agents, tools, their arguments, collections).

    Args:
        path: Path of the workflow YAML.

    Returns:
        The rule it breaks, or one text per resource that does not match; empty when the
        workflow is valid and matches what exists.
    """
    import yaml as _yaml_check

    from backend.agent.utils.workflow_validator import validate_workflow
    from backend.agent.utils.workflows_helpers import verificar_refs

    with open(path, encoding="utf-8") as handle:
        data = _yaml_check.safe_load(handle.read())
    data = data if isinstance(data, dict) else {}
    result = validate_workflow(data)
    if result.get("status") != "success":
        return [str(result.get("message") or "Workflow inválido.")]
    refs = verificar_refs(data)
    return [str(f.get("detalle", "")) for f in refs.get("faltantes", []) or [] if isinstance(f, dict)]


def _yaml_schedule(schedule: dict[str, Any] | None) -> str:
    """Render a schedule as the YAML block the creator has to write.

    Args:
        schedule: Validated schedule (``{"enabled", "slots"}``), or ``None``.

    Returns:
        The ``schedule:`` block as YAML text, or an empty string without schedule.
    """
    if not schedule:
        return ""
    import yaml as _yaml_schedule

    return _yaml_schedule.safe_dump({"schedule": schedule}, allow_unicode=True, sort_keys=False).strip()


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
async def post_create_workflow_stream(req: CreateWorkflowRequest) -> StreamingResponse:
    """Stream the creation of a workflow via an LLM interview.

    Same contract as ``POST /api/create/skill`` but emits ``workflow_action``
    and ``workflow_result_final`` events.

    Args:
        req: The creation request.

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
        """Generate SSE events for the workflow creation flow.

        Yields:
            SSE ``data:`` lines.
        """
        try:
            _create_model, _create_provider = resolve_create_model_provider(req.model, req.provider)
        except Exception as exc:
            log_error(str(exc), source="create.py:workflow(resolve)")
            yield _sse({"type": "error", "content": _FRIENDLY_ERROR_WORKFLOW})
            return

        recursos = await build_resource_context(
            agentes=req.agentes, tools=req.tools, tool_args=req.tool_args, rag=req.rag
        )
        # Absolute paths: the creator writes the files there (a "~" is resolved by guessing).
        carpetas = {
            "carpeta_workflows": _WORKFLOWS_DIR.as_posix(),
            "carpeta_prompts": get_workflow_prompts_dir().as_posix(),
            "carpeta_workspace": get_workspace_dir().as_posix(),
        }

        if req.iterate:
            yield _sse({"type": "workflow_action", "content": {"action": "iterating"}})
            valid_iter_name = _validar_nombre_workflow(nombre)
            if nombre and not valid_iter_name:
                yield _sse({"type": "error", "content": "Nombre inválido. Minúsculas, números, guiones."})
                return
            try:
                workflow_archivo = str(_workflow_file_path(valid_iter_name or "workflow"))
                iter_prompt = agent.prompt(
                    "iterate_workflow",
                    nombre=valid_iter_name or "(inferir)",
                    archivo=workflow_archivo,
                    conversacion=_formatear_mensajes(mensajes),
                    **carpetas,
                    **recursos,
                )
            except FileNotFoundError:
                logger.exception("Prompt iterate_workflow.jinja no encontrado.")
                yield _sse({"type": "error", "content": _FRIENDLY_ERROR_WORKFLOW})
                return
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
            touched = False
            async for event in stream_tool_calling_loop(
                msgs, tools, _FRIENDLY_ERROR_WORKFLOW, model=_create_model, provider=_create_provider
            ):
                yield _sse(event)
                if event["type"] == "error":
                    return
                if event["type"] == "tool_call" and (event.get("content") or {}).get("name") in ("write", "edit"):
                    touched = True
            try:
                from backend.agent.utils.workflow_validator import validate_workflow as _validate_iter
                import yaml as _yaml_iter

                iter_ok = False
                iter_error = "El workflow modificado no valida."
                if valid_iter_name:
                    try:
                        cand = _workflow_file_path(valid_iter_name)
                        if cand.is_file():
                            data = _yaml_iter.safe_load(cand.read_text(encoding="utf-8"))
                            res = _validate_iter(data if isinstance(data, dict) else {})
                            if res.get("status") == "success":
                                iter_ok = True
                            else:
                                iter_error = str(res.get("message", iter_error))
                        else:
                            iter_error = f"Workflow '{valid_iter_name}' no tiene archivo {cand.name}."
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
            complete = await is_creation_complete(
                kind="workflow",
                nombre=valid_iter_name,
                artifact_path=_workflow_file_path(valid_iter_name or "workflow"),
                mensajes=mensajes,
                model=_create_model,
                provider=_create_provider,
                turn_number=len(mensajes),
            )
            if complete:
                message = (
                    f"Workflow '{valid_iter_name}' modificado exitosamente."
                    if touched
                    else f"Consulta sobre el workflow '{valid_iter_name}' respondida."
                )
                yield _sse({"type": "workflow_result_final", "content": {
                    "status": "success",
                    "message": message,
                    "data": {"exist": "Sí", "workflow": valid_iter_name, "workflow_path": workflow_archivo},
                }})
            return

        schedule: dict[str, Any] | None = None
        if req.schedule is not None:
            schedule, schedule_error = normalize_schedule(req.schedule)
            if schedule is None:
                yield _sse({"type": "error", "content": schedule_error or "Horario inválido."})
                return
            if not _validar_nombre_workflow(nombre):
                yield _sse({"type": "error", "content": "El nombre de la tarea es obligatorio (minúsculas, números, guiones)."})
                return
            if _workflow_file_path(str(nombre)).is_file():
                yield _sse({"type": "error", "content": f"Ya existe un workflow con el nombre '{nombre}'. Elegí otro nombre."})
                return

        if schedule is None:
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
                try:
                    prompt = agent.prompt(
                        "interview_workflow",
                        descripcion=descripcion,
                        nombre=nombre or "(inferir)",
                        mensajes=_formatear_mensajes(mensajes),
                        **carpetas,
                        **recursos,
                    )
                except FileNotFoundError:
                    logger.exception("Prompt interview_workflow.jinja no encontrado.")
                    yield _sse({"type": "error", "content": _FRIENDLY_ERROR_WORKFLOW})
                    return
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

        else:
            # A scheduled task comes with everything the form asks: no interview.
            task = descripcion
            name = _validar_nombre_workflow(nombre)

        yield _sse({"type": "workflow_action", "content": {"action": "creating"}})

        try:
            conversacion = _formatear_mensajes(mensajes) if mensajes else f"**Usuario**: {task}"
            archivo = str(_workflow_file_path(name or "workflow"))
            try:
                sys_prompt = agent.prompt(
                    "create_workflow",
                    nombre=name or "(inferir del contexto)",
                    descripcion=task,
                    conversacion=conversacion,
                    archivo=archivo,
                    programada=schedule is not None,
                    horarios=_yaml_schedule(schedule),
                    **carpetas,
                    **recursos,
                )
            except FileNotFoundError:
                logger.exception("Prompt create_workflow.jinja no encontrado.")
                yield _sse({"type": "error", "content": _FRIENDLY_ERROR_WORKFLOW})
                return
        except Exception as exc:
            log_error(str(exc), source="create.py:workflow(create_format)")
            yield _sse({"type": "error", "content": _FRIENDLY_ERROR_WORKFLOW})
            return

        user_msg = "Creá el workflow. Pasos OBLIGATORIOS en orden: 1) Escribí el archivo <nombre>.yaml con write en la carpeta de workflows. 2) Validá el YAML. 3) Cuando valide, pedime aprobación. Cada nodo agent lleva su prompt en un toml dentro de workflows/prompts/, referenciado con prompt_file."
        if schedule is not None:
            user_msg = (
                "Creá la tarea programada. Pasos OBLIGATORIOS en orden: 1) Escribí el archivo <nombre>.yaml con write "
                "en la carpeta de workflows, con el bloque schedule indicado. 2) Validá el YAML. 3) Cuando valide, "
                "terminá sin pedir aprobación. Cada nodo agent lleva su prompt en un toml dentro de workflows/prompts/, "
                "referenciado con prompt_file."
            )

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

        from backend.agent.utils.workflow_validator import validate_workflow
        import time as _time
        import yaml as _yaml

        def _find_created() -> tuple[str | None, str | None, str]:
            """Find the workflow the creator wrote and validate it.

            Returns:
                ``(name, path, error)``: the name and path of the valid workflow, or ``None`` and
                ``None`` with the reason (the rule the file breaks) when there is none.
            """
            try:
                def _try_validate_file(file_name: str) -> tuple[str | None, str | None, str | None]:
                    """Validate one flat workflow file.

                    Args:
                        file_name: Name of the file in the workflows directory.

                    Returns:
                        ``(name, path, error)``; ``error`` is ``None`` when the workflow is valid.
                    """
                    try:
                        candidate = _workflow_file_path(file_name)
                    except ValueError as exc:
                        return None, None, str(exc)
                    try:
                        if not candidate.is_file():
                            return None, None, f"Workflow '{file_name}' no tiene archivo {candidate.name}."
                        data = _yaml.safe_load(candidate.read_text(encoding="utf-8"))
                        result = validate_workflow(data if isinstance(data, dict) else {})
                        if result.get("status") == "success":
                            return file_name, str(candidate), None
                        return None, None, str(result.get("message", "Workflow inválido."))
                    except Exception as exc:
                        log_error(str(exc), source="create.py:workflow(validate)")
                        return None, None, str(exc)

                found_name = None
                found_path = None
                last_error = "El agente no generó un workflow válido."
                if name:
                    ok_name, ok_path, err = _try_validate_file(name)
                    if ok_name:
                        found_name, found_path = ok_name, ok_path
                    elif err:
                        last_error = err
                if not found_name and _WORKFLOWS_DIR.is_dir():
                    try:
                        cutoff = _time.time() - 300
                        for entry in _WORKFLOWS_DIR.iterdir():
                            try:
                                if not entry.is_file() or entry.suffix != ".yaml":
                                    continue
                                if entry.name.startswith("."):
                                    continue
                                if name and entry.stem == name:
                                    continue
                                try:
                                    if entry.stat().st_mtime < cutoff:
                                        continue
                                except Exception:
                                    continue
                                ok_name, ok_path, err = _try_validate_file(entry.stem)
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
                return None, None, "Error buscando el workflow creado."
            return found_name, found_path, last_error

        # What breaks the rules of a workflow goes back to the creator to fix it.
        found_name, found_path, last_error = _find_created()
        for _round in range(_MAX_CORRECTIONS):
            if found_name and found_path:
                break
            yield _sse({"type": "chunk", "content": f"Corrigiendo: {last_error}"})
            msgs_create.append({"role": "user", "content": agent.prompt("correct_workflow", problemas=[last_error])})
            async for event in stream_tool_calling_loop(
                msgs_create, tools, _FRIENDLY_ERROR_WORKFLOW, model=_create_model, provider=_create_provider
            ):
                yield _sse(event)
                if event["type"] == "error":
                    return
            found_name, found_path, last_error = _find_created()
        if not found_name or not found_path:
            yield _sse({"type": "error", "content": last_error})
            return
        if schedule is not None:
            from backend.agent.utils.workflow_loader import load_workflow as _load_scheduled
            from backend.agent.utils.workflow_loader import save_schedule as _save_schedule

            if found_name != name:
                yield _sse({"type": "error", "content": f"El creador no escribió el archivo {name}.yaml."})
                return
            loaded = _load_scheduled(found_name)
            if loaded.get("status") != "success" or loaded["data"].get("schedule") != schedule:
                log_error(
                    f"La tarea '{found_name}' se creó sin el horario pedido; se escribe el del formulario.",
                    source="create.py:workflow(schedule)",
                )
                saved = _save_schedule(found_name, schedule)
                if saved.get("status") != "success":
                    yield _sse({"type": "error", "content": str(saved.get("message"))})
                    return
            # Nobody approves a scheduled task: what does not match the system (an argument a tool
            # does not have, an agent that does not exist, or a rule a fix broke) goes back to the
            # creator to fix it.
            for _round in range(_MAX_CORRECTIONS + 1):
                problems = _problemas_del_workflow(found_path)
                if not problems:
                    break
                if _round == _MAX_CORRECTIONS:
                    yield _sse({"type": "error", "content": "La tarea quedó con problemas: " + "; ".join(problems)})
                    return
                yield _sse({"type": "chunk", "content": "Corrigiendo: " + "; ".join(problems)})
                msgs_create.append({"role": "user", "content": agent.prompt("correct_workflow", problemas=problems)})
                async for event in stream_tool_calling_loop(
                    msgs_create, tools, _FRIENDLY_ERROR_WORKFLOW, model=_create_model, provider=_create_provider
                ):
                    yield _sse(event)
                    if event["type"] == "error":
                        return
        try:
            import yaml as _yaml_refs

            from backend.agent.utils.workflows_helpers import verificar_refs as _verificar_refs_wf

            with open(found_path, encoding="utf-8") as _fh:
                _wf_data = _yaml_refs.safe_load(_fh.read())
            _refs = _verificar_refs_wf(_wf_data if isinstance(_wf_data, dict) else {})
            _falt = _refs.get("faltantes", []) or []
            if _falt:
                _det = "; ".join(str(f.get("detalle", "")) for f in _falt if isinstance(f, dict))
                yield _sse({"type": "chunk", "content": f"Advertencia: {_det} Crealos para que el workflow pueda ejecutarse."})
        except Exception as exc:
            log_error(str(exc), source="create.py:workflow(verificar_refs)")
        yield _sse({"type": "workflow_result_final", "content": {
            "status": "success",
            "message": (
                f"Tarea programada '{found_name}' creada exitosamente."
                if schedule is not None
                else f"Workflow '{found_name}' creado exitosamente."
            ),
            "data": {"exist": "No", "workflow": found_name, "workflow_path": found_path},
        }})

    return StreamingResponse(
        track_creator_run("workflow", req, event_stream()),
        media_type="text/event-stream",
    )


async def create_scheduled_task(req: CreateWorkflowRequest) -> dict[str, str]:
    """Create a scheduled task and wait for the result (used by Telegram).

    Runs the same creation as ``POST /api/create/workflow`` with a schedule and reads its
    stream until the final event.

    Args:
        req: The creation request; ``schedule`` and ``name`` are required.

    Returns:
        ``{"status": "success" | "error", "message": ...}`` with the final message of the creator.
    """
    import json

    final = {"status": "error", "message": _FRIENDLY_ERROR_WORKFLOW}
    response = await post_create_workflow_stream(req)
    async for chunk in response.body_iterator:
        text = chunk.decode("utf-8") if isinstance(chunk, (bytes, bytearray)) else str(chunk)
        for line in text.splitlines():
            if not line.startswith("data: "):
                continue
            try:
                payload = json.loads(line[len("data: "):])
            except ValueError:
                continue
            if payload.get("type") == "workflow_result_final":
                content = payload.get("content") or {}
                final = {"status": str(content.get("status", "error")), "message": str(content.get("message", ""))}
            elif payload.get("type") == "error":
                final = {"status": "error", "message": str(payload.get("content", ""))}
    return final
