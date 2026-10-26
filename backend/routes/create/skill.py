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
    prompt_error_stream,
    router,
    VerifyCreatorRequest,
    stream_creator_turn,
    verify_creator_conversation,
)
from backend.routes.file_text_extractor import extract_text_from_bytes

logger = logging.getLogger(__name__)

creator_sessions = CreatorSessionManager(kind="skill")
"""Persistence of the skill creator conversations."""

_MAX_FILES = 3
_MAX_TOTAL_BYTES = 1 * 1024 * 1024


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
    file_contents: list[tuple[str, str]] = []
    if first_turn and files:
        total_bytes = 0
        for i, file in enumerate(files[:_MAX_FILES]):
            filename = file.filename or f"archivo_{i + 1}"
            try:
                content = await file.read()
            except Exception as exc:
                logger.warning("Error leyendo archivo %s: %s", filename, exc)
                continue
            total_bytes += len(content)
            if total_bytes > _MAX_TOTAL_BYTES:
                return error_response(
                    f"Los adjuntos superan 1 MB en total."
                )
            try:
                result = extract_text_from_bytes(filename, content)
                file_contents.append((filename, result.text or f"[Error al procesar {filename}]"))
            except Exception as exc:
                logger.warning("Error extrayendo texto de %s: %s", filename, exc)
                file_contents.append((filename, f"[Error al procesar {filename}.]"))

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
            "files": [{"name": n, "size": len(t)} for n, t in file_contents],
        }
    else:
        user_message = texto
        user_setup = None

    parameters: dict | None = None
    if model or provider:
        resolved_model, resolved_provider = resolve_create_model_provider(model, provider)
        parameters = {"model": resolved_model, "provider": resolved_provider}

    try:
        system_prompt = agent.prompt("create_skill", carpeta=str(_SKILLS_DIR / (nombre or "skill")))
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
