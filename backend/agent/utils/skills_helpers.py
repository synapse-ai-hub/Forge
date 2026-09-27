"""Helpers for skill creation.

Low-level internal functions:
- ``_parse_frontmatter``
- ``_listar_skills_locales``
- ``_evaluar_si_existe``
- ``_explain_skill``
- ``_create_skill``
- ``_copiar_referencias``

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

from backend.agent.utils.config_dir import get_skills_dir
from backend.agent.utils.create_helpers import resolve_create_model_provider
from backend.instances import agent

logger = logging.getLogger(__name__)

_SKILLS_DIR = get_skills_dir()


# ═══════════════════════════════════════════════════════════════════════
# Frontmatter
# ═══════════════════════════════════════════════════════════════════════


def _parse_frontmatter(content: str) -> dict[str, Any]:
    """Parse the YAML frontmatter of a SKILL.md file.

    Args:
        content: Full file content.

    Returns:
        A dict with the frontmatter fields, or an empty dict.
    """
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}
    try:
        import yaml

        return yaml.safe_load(match.group(1)) or {}
    except Exception as e:
        logger.warning("Error parseando frontmatter: %s", e)
        return {}


# ═══════════════════════════════════════════════════════════════════════
# Skills locales
# ═══════════════════════════════════════════════════════════════════════


def _listar_skills_locales() -> list[dict[str, Any]]:
    """Scan local skills and return name + description.

    Returns:
        List of ``{"name", "description"}`` dicts.
    """
    if not _SKILLS_DIR.is_dir():
        return []
    resultados: list[dict[str, Any]] = []
    for d in _SKILLS_DIR.iterdir():
        if not d.is_dir():
            continue
        md = d / "SKILL.md"
        if not md.is_file():
            continue
        fm = _parse_frontmatter(md.read_text(encoding="utf-8"))
        resultados.append({
            "name": d.name,
            "description": fm.get("description", ""),
            "triggers": (fm.get("metadata") or {}).get("triggers", ""),
            "path": str(d),
        })
    return resultados


# ═══════════════════════════════════════════════════════════════════════
# Evaluación con LLM (Sí/No)
# ═══════════════════════════════════════════════════════════════════════


async def _evaluar_si_existe(
    tarea: str,
    skills_locales: list[dict[str, Any]],
    model: str | None = None,
    provider: str | None = None,
) -> dict | None:
    """Pregunta al LLM si alguna skill local sirve.

    Args:
        tarea: Lo que el usuario quiere hacer.
        skills_locales: Lista de skills existentes.
        model: Modelo elegido por el usuario (opcional).
        provider: Provider elegido por el usuario (opcional).

    Returns:
        ``{"exist": "Sí", "skill": ...}`` o ``{"exist": "No", "skill": None}``.
    """
    eval_model, eval_provider = resolve_create_model_provider(model, provider)
    if not eval_model:
        logger.warning("Sin modelo configurado.")
        return None

    try:
        template = agent.prompt("evaluate_skills")
    except FileNotFoundError:
        logger.warning("Prompt evaluate_skills.md no encontrado.")
        return None

    if skills_locales:
        lines = [f"- **{s['name']}**: {s['description'][:200]}" for s in skills_locales]
        skills_text = "\n".join(lines)
    else:
        skills_text = "(No hay skills creadas todavía.)"

    prompt = template.format(tarea=tarea, skills=skills_text)

    # print("=" * 60)
    # print(">>> EVALUAR SKILLS - PROMPT AL LLM:")
    # print(prompt)
    # print("=" * 60)

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
            "creator:skill:evaluate", eval_provider, eval_model,
            result.get("usage") if isinstance(result, dict) else None,
        )
    except Exception:
        pass

    # print(">>> EVALUAR SKILLS - RESPUESTA CRUDA DEL LLM:")
    # print("  result brute:", result)
    # print("=" * 60)

    if result.get("status") != "success" or not result.get("data"):
        logger.warning("Error del LLM: %s", result.get("message"))
        return None

    raw = result["data"].strip()
    m = re.search(r"\{.*?\}", raw, re.DOTALL)
    if not m:
        logger.warning("LLM no devolvió JSON: %s", raw[:150])
        return None
    try:
        parsed = json.loads(m.group(0))
        # print(">>> EVALUAR SKILLS - JSON PARSED:", parsed)
        # print("=" * 60)
        return parsed
    except Exception as e:
        logger.warning("Error parseando JSON: %s", e)
        return None


# ═══════════════════════════════════════════════════════════════════════
# Explicación de skill existente
# ═══════════════════════════════════════════════════════════════════════


async def _explain_skill(
    tarea: str,
    skill_dir: Path,
    model: str | None = None,
    provider: str | None = None,
) -> str | None:
    """Pide al LLM una breve explicación de qué hace la skill.

    Args:
        tarea: Lo que el usuario quiere resolver.
        skill_dir: Directorio de la skill.
        model: Modelo elegido por el usuario (opcional).
        provider: Provider elegido por el usuario (opcional).

    Returns:
        Explicación breve, o None si falla.
    """
    eval_model, eval_provider = resolve_create_model_provider(model, provider)
    if not eval_model:
        return None

    md_path = skill_dir / "SKILL.md"
    if not md_path.is_file():
        return None

    contenido = md_path.read_text(encoding="utf-8")

    try:
        template = agent.prompt("explain_skill")
    except FileNotFoundError:
        logger.warning("Prompt explain_skill.md no encontrado.")
        return None

    prompt = template.format(tarea=tarea, contenido=contenido)

    result = await agent.llm_process(
        model=eval_model,
        provider=eval_provider,
        prompt=prompt,
        temperature=0.3,
        top_p=0.8,
        max_tokens=5000,
        cleaned_output=True,
    )

    # Contemplate this explainer LLM call (tracked in creator_calls
    # since it never produces messages rows).
    try:
        from backend.agent.utils.spend_handler import record_creator_call

        record_creator_call(
            "creator:skill:explain", eval_provider, eval_model,
            result.get("usage") if isinstance(result, dict) else None,
        )
    except Exception:
        pass

    if result.get("status") != "success" or not result.get("data"):
        return None

    raw = result["data"].strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        dec = json.loads(m.group(0))
        return dec.get("explicacion")
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════
# Generación con LLM
# ═══════════════════════════════════════════════════════════════════════


async def _create_skill(
    conversacion: str,
    nombre: str | None = None,
    model: str | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    """Generate a skill with the LLM using the ``create_skill`` prompt.

    Args:
        conversacion: Full conversation history with the user.
        nombre: Suggested name for the skill.
        model: Model chosen by the user (optional).
        provider: Provider chosen by the user (optional).

    Returns:
        ``{"name": ..., "content": ...}``.

    Raises:
        RuntimeError: If the LLM fails or no model is available.
    """
    eval_model, eval_provider = resolve_create_model_provider(model, provider)
    if not eval_model:
        raise RuntimeError("No hay modelo configurado. Seleccioná un modelo en Configuración.")

    try:
        template = agent.prompt("create_skill")
    except FileNotFoundError:
        raise RuntimeError("Prompt create_skill.md no encontrado.")

    prompt = template.format(
        nombre=nombre or "(inferir del contexto)",
        conversacion=conversacion,
    )

    logger.info("Generando skill con LLM (%s)...", eval_model)

    result = await agent.llm_process(
        model=eval_model,
        provider=eval_provider,
        prompt=prompt,
        temperature=0.4,
        top_p=0.85,
        max_tokens=15000,
        cleaned_output=True,
    )

    # Contemplate this generator LLM call (tracked in creator_calls
    # since it never produces messages rows).
    try:
        from backend.agent.utils.spend_handler import record_creator_call

        record_creator_call(
            "creator:skill:generate", eval_provider, eval_model,
            result.get("usage") if isinstance(result, dict) else None,
        )
    except Exception:
        pass

    if result.get("status") != "success" or not result.get("data"):
        raise RuntimeError(f"Error del LLM: {result.get('message', 'sin respuesta')}")

    raw = result["data"]
    # Safety: strip markdown code fences
    raw = re.sub(r"^```\w*\s*", "", raw.strip())
    raw = re.sub(r"\s*```\s*$", "", raw)
    fm = _parse_frontmatter(raw)
    skill_name = nombre or fm.get("name") or "skill-generada"
    return {"name": skill_name, "content": raw}


# ═══════════════════════════════════════════════════════════════════════
# Post-creación: referencias
# ═══════════════════════════════════════════════════════════════════════


def _copiar_referencias(
    skill_dir: Path,
    mensajes: list[dict] | None = None,
    refs: str | None = None,
    archivos_raw: dict[str, bytes] | None = None,
) -> None:
    """Copy the user's attached files into ``references/``.

    Separate step from skill creation. Only copies files by code; the LLM
    already referenced these files in the SKILL.md with relative paths
    (``references/``).

    No nested subdirectories are created, only loose files inside
    ``references/``.

    Args:
        skill_dir: The skill directory.
        mensajes: Message history (may contain ``files``).
        refs: LLM reference text (optional, legacy).
        archivos_raw: Dict ``{filename: bytes}`` with the raw bytes of the
            uploaded files (takes priority over ``files[].content``).
    """
    refs_dir = skill_dir / "references"
    refs_dir.mkdir(exist_ok=True)

    # 5a. Si el LLM devolvió refs de texto (legacy)
    if refs and refs.strip():
        (refs_dir / "referencias_usuario.md").write_text(refs, encoding="utf-8")
        logger.info("Refs de texto guardadas en references/")

    # 5b. Copiar archivos adjuntos del usuario con nombre original
    #     Solo archivos sueltos, sin subdirectorios anidados.
    contadas = 0

    # Prioridad: archivos_raw (bytes del UploadFile) > files[].content (legacy)
    if archivos_raw:
        for fname, raw_bytes in archivos_raw.items():
            safe_name = Path(fname).name
            if not safe_name:
                continue
            ref_path = refs_dir / safe_name
            ref_path.write_bytes(raw_bytes)
            contadas += 1
            logger.info("Referencia copiada (raw): %s", ref_path)
    elif mensajes:
        for m in mensajes:
            files = m.get("files")
            if files and isinstance(files, list):
                for f in files:
                    fname = f.get("name", "archivo")
                    fcontent = f.get("content", "")
                    if fname and fcontent:
                        safe_name = Path(fname).name
                        if not safe_name:
                            continue
                        ref_path = refs_dir / safe_name
                        ref_path.write_text(fcontent, encoding="utf-8")
                        contadas += 1
                        logger.info("Referencia copiada: %s", ref_path)
        if contadas:
            logger.info("%d archivos copiados a references/", contadas)
