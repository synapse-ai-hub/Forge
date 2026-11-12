"""Endpoint to create or modify external tools.

Runs the agent loop with the tool creator system prompt. Every turn of the
same ``creator_id`` continues the conversation (history persists in the
``creators`` table): the first turn carries the setup form, follow-ups carry
only the user message. When the turn creates or modifies the tool file, a
terminal ``tool_result_final`` event is appended; a turn that only asks
questions emits none.
"""

from __future__ import annotations

import logging
import uuid

from typing import Optional

from fastapi import File, Form, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from backend.agent.creator_session import CreatorSessionManager
from backend.agent.utils.create_helpers import resolve_create_model_provider
from backend.agent.utils.creators import is_valid_id
from backend.instances import agent
from backend.routes.create.common import (
    _TOOLS_DIR,
    VerifyCreatorRequest,
    error_response,
    parse_creator_list,
    process_creator_attachments,
    prompt_error_stream,
    router,
    stream_creator_turn,
    verify_creator_conversation,
)

logger = logging.getLogger(__name__)

creator_sessions = CreatorSessionManager(kind="tool")
"""Persistence of the tool creator conversations."""


def _setup_text(name: str | None, descripcion: str, parametros: list | None, datos: list | None) -> str:
    """Render the setup form as the head of the first user message.

    Args:
        name: Tool name suggested by the user.
        descripcion: What the tool does.
        parametros: Parameters the LLM passes when invoking it.
        datos: External data (env vars, secrets, fixed endpoints).

    Returns:
        The setup block in plain text.
    """
    lines = ["Datos del formulario:"]
    lines.append(f"- Nombre: {name or '(sin nombre, elegilo vos)'}")
    lines.append(f"- Descripción: {descripcion}")
    if parametros:
        lines.append("- Parámetros:")
        for p in parametros:
            if isinstance(p, dict):
                pname = p.get("name", "?")
                ptype = p.get("type", "?")
                pdesc = p.get("description", "")
                lines.append(f"  - {pname} ({ptype}): {pdesc}")
            else:
                lines.append(f"  - {p}")
    else:
        lines.append("- Parámetros: (no indicados, inferilos)")
    if datos:
        lines.append("- Datos externos:")
        for d in datos:
            if isinstance(d, dict):
                lines.append(f"  - {d.get('name', '?')}: {d.get('description', '')}")
            else:
                lines.append(f"  - {d}")
    else:
        lines.append("- Datos externos: (no indicados)")
    return "\n".join(lines)


@router.post("/tool")
async def post_create_tool_stream(
    descripcion: str = Form(...),
    name: str | None = Form(None),
    creator_id: str | None = Form(None),
    parametros: str | None = Form(None),
    datos: str | None = Form(None),
    model: str | None = Form(None),
    provider: str | None = Form(None),
    files: Optional[list[UploadFile]] = File(None),
):
    """Stream one turn of the tool creator.

    Accepts setup fields as ``FormData`` with optional file attachments
    on every turn (setup and iteration). Attachments travel as extracted
    text via ``file_contents`` so they are injected into the prompt like
    the main chat (``<inicio_adjuntos>``).

    Args:
        descripcion: What the tool does (or follow-up message).
        name: Tool name suggested by the user.
        creator_id: Creator conversation id.
        parametros: JSON string with parameters list.
        datos: JSON string with external data list.
        model: Optional model override.
        provider: Optional provider override.
        files: Optional attachments (every turn).

    Returns:
        A ``StreamingResponse`` with the loop SSE events plus, when the
        turn touched the tool file, a terminal ``tool_result_final`` event.
    """
    descripcion = (descripcion or "").strip()
    if not descripcion:
        return error_response("La descripción es obligatoria.")
    cid = creator_id if creator_id and is_valid_id(creator_id) else str(uuid.uuid4())
    nombre = (name or "").strip() or None
    parametros_list = parse_creator_list(parametros)
    datos_list = parse_creator_list(datos)

    try:
        file_contents, raw_files = await process_creator_attachments(files, cid, creator_sessions)
    except ValueError as exc:
        return error_response(str(exc))

    first_turn = not creator_sessions.has_rows(cid)
    if first_turn:
        setup_lines = _setup_text(nombre, descripcion, parametros_list, datos_list)
        if file_contents:
            setup_lines += f"\n- Archivos adjuntos: {', '.join(n for n, _ in file_contents)}"
        user_message = f"{setup_lines}\n\nMensaje del usuario: {descripcion}"
        user_setup: dict | None = {
            "name": nombre,
            "descripcion": descripcion,
            "parametros": parametros_list,
            "datos": datos_list,
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
        from backend.agent.utils.email_accounts import load_email_accounts_text

        system_prompt = agent.prompt("create_tool", carpeta=_TOOLS_DIR.as_posix(), email_accounts=load_email_accounts_text())
    except Exception:
        logger.exception("Prompt create_tool.jinja no encontrado.")
        return prompt_error_stream()

    return StreamingResponse(
        stream_creator_turn(
            kind="tool",
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


@router.post("/tool/verify")
async def post_verify_tool(req: VerifyCreatorRequest):
    """Verify the tool creator conversation on demand.

    Args:
        req: The verification request (creator conversation id).

    Returns:
        ``{"done", "reason"}``: whether the work fulfils the request.
    """
    return await verify_creator_conversation("tool", creator_sessions, req.creator_id)
