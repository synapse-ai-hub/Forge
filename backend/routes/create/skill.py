"""Endpoint POST /api/create/skill — crear skills via entrevista LLM."""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, AsyncGenerator, Optional

from fastapi import File, Form, UploadFile
from fastapi.responses import StreamingResponse

# ---------------------------------------------------------------------------
# Ensure project root for absolute imports
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(_current_dir)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.utils.skills_helpers import (
    _copiar_referencias,
    _evaluar_si_existe,
    _listar_skills_locales,
)
from backend.agent.utils.create_helpers import (
    stream_tool_calling_loop,
    stream_interview_loop,
    resolve_create_model_provider,
)
from backend.instances import agent
from backend.routes.file_text_extractor import extract_text_from_bytes
from backend.agent.utils.error_logger import log_error
from backend.routes.create.common import (
    _AGENT_TOOLS_PERMS,
    _FRIENDLY_ERROR,
    _SKILLS_DIR,
    _formatear_mensajes,
    _sse,
    _try_parse_json,
    router,
)

logger = logging.getLogger(__name__)


# ── Tool definition for interview ─────────────────────────────────────

_INTERVIEW_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "responder_interview",
        "description": (
            "Llamar cuando tengas suficiente información para crear la skill "
            "o cuando necesites hacer una pregunta al usuario. "
            "Los parámetros contienen la información estructurada de tu decisión."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["question", "create"],
                    "description": (
                        "'question' cuando necesitás más información del usuario. "
                        "'create' cuando ya tenés suficiente para diseñar la skill."
                    ),
                },
                "question": {
                    "type": "string",
                    "description": "Tu pregunta para el usuario (solo si action='question').",
                },
                "task": {
                    "type": "string",
                    "description": (
                        "Descripción detallada de lo que debe hacer la skill, "
                        "incluyendo señales de activación y pasos (solo si action='create')."
                    ),
                },
                "name": {
                    "type": "string",
                    "description": (
                        "Nombre exacto que dio el usuario para la skill. "
                        "Si no dio nombre, usar nombre corto con guiones (solo si action='create')."
                    ),
                },
                "triggers": {
                    "type": "string",
                    "description": (
                        "Palabras clave separadas por comas que activan la skill "
                        "(solo si action='create')."
                    ),
                },
                "not_triggers": {
                    "type": "string",
                    "description": (
                        "Lo que NO debe hacer la skill, contextos en los que NO activarse "
                        "(solo si action='create', opcional)."
                    ),
                },
                "refs": {
                    "type": "string",
                    "description": (
                        "Referencias, archivos o templates que mencionó el usuario "
                        "(solo si action='create', opcional)."
                    ),
                },
            },
            "required": ["action"],
        },
    },
}


# ── Streaming endpoint ───────────────────────────────────────────────


@router.post("/skill")
async def post_create_skill_stream(
    descripcion: str = Form(...),
    name: str | None = Form(None),
    mensajes: str | None = Form(None),
    model: str | None = Form(None),
    provider: str | None = Form(None),
    iterate: bool = Form(False),
    files: Optional[list[UploadFile]] = File(None),
):
    """Streaming endpoint to create a skill via an LLM interview.

    Streams Server-Sent Events back to the client as the interview progresses.

    Returns:
        A StreamingResponse with SSE events.
    """
    # Parse mensajes from JSON string
    try:
        mensajes_list = json.loads(mensajes) if mensajes else []
    except (json.JSONDecodeError, TypeError):
        mensajes_list = []

    # Extract text from uploaded files and append to latest user message
    archivos_raw: dict[str, bytes] = {}
    if files:
        extracted_parts: list[str] = []
        for f in files:
            filename = f.filename or "archivo"
            try:
                content = await f.read()
            except Exception as exc:
                log_error(str(exc), source="create.py:skill(file_read)")
                continue
            # Store raw bytes for later copying to references/
            archivos_raw[filename] = content
            result = extract_text_from_bytes(filename, content)
            text = (result.text or "").strip() if result.success else ""
            if text:
                extracted_parts.append(f"[Archivo adjunto: {filename}]\n```\n{text}\n```")
            else:
                extracted_parts.append(f"[Archivo adjunto: {filename}: no se pudo extraer texto]")

        if extracted_parts:
            # Append extracted text to the latest user message
            file_block = "\n\n".join(extracted_parts)
            if mensajes_list:
                last_user_idx = None
                for i in reversed(range(len(mensajes_list))):
                    if mensajes_list[i].get("role") == "user":
                        last_user_idx = i
                        break
                if last_user_idx is not None:
                    mensajes_list[last_user_idx]["content"] += f"\n\n{file_block}"
                else:
                    mensajes_list.append({"role": "user", "content": file_block})
            else:
                mensajes_list = [{"role": "user", "content": file_block}]

    logger.info(
        "POST /api/create/skill — descripcion='%s' name=%s mensajes=%d",
        descripcion, name,
        len(mensajes_list),
    )

    descripcion = descripcion.strip()
    nombre = name.strip() if name else None
    mensajes = mensajes_list

    if not descripcion:
        return StreamingResponse(
            iter([_sse({"type": "error", "content": "El campo 'descripcion' es obligatorio."})]),
            media_type="text/event-stream",
        )

    async def event_stream() -> AsyncGenerator[str, None]:
        """Generate SSE events for the skill creation flow."""
        _create_model, _create_provider = resolve_create_model_provider(model, provider)

        # ════════════════════════════════════════════════════════════════
        # FASE ITERACIÓN — si iterate=True, modificar creación existente
        # ════════════════════════════════════════════════════════════════
        if iterate:
            yield _sse({"type": "skill_action", "content": {"action": "iterating"}})

            try:
                iter_template = agent.prompt("iterate_skill")
            except FileNotFoundError:
                logger.exception("Prompt iterate_skill.md no encontrado.")
                yield _sse({"type": "error", "content": _FRIENDLY_ERROR})
                return

            # Buscar la skill existente por nombre
            skill_carpeta = str(_SKILLS_DIR / (nombre or "skill"))
            iter_prompt = iter_template.format(
                nombre=nombre or "(inferir)",
                carpeta=skill_carpeta,
                conversacion=_formatear_mensajes(mensajes),
            )

            try:
                tools = list(agent.tools.tools_registry(_AGENT_TOOLS_PERMS))
            except AttributeError as e:
                logger.exception("Error obteniendo tools: %s", e)
                yield _sse({"type": "error", "content": _FRIENDLY_ERROR})
                return

            msgs: list[dict[str, Any]] = [
                {"role": "system", "content": iter_prompt},
                {"role": "user", "content": mensajes[-1]["content"] if mensajes else "Modificá la skill."},
            ]

            async for event in stream_tool_calling_loop(
                msgs, tools, _FRIENDLY_ERROR, model=_create_model, provider=_create_provider
            ):
                yield _sse(event)
                if event["type"] == "error":
                    return

            yield _sse({"type": "skill_result", "content": {
                "status": "success",
                "message": f"Skill '{nombre}' modificada exitosamente.",
                "data": {"exist": "Sí", "skill": nombre, "skill_path": skill_carpeta},
            }})
            return

        # ════════════════════════════════════════════════════════════════
        # FASE 1: INTERVIEW — stream texto + tool responder_interview
        # ════════════════════════════════════════════════════════════════
        try:
            template = agent.prompt("interview_skill")
        except FileNotFoundError:
            logger.exception("Prompt interview_skill.md no encontrado.")
            yield _sse({"type": "error", "content": _FRIENDLY_ERROR})
            return

        prompt = template.format(
            descripcion=descripcion,
            nombre=nombre or "(inferir)",
            mensajes=_formatear_mensajes(mensajes),
        )

        collected_content = ""
        tool_calls_data = None

        _create_model, _create_provider = resolve_create_model_provider(model, provider)
        async for event in stream_interview_loop(
            prompt=prompt,
            interview_tool=_INTERVIEW_TOOL,
            friendly_error=_FRIENDLY_ERROR,
            model=_create_model,
            provider=_create_provider,
        ):
            if event["type"] == "chunk":
                collected_content += event.get("content", "")
                yield _sse(event)

            elif event["type"] == "_interview_args":
                tool_calls_data = event.get("content") or {}

            elif event["type"] == "aborted":
                yield _sse(event)
                return

            else:
                yield _sse(event)

        # ── Fallback: si no hubo tool call, intentar parsear JSON ──
        if not tool_calls_data:
            logger.warning("No tool call recibida. Content: %s", collected_content)
            parsed = _try_parse_json(collected_content)
            if parsed:
                tool_calls_data = parsed
            elif collected_content.strip():
                # El LLM respondió en texto natural sin llamar a la tool: esa es la
                # respuesta de la entrevista (el front ya la mostró). No se envía nada
                # extra al front; finaliza al terminar el stream.
                return
            else:
                yield _sse({"type": "error", "content": "El LLM no devolvió una respuesta válida."})
                return

        action = tool_calls_data.get("action")

        # ── QUESTION ──
        if action == "question":
            question_text = tool_calls_data.get("question", "")
            yield _sse({"type": "skill_action", "content": {"action": "question", "question": question_text}})
            return

        # ── CREATE ──
        if action != "create":
            logger.warning("Acción desconocida del LLM: %s", action)
            yield _sse({"type": "error", "content": _FRIENDLY_ERROR})
            return

        task = tool_calls_data.get("task", descripcion)
        name = nombre or tool_calls_data.get("name")
        refs = tool_calls_data.get("refs")

        # ════════════════════════════════════════════════════════════════
        # FASE 2: EVALUAR si ya existe una skill que cubra la tarea
        # ════════════════════════════════════════════════════════════════
        _SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        skills_locales = _listar_skills_locales()
        decision = await _evaluar_si_existe(task, skills_locales, model, provider)

        if decision and decision.get("exist") == "Sí":
            skill_name = decision.get("skill")
            yield _sse({"type": "skill_result", "content": {
                "status": "success",
                "message": f"Ya existe la skill '{skill_name}' que cubre esta tarea.",
                "data": {"exist": "Sí", "skill": skill_name},
            }})
            return

        # ════════════════════════════════════════════════════════════════
        # FASE 3: CREAR — ejecutar agente con tools, stremeando events
        # ════════════════════════════════════════════════════════════════
        yield _sse({"type": "skill_action", "content": {"action": "creating"}})

        # Build the generate prompt
        try:
            sys_prompt_template = agent.prompt("create_skill")
        except FileNotFoundError:
            logger.exception("Prompt create_skill.md no encontrado.")
            yield _sse({"type": "error", "content": _FRIENDLY_ERROR})
            return

        conversacion = _formatear_mensajes(mensajes)
        carpeta_skill = str(_SKILLS_DIR / (name or "skill"))
        sys_prompt = sys_prompt_template.format(
            nombre=name or "(inferir del contexto)",
            conversacion=conversacion,
            carpeta=carpeta_skill,
        )

        user_msg = "Ejecutá tu tarea. Creá el SKILL.md y los archivos necesarios. Cuando termines, indicame qué creaste."

        # ── 3a. Resolver tools ──
        try:
            tools = list(agent.tools.tools_registry(_AGENT_TOOLS_PERMS))
        except AttributeError as e:
            logger.exception("Error obteniendo tools: %s", e)
            yield _sse({"type": "error", "content": _FRIENDLY_ERROR})
            return

        # ── 3b. Loop de tool calling EXACTO ChatInterface (loop.py) ──
        msgs: list[dict[str, Any]] = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_msg},
        ]

        async for event in stream_tool_calling_loop(
            msgs, tools, _FRIENDLY_ERROR, model=_create_model, provider=_create_provider
        ):
            yield _sse(event)
            if event["type"] == "error":
                return

        # ════════════════════════════════════════════════════════════════
        # FASE 4: BUSCAR lo que creó el agente
        # ════════════════════════════════════════════════════════════════
        skills_actualizadas = _listar_skills_locales()
        nuevas = [s for s in skills_actualizadas if s["name"] not in {old["name"] for old in skills_locales}]

        skill_dir = None
        skill_name_creado = None

        if name:
            skill_dir = _SKILLS_DIR / name
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").is_file():
                skill_name_creado = name
        elif nuevas:
            nueva = nuevas[0]
            skill_name_creado = nueva["name"]
            skill_dir = _SKILLS_DIR / skill_name_creado

        # Copiar referencias
        if skill_dir and skill_name_creado:
            _copiar_referencias(skill_dir, mensajes, refs, archivos_raw=archivos_raw)

        if skill_name_creado and skill_dir:
            yield _sse({"type": "skill_result", "content": {
                "status": "success",
                "message": f"Skill '{skill_name_creado}' creada exitosamente.",
                "data": {"exist": "No", "skill": skill_name_creado, "skill_dir": str(skill_dir)},
            }})
        else:
            # El agente terminó la creación (escribió los archivos). Mostrar el cartel de éxito.
            nombre_creado = skill_name_creado or name or "skill"
            yield _sse({"type": "skill_result", "content": {
                "status": "success",
                "message": f"Skill '{nombre_creado}' creada exitosamente.",
                "data": {"exist": "No", "skill": nombre_creado, "skill_dir": str(skill_dir or _SKILLS_DIR / nombre_creado)},
            }})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
