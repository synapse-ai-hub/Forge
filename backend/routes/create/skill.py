"""Endpoint to create or modify skills.

Runs the agent loop with the skill creator system prompt. Every turn of the
same ``creator_id`` continues the conversation (history persists in the
``creators`` table): the first turn carries the setup form, follow-ups carry
only the user message. Attachments travel as extracted text. When the turn
creates or modifies the skill, a terminal ``skill_result_final`` event is
appended; a turn that only asks questions emits none.
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
    _SKILLS_DIR,
    error_response,
    process_creator_attachments,
    prompt_error_stream,
    router,
    VerifyCreatorRequest,
    stream_creator_turn,
    verify_creator_conversation,
)

logger = logging.getLogger(__name__)

creator_sessions = CreatorSessionManager(kind="skill")
"""Persistence of the skill creator conversations."""


@router.post("/skill")
async def post_create_skill_stream(
    descripcion: str = Form(...),
    name: str | None = Form(None),
    creator_id: str | None = Form(None),
    model: str | None = Form(None),
    provider: str | None = Form(None),
    files: Optional[list[UploadFile]] = File(None),
):
    """Stream one turn of the skill creator.

    Args:
        descripcion: What the skill does (or the follow-up message).
        name: Skill name suggested by the user.
        creator_id: Creator conversation id (a new one is issued when missing).
        model: Optional model override chosen by the user.
        provider: Optional provider override chosen by the user.
        files: Optional attachments (first turn only).

    Returns:
        A ``StreamingResponse`` with the loop SSE events plus, when the
        turn touched the skill, a terminal ``skill_result_final`` event.
    """
    texto = (descripcion or "").strip()
    if not texto:
        return error_response("La descripción es obligatoria.")
    cid = creator_id if creator_id and is_valid_id(creator_id) else str(uuid.uuid4())
    nombre = (name or "").strip() or None

    first_turn = not creator_sessions.has_rows(cid)
    try:
        file_contents, raw_files = await process_creator_attachments(files, cid, creator_sessions)
    except ValueError as exc:
        return error_response(str(exc))

    if first_turn:
        setup_lines = [
            "Datos del formulario:",
            f"- Nombre: {nombre or '(sin nombre, elegilo vos)'}",
            f"- Descripción: {texto}",
        ]
        if file_contents:
            setup_lines.append(f"- Archivos adjuntos: {', '.join(n for n, _ in file_contents)}")
        user_message = "\n".join(setup_lines) + f"\n\nMensaje del usuario: {texto}"
        user_setup: dict | None = {
            "name": nombre,
            "descripcion": texto,
            "files": [{"name": n, "size": len(b)} for n, b in raw_files],
        }
    else:
        user_message = texto
        user_setup = None

    parameters: dict | None = None
    if model or provider:
        resolved_model, resolved_provider = resolve_create_model_provider(model, provider)
        parameters = {"model": resolved_model, "provider": resolved_provider}

    try:
        from backend.agent.utils.email_accounts import load_email_accounts_text

        system_prompt = agent.prompt(
            "create_skill",
            carpeta=str(_SKILLS_DIR / (nombre or "skill")),
            email_accounts=load_email_accounts_text(),
        )
    except Exception:
        logger.exception("Prompt create_skill.jinja no encontrado.")
        return prompt_error_stream()

    return StreamingResponse(
        stream_creator_turn(
            kind="skill",
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


@router.post("/skill/verify")
async def post_verify_skill(req: VerifyCreatorRequest):
    """Verify the skill creator conversation on demand.

    Args:
        req: The verification request (creator conversation id).

    Returns:
        ``{"done", "reason"}``: whether the work fulfils the request.
    """
    return await verify_creator_conversation("skill", creator_sessions, req.creator_id)
