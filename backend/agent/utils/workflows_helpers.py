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

# Same rule as ``workflow_loader._NAME_RE``: listings must agree with the loader.
_WORKFLOW_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


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
            if not entry.is_file() or entry.name.startswith("."):
                continue
            if entry.suffix != ".yaml":
                continue
            if not _WORKFLOW_NAME_RE.match(entry.stem):
                continue
            yaml_path = entry
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
                "name": entry.stem,
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


def _workflow_file_path(name: str) -> Path:
    """Return the absolute path of the flat workflow file.

    Args:
        name: The workflow name (file stem, ``<name>.yaml``).

    Returns:
        The absolute ``Path`` to the workflow YAML file.

    Raises:
        ValueError: If the name is empty, fails the workflow name regex,
            or contains path traversal.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Nombre de workflow inválido.")
    clean = name.strip()
    if not _WORKFLOW_NAME_RE.match(clean):
        raise ValueError("Nombre de workflow inválido.")
    if ".." in clean or "/" in clean or "\\" in clean:
        raise ValueError("Nombre de workflow inválido.")
    return _WORKFLOWS_DIR / f"{clean}.yaml"


# ═══════════════════════════════════════════════════════════════════════
# Verificación de referencias (agentes, tools, colecciones)
# ═══════════════════════════════════════════════════════════════════════


def _ref_es_segura(ref: str) -> bool:
    """Check a node reference for path traversal.

    Args:
        ref: Reference string from a workflow node.

    Returns:
        ``True`` when the ref is a plain name without traversal.
    """
    try:
        if not isinstance(ref, str) or not ref.strip():
            return False
        clean = ref.strip()
        return ".." not in clean and "/" not in clean and "\\" not in clean
    except Exception:
        return False


def verificar_refs(workflow: dict[str, Any]) -> dict[str, Any]:
    """Check that every node reference exists before running.

    Verifies ``agent`` nodes against ``get_agents_list``, ``tool`` nodes
    against the tools registry (native + external + MCP) and ``rag`` nodes
    against the vector collections. Anything missing is reported so the
    caller can show a friendly message instead of failing mid-run.

    Args:
        workflow: Validated workflow data (see ``workflow_validator``).

    Returns:
        ``{"ok": bool, "faltantes": [{"nodo", "tipo", "ref", "detalle"}]}``.
        Never raises: unexpected errors yield ``ok=False`` with a generic entry.
    """
    faltantes: list[dict[str, Any]] = []
    try:
        if not isinstance(workflow, dict):
            return {"ok": False, "faltantes": [{
                "nodo": "", "tipo": "", "ref": "",
                "detalle": "No se pudo leer el workflow.",
            }]}
        nodes = workflow.get("nodes", [])
        if not isinstance(nodes, list):
            return {"ok": False, "faltantes": [{
                "nodo": "", "tipo": "", "ref": "",
                "detalle": "El workflow no tiene nodos válidos.",
            }]}
    except Exception as exc:
        logger.warning("No se pudo leer nodos del workflow: %s", exc)
        return {"ok": False, "faltantes": [{
            "nodo": "", "tipo": "", "ref": "",
            "detalle": "No se pudo leer el workflow.",
        }]}

    try:
        from backend.agent.utils.agent_helpers import get_agents_list, get_tools_list

        agentes = {a.get("name", "") for a in (get_agents_list() or []) if isinstance(a, dict)}
        herramientas = {t.get("name", "") for t in (get_tools_list() or []) if isinstance(t, dict)}
        try:
            registry = getattr(getattr(agent, "tools", None), "_tools_registry", []) or []
            for entry in registry:
                if isinstance(entry, dict):
                    fname = (entry.get("function", {}) or {}).get("name", "")
                    if fname:
                        herramientas.add(fname)
        except Exception as exc:
            logger.warning("No se pudo leer registry de tools: %s", exc)
    except Exception as exc:
        logger.warning("No se pudieron listar agentes/tools: %s", exc)
        agentes, herramientas = set(), set()

    try:
        from backend.agent.utils.vector_db import get_vector_db

        colecciones_raw = get_vector_db().list_collections() or []
        colecciones = set()
        for c in colecciones_raw:
            try:
                if isinstance(c, dict) and c.get("name"):
                    colecciones.add(str(c["name"]))
                elif isinstance(c, str) and c.strip():
                    colecciones.add(c.strip())
            except Exception:
                continue
    except Exception as exc:
        logger.warning("No se pudieron listar colecciones RAG: %s", exc)
        colecciones = set()

    for node in nodes:
        try:
            if not isinstance(node, dict):
                continue
            nid = str(node.get("id", "") or "")
            ntype = str(node.get("type", "") or "")
            if ntype == "agent":
                ref = str(node.get("agent_name", "") or "")
                if not _ref_es_segura(ref):
                    faltantes.append({"nodo": nid, "tipo": "agent", "ref": ref,
                                      "detalle": f"Nombre de agente inválido en nodo '{nid}'."})
                elif ref not in agentes:
                    faltantes.append({"nodo": nid, "tipo": "agent", "ref": ref,
                                      "detalle": f"No se encontró el agente '{ref}' (nodo '{nid}'). Revisá que exista en la carpeta de agentes."})
            elif ntype == "tool":
                ref = str(node.get("tool", "") or "")
                if not _ref_es_segura(ref):
                    faltantes.append({"nodo": nid, "tipo": "tool", "ref": ref,
                                      "detalle": f"Nombre de tool inválido en nodo '{nid}'."})
                elif ref not in herramientas:
                    faltantes.append({"nodo": nid, "tipo": "tool", "ref": ref,
                                      "detalle": f"No se encontró la tool '{ref}' (nodo '{nid}'). Revisá que exista entre las tools."})
            elif ntype == "rag":
                ref = str(node.get("collection", "") or "")
                if not _ref_es_segura(ref):
                    faltantes.append({"nodo": nid, "tipo": "rag", "ref": ref,
                                      "detalle": f"Nombre de colección inválido en nodo '{nid}'."})
                elif ref not in colecciones:
                    faltantes.append({"nodo": nid, "tipo": "rag", "ref": ref,
                                      "detalle": f"No existe la colección RAG '{ref}' (nodo '{nid}'). Revisá que esté indexada."})
        except Exception as exc:
            logger.warning("No se pudo verificar nodo: %s", exc)
            continue

    return {"ok": not faltantes, "faltantes": faltantes}
