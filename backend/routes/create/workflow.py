"""Endpoint to create or modify workflows.

Runs the agent loop with the workflow creator system prompt. Every turn of
the same ``creator_id`` continues the conversation (history persists in the
``creators`` table): the first turn carries the setup form, follow-ups carry
only the user message. When the turn writes the workflow file, a terminal
``workflow_result_final`` event is appended; a turn that only asks questions
emits none.

Scheduled tasks reuse this endpoint through ``create_scheduled_task``: the
prompt carries the ``schedule`` block and the creator finishes without asking
for approval.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from backend.agent.creator_session import CreatorSessionManager
from backend.agent.utils.config_dir import get_workflow_prompts_dir, get_workflows_dir, get_workspace_dir
from backend.agent.utils.create_helpers import build_resource_context, resolve_create_model_provider
from backend.agent.utils.creators import is_valid_id
from backend.agent.utils.workflow_validator import normalize_schedule
from backend.agent.utils.workflows_helpers import _workflow_file_path
from backend.instances import agent
from backend.routes.create.common import (
    _WORKFLOWS_DIR,
    VerifyCreatorRequest,
    error_response,
    prompt_error_stream,
    router,
    stream_creator_turn,
    verify_creator_conversation,
)

logger = logging.getLogger(__name__)

creator_sessions = CreatorSessionManager(kind="workflow")
"""Persistence of the workflow creator conversations."""


class CreateWorkflowRequest(BaseModel):
    """Request to create or modify a workflow."""

    descripcion: str
    name: str | None = None
    creator_id: str | None = None
    agentes: list[str] | None = None
    tools: list[str] | None = None
    rag: list[str] | None = None
    tool_args: dict[str, dict[str, Any]] | None = None
    schedule: dict[str, Any] | None = None
    model: str | None = None
    provider: str | None = None


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


def _yaml_schedule(schedule: dict[str, Any] | None) -> str:
    """Render a schedule as the YAML block the creator has to write.

    Args:
        schedule: Validated schedule (``{"enabled", "slots"}``), or ``None``.

    Returns:
        The ``schedule:`` block as YAML text, or an empty string without schedule.
    """
    if not schedule:
        return ""
    lines = ["schedule:", "  enabled: true", "  slots:"]
    for slot in schedule.get("slots", []) or []:
        lines.append(f"    - time: \"{slot.get('time', '')}\"")
        days = slot.get("days", [])
        lines.append(f"      days: [{', '.join(str(d) for d in days)}]")
    return "\n".join(lines)


def _setup_text(req: CreateWorkflowRequest, descripcion: str) -> str:
    """Render the setup form as the head of the first user message.

    Args:
        req: The creation request.
        descripcion: What the workflow does.

    Returns:
        The setup block in plain text.
    """
    lines = [
        "Datos del formulario:",
        f"- Nombre: {(req.name or '').strip() or '(sin nombre, elegilo vos)'}",
        f"- Descripción: {descripcion}",
    ]
    if req.agentes:
        lines.append(f"- Agentes: {', '.join(req.agentes)}")
    if req.tools:
        lines.append(f"- Tools: {', '.join(req.tools)}")
    if req.tool_args:
        lines.append(f"- Argumentos de tools: {req.tool_args}")
    if req.rag:
        lines.append(f"- Colecciones RAG: {', '.join(req.rag)}")
    if req.schedule:
        lines.append("- Es una tarea programada: incluí el bloque schedule indicado y terminá sin pedir aprobación.")
    return "\n".join(lines)


@router.post("/workflow")
async def post_create_workflow_stream(req: CreateWorkflowRequest):
    """Stream one turn of the workflow creator.

    Args:
        req: The creation request (message, optional name, setup form,
            optional creator id and optional model/provider override).

    Returns:
        A ``StreamingResponse`` with the loop SSE events plus, when the
        turn touched the workflow file, a terminal ``workflow_result_final``
        event.
    """
    descripcion = (req.descripcion or "").strip()
    if not descripcion:
        return error_response("La descripción es obligatoria.")
    creator_id = req.creator_id if req.creator_id and is_valid_id(req.creator_id) else str(uuid.uuid4())
    nombre = _validar_nombre_workflow(req.name)
    if req.name and not nombre:
        return error_response("Nombre inválido. Minúsculas, números, guiones.")

    schedule = normalize_schedule(req.schedule) if req.schedule else None

    first_turn = not creator_sessions.has_rows(creator_id)
    if first_turn:
        user_message = f"{_setup_text(req, descripcion)}\n\nMensaje del usuario: {descripcion}"
        user_setup: dict | None = {
            "name": nombre,
            "descripcion": descripcion,
            "agentes": req.agentes or [],
            "tools": req.tools or [],
            "rag": req.rag or [],
            "tool_args": req.tool_args or {},
            "schedule": schedule,
        }
    else:
        user_message = descripcion
        user_setup = None

    parameters: dict | None = None
    if req.model or req.provider:
        model, provider = resolve_create_model_provider(req.model, req.provider)
        parameters = {"model": model, "provider": provider}

    try:
        recursos = await build_resource_context(
            agentes=req.agentes, tools=req.tools, tool_args=req.tool_args,
            skills=None, rag=req.rag, with_skills=False, with_mcp=False,
        )
        system_prompt = agent.prompt(
            "create_workflow",
            archivo=str(_workflow_file_path(nombre or "workflow")),
            programada=schedule is not None,
            horarios=_yaml_schedule(schedule),
            carpeta_workflows=_WORKFLOWS_DIR.as_posix(),
            carpeta_prompts=get_workflow_prompts_dir().as_posix(),
            carpeta_workspace=get_workspace_dir().as_posix(),
            **recursos,
        )
    except Exception:
        logger.exception("Prompt create_workflow.jinja no encontrado.")
        return prompt_error_stream()

    return StreamingResponse(
        stream_creator_turn(
            kind="workflow",
            creator_id=creator_id,
            user_message=user_message,
            system_prompt=system_prompt,
            session_manager=creator_sessions,
            user_setup=user_setup,
            parameters=parameters,
        ),
        media_type="text/event-stream",
    )


@router.post("/workflow/verify")
async def post_verify_workflow(req: VerifyCreatorRequest):
    """Verify the workflow creator conversation on demand.

    Args:
        req: The verification request (creator conversation id).

    Returns:
        ``{"done", "reason"}``: whether the work fulfils the request.
    """
    return await verify_creator_conversation("workflow", creator_sessions, req.creator_id)


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

    final = {"status": "error", "message": "No se pudo crear la tarea programada."}
    last_text = ""
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
            if payload.get("type") == "chunk":
                last_text += str(payload.get("content") or "")
            elif payload.get("type") == "workflow_result_final":
                content = payload.get("content") or {}
                final = {"status": str(content.get("status", "error")), "message": str(content.get("message", ""))}
            elif payload.get("type") == "error":
                final = {"status": "error", "message": str(payload.get("content") or last_text or final["message"])}
    if final["status"] != "success" and last_text.strip() and final["message"] == "No se pudo crear la tarea programada.":
        final = {"status": "error", "message": last_text.strip()}
    return final
