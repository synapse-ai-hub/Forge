"""Endpoint to create or modify specialized agents.

Runs the agent loop with the agent creator system prompt. Every turn of the
same ``creator_id`` continues the conversation (history persists in the
``creators`` table): the first turn carries the setup form, follow-ups carry
only the user message. When the turn writes the agent file, a terminal
``agent_result_final`` event is appended; a turn that only asks questions
emits none.
"""

from __future__ import annotations

import logging
import uuid

from fastapi.responses import JSONResponse, StreamingResponse

from backend.agent.creator_session import CreatorSessionManager
from backend.agent.utils.create_helpers import build_resource_context, resolve_create_model_provider
from backend.agent.utils.creators import is_valid_id
from backend.instances import agent
from backend.routes.create.common import (
    CreateAgentRequest,
    error_response,
    router,
    stream_creator_turn,
)

logger = logging.getLogger(__name__)

creator_sessions = CreatorSessionManager(kind="agent")
"""Persistence of the agent creator conversations."""


def _setup_text(req: CreateAgentRequest, descripcion: str) -> str:
    """Render the setup form as the head of the first user message.

    Args:
        req: The creation request.
        descripcion: What the agent does.

    Returns:
        The setup block in plain text.
    """
    lines = [
        "Datos del formulario:",
        f"- Nombre: {(req.name or '').strip() or '(sin nombre, elegilo vos)'}",
        f"- Descripción: {descripcion}",
    ]
    if req.agentes:
        lines.append(f"- Sub-agentes para delegar: {', '.join(req.agentes)}")
    if req.tools:
        lines.append(f"- Tools: {', '.join(req.tools)}")
    if req.tool_args:
        lines.append(f"- Argumentos de tools: {req.tool_args}")
    if req.skills:
        lines.append(f"- Skills: {', '.join(req.skills)}")
    if req.rag:
        lines.append(f"- Colecciones RAG: {', '.join(req.rag)}")
    return "\n".join(lines)


@router.post("/agent")
async def post_create_agent_stream(req: CreateAgentRequest):
    """Stream one turn of the agent creator.

    Args:
        req: The creation request (message, optional name, setup form,
            optional creator id and optional model/provider override).

    Returns:
        A ``StreamingResponse`` with the loop SSE events plus, when the
        turn touched the agent file, a terminal ``agent_result_final`` event.
    """
    descripcion = (req.descripcion or "").strip()
    if not descripcion:
        return error_response("La descripción es obligatoria.")
    creator_id = req.creator_id if req.creator_id and is_valid_id(req.creator_id) else str(uuid.uuid4())
    nombre = (req.name or "").strip() or None

    first_turn = not creator_sessions.has_rows(creator_id)
    if first_turn:
        user_message = f"{_setup_text(req, descripcion)}\n\nMensaje del usuario: {descripcion}"
        user_setup: dict | None = {
            "name": nombre,
            "descripcion": descripcion,
            "agentes": req.agentes or [],
            "tools": req.tools or [],
            "skills": req.skills or [],
            "rag": req.rag or [],
            "tool_args": req.tool_args or {},
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
            skills=req.skills, rag=req.rag, with_skills=True, with_mcp=True,
        )
        system_prompt = agent.prompt("create_agent", **recursos)
    except Exception:
        logger.exception("Prompt create_agent.jinja no encontrado.")
        return error_response("No se pudo cargar el prompt del creador de agentes.", status_code=500)

    return StreamingResponse(
        stream_creator_turn(
            kind="agent",
            creator_id=creator_id,
            user_message=user_message,
            system_prompt=system_prompt,
            session_manager=creator_sessions,
            user_setup=user_setup,
            parameters=parameters,
        ),
        media_type="text/event-stream",
    )
