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
    """Request para crear una skill con iteración."""

    descripcion: str
    name: str | None = None
    mensajes: list[dict] | None = None  # [{"role": "user"|"assistant", "content": "..."}]
    model: str | None = None  # Modelo cloud elegido para esta tarea (efímero)
    provider: str | None = None  # Provider cloud elegido para esta tarea (efímero)
    iterate: bool = False  # True = fase de iteración (modificar creación existente)


class CreateToolRequest(BaseModel):
    """Request para crear una tool externa con iteración."""

    descripcion: str
    name: str | None = None
    mensajes: list[dict] | None = None  # [{"role": "user"|"assistant", "content": "..."}]
    parametros: list[dict] | None = None  # [{"name", "type", "description", "required"}]
    datos: list[str] | None = None  # Lista de env vars / datos externos
    model: str | None = None  # Modelo cloud elegido para esta tarea (efímero)
    provider: str | None = None  # Provider cloud elegido para esta tarea (efímero)
    iterate: bool = False  # True = fase de iteración (modificar creación existente)


class CreateAgentRequest(BaseModel):
    """Request para crear un agente especializado con iteración."""

    descripcion: str
    name: str | None = None
    mensajes: list[dict] | None = None  # [{"role": "user"|"assistant", "content": "..."}]
    model: str | None = None  # Modelo cloud elegido para esta tarea (efímero)
    provider: str | None = None  # Provider cloud elegido para esta tarea (efímero)
    iterate: bool = False  # True = fase de iteración (modificar creación existente)


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
    """Serialize dict to SSE ``data: {...}\\n\\n``."""
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
    """Intenta extraer un JSON del texto generado por el LLM."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None
