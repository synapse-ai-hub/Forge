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

from typing import Optional

from fastapi import File, Form, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from backend.agent.creator_session import CreatorSessionManager
from backend.agent.utils.create_helpers import build_resource_context, resolve_create_model_provider
from backend.agent.utils.creators import is_valid_id
from backend.instances import agent
from backend.routes.create.common import (
    _AGENTS_DIR,
    CreateAgentRequest,
    VerifyCreatorRequest,
    error_response,
    parse_creator_dict,
    parse_creator_list,
    process_creator_attachments,
    prompt_error_stream,
    router,
    stream_creator_turn,
    verify_creator_conversation,
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
async def post_create_agent_stream(
    descripcion: str = Form(...),
    name: str | None = Form(None),
    creator_id: str | None = Form(None),
    agentes: str | None = Form(None),
    tools: str | None = Form(None),
    skills: str | None = Form(None),
    rag: str | None = Form(None),
    tool_args: str | None = Form(None),
    model: str | None = Form(None),
    provider: str | None = Form(None),
    files: Optional[list[UploadFile]] = File(None),
):
    """Stream one turn of the agent creator.

    Accepts setup fields as ``FormData`` with optional file attachments
    on every turn. Attachments travel as extracted text via
    ``file_contents`` so they are injected into the prompt like the main
    chat (``<inicio_adjuntos>``).

    Args:
        descripcion: What the agent does (or follow-up message).
        name: Agent name suggested by the user.
        creator_id: Creator conversation id.
        agentes: JSON string with sub-agents list.
        tools: JSON string with tools list.
        skills: JSON string with skills list.
        rag: JSON string with RAG collections list.
        tool_args: JSON string with tool args dict.
        model: Optional model override.
        provider: Optional provider override.
        files: Optional attachments (every turn).

    Returns:
        A ``StreamingResponse`` with the loop SSE events plus, when the
        turn touched the agent file, a terminal ``agent_result_final`` event.
    """
    descripcion = (descripcion or "").strip()
    if not descripcion:
        return error_response("La descripción es obligatoria.")
    cid = creator_id if creator_id and is_valid_id(creator_id) else str(uuid.uuid4())
    nombre = (name or "").strip() or None
    agentes_list = parse_creator_list(agentes)
    tools_list = parse_creator_list(tools)
    skills_list = parse_creator_list(skills)
    rag_list = parse_creator_list(rag)
    tool_args_dict = parse_creator_dict(tool_args)

    try:
        file_contents, raw_files = await process_creator_attachments(files, cid, creator_sessions)
    except ValueError as exc:
        return error_response(str(exc))

    first_turn = not creator_sessions.has_rows(cid)
    if first_turn:
        req_like = CreateAgentRequest(
            descripcion=descripcion,
            name=nombre,
            agentes=agentes_list,
            tools=tools_list,
            skills=skills_list,
            rag=rag_list,
            tool_args=tool_args_dict,
        )
        setup_text = _setup_text(req_like, descripcion)
        if file_contents:
            setup_text += f"\n- Archivos adjuntos: {', '.join(n for n, _ in file_contents)}"
        user_message = f"{setup_text}\n\nMensaje del usuario: {descripcion}"
        user_setup: dict | None = {
            "name": nombre,
            "descripcion": descripcion,
            "agentes": agentes_list,
            "tools": tools_list,
            "skills": skills_list,
            "rag": rag_list,
            "tool_args": tool_args_dict,
            "files": [{"name": n, "size": len(b)} for n, b in raw_files],
        }
    else:
        user_message = descripcion
        user_setup = None

    parameters: dict | None = None
    if model or provider:
        resolved_model, resolved_provider = resolve_create_model_provider(model, provider)
        parameters = {"model": resolved_model, "provider": resolved_provider}

    try:
        recursos = await build_resource_context(
            agentes=agentes_list, tools=tools_list, tool_args=tool_args_dict,
            skills=skills_list, rag=rag_list, with_skills=True, with_mcp=True,
        )
        system_prompt = agent.prompt("create_agent", carpeta=_AGENTS_DIR.as_posix(), **recursos)
    except Exception:
        logger.exception("Prompt create_agent.jinja no encontrado.")
        return prompt_error_stream()

    return StreamingResponse(
        stream_creator_turn(
            kind="agent",
            creator_id=cid,
            user_message=user_message,
            system_prompt=system_prompt,
            session_manager=creator_sessions,
            user_setup=user_setup,
            parameters=parameters,
            file_contents=file_contents or None,
        ),
        media_type="text/event-stream",
    )


@router.post("/agent/verify")
async def post_verify_agent(req: VerifyCreatorRequest):
    """Verify the agent creator conversation on demand.

    Args:
        req: The verification request (creator conversation id).

    Returns:
        ``{"done", "reason"}``: whether the work fulfils the request.
    """
    return await verify_creator_conversation("agent", creator_sessions, req.creator_id)
