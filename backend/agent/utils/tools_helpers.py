"""Helpers for external tool creation.

Low-level internal functions:
- ``_listar_tools_locales`` — Scans ``~/.config/synapseForge/tools/``.
- ``_evaluar_si_existe`` — Asks the LLM whether an existing tool already
  covers the task.

All are imported by ``backend/routes/create.py``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Ensure the project root is in sys.path for absolute imports
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(_current_dir)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.utils.config_dir import get_tools_dir
from backend.agent.utils.create_helpers import resolve_create_model_provider
from backend.instances import agent

logger = logging.getLogger(__name__)

_TOOLS_DIR = get_tools_dir()


# ═══════════════════════════════════════════════════════════════════════
# Tools locales
# ═══════════════════════════════════════════════════════════════════════


def _listar_tools_locales() -> list[dict[str, Any]]:
    """Scan external tools and return name + description.

    Returns:
        List of ``{"name", "description", "path"}`` dicts.
    """
    if not _TOOLS_DIR.is_dir():
        return []
    resultados: list[dict[str, Any]] = []
    for entry in sorted(_TOOLS_DIR.iterdir()):
        if not entry.is_file():
            continue
        if not entry.name.endswith(".py") or entry.name.startswith("_"):
            continue
        try:
            content = entry.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("No se pudo leer %s: %s", entry, e)
            continue
        # Descripción = primera línea del módulo docstring
        mod_doc = content.strip().split("\n", 1)[0].strip()
        description = mod_doc.lstrip("\"'> ").rstrip("\"'> ") if mod_doc else ""
        if not description:
            continue
        resultados.append({
            "name": entry.stem,
            "description": description[:200],
            "path": str(entry),
        })
    return resultados


# ═══════════════════════════════════════════════════════════════════════
# Evaluación con LLM (Sí/No)
# ═══════════════════════════════════════════════════════════════════════


async def _evaluar_si_existe(
    tarea: str,
    tools_locales: list[dict[str, Any]],
    model: str | None = None,
    provider: str | None = None,
) -> dict | None:
    """Pregunta al LLM si alguna tool local cubre la tarea.

    Args:
        tarea: Lo que el usuario quiere hacer.
        tools_locales: Lista de tools existentes.
        model: Modelo elegido por el usuario (opcional).
        provider: Provider elegido por el usuario (opcional).

    Returns:
        ``{"exist": "Sí", "tool": ...}`` o ``{"exist": "No", "tool": None}``.
    """
    eval_model, eval_provider = resolve_create_model_provider(model, provider)
    if not eval_model:
        logger.warning("Sin modelo configurado.")
        return None

    if tools_locales:
        lines = [f"- **{t['name']}**: {t['description'][:200]}" for t in tools_locales]
        tools_text = "\n".join(lines)
    else:
        tools_text = "(No hay tools externas creadas todavía.)"

    prompt = (
        "Sos un asistente que evalúa si alguna tool externa ya cubre una tarea.\n\n"
        f"Tarea del usuario: {tarea}\n\n"
        f"Tools externas disponibles:\n{tools_text}\n\n"
        "Respondé SOLO con un JSON con este formato:\n"
        '{"exist": "Sí", "tool": "<nombre exacto de la tool>"}\n'
        'o\n'
        '{"exist": "No", "tool": null}\n\n'
        "Reglas:\n"
        "- 'Sí' solo si hay una tool que claramente cumple la tarea.\n"
        "- Si ninguna tool sirve, 'No'.\n"
        "- Sin texto adicional, solo el JSON."
    )

    result = await agent.llm_process(
        model=eval_model,
        provider=eval_provider,
        prompt=prompt,
        temperature=0.0,
        top_p=0.6,
        max_tokens=5000,
        cleaned_output=True,
    )

    # Contemplate this evaluator LLM call (tracked in creator_calls
    # since it never produces messages rows).
    try:
        from backend.agent.utils.spend_handler import record_creator_call

        record_creator_call(
            "creator:tool:evaluate", eval_provider, eval_model,
            result.get("usage") if isinstance(result, dict) else None,
        )
    except Exception:
        pass

    if result.get("status") != "success" or not result.get("data"):
        logger.warning("Error del LLM: %s", result.get("message"))
        return None

    raw = result["data"].strip()
    m = re.search(r"\{.*?\}", raw, re.DOTALL)
    if not m:
        logger.warning("LLM no devolvió JSON: %s", raw[:150])
        return None
    try:
        return json.loads(m.group(0))
    except Exception as e:
        logger.warning("Error parseando JSON: %s", e)
        return None


def _tool_file_path(name: str) -> Path:
    """Return the absolute path of the tool file.

    Args:
        name: The tool name (without the ``.py`` extension).

    Returns:
        The absolute ``Path`` to the tool file.
    """
    return _TOOLS_DIR / f"{name}.py"