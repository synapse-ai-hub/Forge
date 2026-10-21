"""Shared helpers for creation endpoints (skills, tools, agents).

Centralizes the router, request models, constants and helpers used by
``skill.py``, ``tool.py`` and ``agent.py``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from fastapi import APIRouter
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Ensure project root for absolute imports
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(_current_dir)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.utils.config_dir import get_agents_dir, get_skills_dir, get_tools_dir

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/create", tags=["create"])

_SKILLS_DIR = get_skills_dir()
_TOOLS_DIR = get_tools_dir()
_AGENTS_DIR = get_agents_dir()

# Mensaje user-friendly para errores: el detalle técnico NUNCA llega a la UI.
_FRIENDLY_ERROR = "No se pudo crear la skill. Ocurrió un error durante el proceso. Verificá la configuración e intentá de nuevo."
_FRIENDLY_ERROR_TOOL = "No se pudo crear la tool. Ocurrió un error durante el proceso. Verificá la configuración e intentá de nuevo."
_FRIENDLY_ERROR_AGENT = "No se pudo crear el agente. Ocurrió un error durante el proceso. Verificá la configuración e intentá de nuevo."


# ── Modelos de request / response ─────────────────────────────────────


class CreateSkillRequest(BaseModel):
    """Request to create a skill with iteration."""

    descripcion: str
    name: str | None = None
    mensajes: list[dict] | None = None  # [{"role": "user"|"assistant", "content": "..."}]
    model: str | None = None  # Modelo cloud elegido para esta tarea (efímero)
    provider: str | None = None  # Provider cloud elegido para esta tarea (efímero)
    iterate: bool = False  # True = fase de iteración (modificar creación existente)
    creator_id: str | None = None  # Conversation of the creator (history)


class CreateToolRequest(BaseModel):
    """Request to create an external tool with iteration."""

    descripcion: str
    name: str | None = None
    mensajes: list[dict] | None = None  # [{"role": "user"|"assistant", "content": "..."}]
    parametros: list[dict] | None = None  # [{"name", "type", "description", "required"}]
    datos: list[str | dict] | None = None  # env vars / datos externos: texto o {"name", "type", "description", "required"}
    model: str | None = None  # Modelo cloud elegido para esta tarea (efímero)
    provider: str | None = None  # Provider cloud elegido para esta tarea (efímero)
    iterate: bool = False  # True = fase de iteración (modificar creación existente)
    creator_id: str | None = None  # Conversation of the creator (history)


def _formatear_dato(d: str | dict) -> str:
    """Render one declared external datum (plain string or field dict) as a line of text.

    Args:
        d: The datum, as a string or a dict with its fields.

    Returns:
        The line of text.
    """
    if isinstance(d, dict):
        nombre = d.get("name", "?")
        desc = d.get("description", "")
        req = "obligatorio" if d.get("required", True) else "opcional"
        return f"{nombre} ({d.get('type', 'string')}, {req})" + (f": {desc}" if desc else "")
    return str(d)


class CreateAgentRequest(BaseModel):
    """Request to create a specialized agent with iteration."""

    descripcion: str
    name: str | None = None
    mensajes: list[dict] | None = None  # [{"role": "user"|"assistant", "content": "..."}]
    model: str | None = None  # Modelo cloud elegido para esta tarea (efímero)
    provider: str | None = None  # Provider cloud elegido para esta tarea (efímero)
    iterate: bool = False  # True = fase de iteración (modificar creación existente)
    creator_id: str | None = None  # Conversation of the creator (history)


# ── Tools permitidas para el agente creador ─────────────────────────

_AGENT_TOOLS_PERMS: dict[str, str] = {
    "read": "allow",
    "write": "allow",
    "edit": "allow",
    "shell": "allow",
    "list_dir": "allow",
}


# ── Helper: emitir SSE string ────────────────────────────────────────


def _sse(event: dict) -> str:
    """Serialize a dict as an SSE event, ``data: {...}`` followed by a blank line.

    Args:
        event: The event to send.

    Returns:
        The SSE-formatted string.
    """
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


# ── Helper: formatear mensajes ───────────────────────────────────────


def _formatear_mensajes(mensajes: list[dict]) -> str:
    """Convert the list of messages into text for the prompt.

    Args:
        mensajes: List of message dicts from the interview.

    Returns:
        A plain-text representation of the conversation.
    """
    if not mensajes:
        return "(Sin preguntas aún)"
    partes = []
    for m in mensajes:
        role = m.get("role", "user")
        content = m.get("content", "")
        label = "Usuario" if role == "user" else "Asistente"
        parte = f"**{label}**: {content}"
        files = m.get("files")
        if files and isinstance(files, list):
            for f in files:
                fname = f.get("name", "archivo")
                fcontent = f.get("content", "")
                if fcontent:
                    parte += f"\n\n[Archivo adjunto: {fname}]\n```\n{fcontent}\n```"
        partes.append(parte)
    return "\n\n".join(partes)


# ── Fallback: intentar extraer JSON del texto ────────────────────────


def _try_parse_json(text: str) -> dict | None:
    """Try to extract a JSON object from the text generated by the LLM.

    Args:
        text: Text answered by the LLM.

    Returns:
        The parsed dict, or None when no JSON object can be read.
    """
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None
