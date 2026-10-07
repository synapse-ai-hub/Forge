"""Helpers for workflow creation.

Low-level internal functions:
- ``_listar_workflows_locales`` — Scans ``~/.config/synapseForge/workflows/``.
- ``_evaluar_si_existe`` — Asks the LLM whether an existing workflow already
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

from backend.agent.utils.config_dir import get_workflows_dir
from backend.agent.utils.create_helpers import resolve_create_model_provider
from backend.instances import agent

logger = logging.getLogger(__name__)

_WORKFLOWS_DIR = get_workflows_dir()


# ═══════════════════════════════════════════════════════════════════════
# Workflows locales
# ═══════════════════════════════════════════════════════════════════════


def _listar_workflows_locales() -> list[dict[str, Any]]:
    """Scan local workflows and return name + description.

    Returns:
        List of ``{"name", "description", "path"}`` dicts.
    """
    try:
        if not _WORKFLOWS_DIR.is_dir():
            return []
    except Exception as exc:
        logger.warning("No se pudo listar workflows: %s", exc)
        return []
    resultados: list[dict[str, Any]] = []
    try:
        entries = sorted(_WORKFLOWS_DIR.iterdir())
    except Exception as exc:
        logger.warning("No se pudo listar workflows: %s", exc)
        return []
    for entry in entries:
        try:
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            yaml_path = entry / "workflow.yaml"
            if not yaml_path.is_file():
                continue
            description = ""
            try:
                import yaml as _yaml

                data = _yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    description = str(data.get("description", "") or "")
            except Exception as exc:
                logger.warning("No se pudo leer %s: %s", yaml_path, exc)
                continue
            resultados.append({
                "name": entry.name,
                "description": description[:200],
                "path": str(entry),
            })
        except Exception as exc:
            logger.warning("No se pudo leer %s: %s", entry, exc)
            continue
    return resultados


# ═══════════════════════════════════════════════════════════════════════
# Evaluación con LLM (Sí/No)
# ═══════════════════════════════════════════════════════════════════════


async def _evaluar_si_existe(
    tarea: str,
    workflows_locales: list[dict[str, Any]],
    model: str | None = None,
    provider: str | None = None,
) -> dict | None:
    """Ask the LLM whether a local workflow already covers the task.

    Args:
        tarea: What the user wants to do.
        workflows_locales: List of existing workflows.
        model: Model chosen by the user (optional).
        provider: Provider chosen by the user (optional).

    Returns:
        ``{"exist": "Sí", "workflow": ...}`` or ``{"exist": "No", "workflow": None}``.
    """
    try:
        eval_model, eval_provider = resolve_create_model_provider(model, provider)
    except Exception as exc:
        logger.warning("No se pudo resolver modelo: %s", exc)
        return None
    if not eval_model:
        logger.warning("Sin modelo configurado.")
        return None

    if workflows_locales:
        lines = []
        for w in workflows_locales:
            try:
                if not isinstance(w, dict):
                    continue
                wname = str(w.get("name", "") or "")
                wdesc = str(w.get("description", "") or "")
                if not wname:
                    continue
                lines.append(f"- **{wname}**: {wdesc[:200]}")
            except Exception as exc:
                logger.warning("Entrada de workflow inválida: %s", exc)
                continue
        workflows_text = "\n".join(lines) if lines else "(No hay workflows creados todavía.)"
    else:
        workflows_text = "(No hay workflows creados todavía.)"

    prompt = (
        "Sos un asistente que evalúa si algún workflow ya cubre una tarea.\n\n"
        f"Tarea del usuario: {tarea}\n\n"
        f"Workflows disponibles:\n{workflows_text}\n\n"
        "Respondé SOLO con un JSON con este formato:\n"
        '{"exist": "Sí", "workflow": "<nombre exacto del workflow>"}\n'
        "o\n"
        '{"exist": "No", "workflow": null}\n\n'
        "Reglas:\n"
        "- 'Sí' solo si hay un workflow que claramente cumple la tarea.\n"
        "- Si ningún workflow sirve, 'No'.\n"
        "- Sin texto adicional, solo el JSON."
    )

    try:
        result = await agent.llm_process(
            model=eval_model,
            provider=eval_provider,
            prompt=prompt,
            temperature=0.0,
            top_p=0.6,
            max_tokens=5000,
            cleaned_output=True,
        )
    except Exception as exc:
        logger.warning("Error del LLM evaluando workflows: %s", exc)
        return None

    try:
        from backend.agent.utils.spend_handler import record_creator_call

        record_creator_call(
            "creator:workflow:evaluate", eval_provider, eval_model,
            result.get("usage") if isinstance(result, dict) else None,
        )
    except Exception as exc:
        logger.debug("No se pudo registrar creator call: %s", exc)

    if not isinstance(result, dict):
        logger.warning("LLM no devolvió resultado válido.")
        return None
    if result.get("status") != "success" or not result.get("data"):
        logger.warning("Error del LLM: %s", result.get("message"))
        return None

    raw = str(result.get("data", "") or "").strip()
    m = re.search(r"\{.*?\}", raw, re.DOTALL)
    if not m:
        logger.warning("LLM no devolvió JSON: %s", raw[:150])
        return None
    try:
        return json.loads(m.group(0))
    except Exception as exc:
        logger.warning("Error parseando JSON: %s", exc)
        return None


def _workflow_dir_path(name: str) -> Path:
    """Return the absolute path of the workflow directory.

    Args:
        name: The workflow name (directory name).

    Returns:
        The absolute ``Path`` to the workflow directory.

    Raises:
        ValueError: If the name is empty or contains path traversal.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Nombre de workflow inválido.")
    clean = name.strip()
    if ".." in clean or "/" in clean or "\\" in clean:
        raise ValueError("Nombre de workflow inválido.")
    return _WORKFLOWS_DIR / clean
