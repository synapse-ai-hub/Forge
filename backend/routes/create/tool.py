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

from fastapi.responses import JSONResponse, StreamingResponse

from backend.agent.creator_session import CreatorSessionManager
from backend.agent.utils.create_helpers import resolve_create_model_provider
from backend.agent.utils.creators import is_valid_id
from backend.instances import agent
from backend.routes.create.common import (
    CreateToolRequest,
    error_response,
    router,
    stream_creator_turn,
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
async def post_create_tool_stream(req: CreateToolRequest):
    """Stream one turn of the tool creator.

    Args:
        req: The creation request (message, optional name, setup form,
            optional creator id and optional model/provider override).

    Returns:
        A ``StreamingResponse`` with the loop SSE events plus, when the
        turn touched the tool file, a terminal ``tool_result_final`` event.
    """
    descripcion = (req.descripcion or "").strip()
    if not descripcion:
        return error_response("La descripción es obligatoria.")
    creator_id = req.creator_id if req.creator_id and is_valid_id(req.creator_id) else str(uuid.uuid4())
    nombre = (req.name or "").strip() or None

    first_turn = not creator_sessions.has_rows(creator_id)
    if first_turn:
        user_message = f"{_setup_text(nombre, descripcion, req.parametros, req.datos)}\n\nMensaje del usuario: {descripcion}"
        user_setup: dict | None = {
            "name": nombre,
            "descripcion": descripcion,
            "parametros": req.parametros or [],
            "datos": req.datos or [],
        }
    else:
        user_message = descripcion
        user_setup = None

    parameters: dict | None = None
    if req.model or req.provider:
        model, provider = resolve_create_model_provider(req.model, req.provider)
        parameters = {"model": model, "provider": provider}

    try:
        system_prompt = agent.prompt("create_tool")
    except Exception:
        logger.exception("Prompt create_tool.jinja no encontrado.")
        return error_response("No se pudo cargar el prompt del creador de tools.", status_code=500)

    return StreamingResponse(
        stream_creator_turn(
            kind="tool",
            creator_id=creator_id,
            user_message=user_message,
            system_prompt=system_prompt,
            session_manager=creator_sessions,
            user_setup=user_setup,
            parameters=parameters,
        ),
        media_type="text/event-stream",
    )
