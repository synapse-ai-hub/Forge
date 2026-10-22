"""Endpoint POST /api/create/agent — crear agentes especializados."""

from __future__ import annotations

import logging
import os
import sys
import time as _time
from typing import Any, AsyncGenerator

from fastapi.responses import StreamingResponse

# ---------------------------------------------------------------------------
# Ensure project root for absolute imports
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(_current_dir)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.utils.create_helpers import (
    build_resource_context,
    stream_tool_calling_loop,
    stream_interview_loop,
    resolve_create_model_provider,
)
from backend.instances import agent
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.creators import track_creator_run
from backend.routes.create.common import (
    _AGENT_TOOLS_PERMS,
    _AGENTS_DIR,
    _FRIENDLY_ERROR_AGENT,
    _formatear_mensajes,
    _sse,
    _try_parse_json,
    CreateAgentRequest,
    router,
)

logger = logging.getLogger(__name__)


# Tool schema para la entrevista de agentes
_AGENT_INTERVIEW_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "responder_interview_agent",
        "description": (
            "Llamar cuando tengas suficiente información para crear el agente "
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
                        "'create' cuando ya tenés suficiente para diseñar el agente."
                    ),
                },
                "question": {
                    "type": "string",
                    "description": "Tu pregunta para el usuario (solo si action='question').",
                },
                "task": {
                    "type": "string",
                    "description": (
                        "Descripción del rol del agente, su propósito y restricciones "
                        "(solo si action='create')."
                    ),
                },
                "name": {
                    "type": "string",
                    "description": (
                        "Nombre exacto del archivo del agente (sin extensión, "
                        "snake_case). Si no dio nombre, inferir del contexto "
                        "(solo si action='create')."
                    ),
                },
                "tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Lista de tools que el agente debe tener habilitadas "
                        "(solo si action='create')."
                    ),
                },
                "skills": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Lista de skills que el agente debe tener habilitadas "
                        "(solo si action='create')."
                    ),
                },
                "temperature": {
                    "type": "number",
                    "description": "Temperature para el agente (solo si action='create'). Default: 0.0.",
                },
                "top_p": {
                    "type": "number",
                    "description": "Top_p para el agente (solo si action='create'). Default: 0.5.",
                },
            },
            "required": ["action"],
        },
    },
}


@router.post("/agent")
async def post_create_agent_stream(req: CreateAgentRequest) -> StreamingResponse:
    """Stream the creation of a specialized agent via an LLM interview.

    Same contract as ``POST /api/create/skill`` but emits ``agent_action``
    and ``agent_result`` events instead of ``skill_action`` / ``skill_result``.

    Args:
        req: The creation request.

    Returns:
        A StreamingResponse with SSE events.
    """
    descripcion = req.descripcion.strip()
    nombre = req.name.strip() if req.name else None
    mensajes = req.mensajes or []

    if not descripcion:
        return StreamingResponse(
            iter([_sse({"type": "error", "content": "El campo 'descripcion' es obligatorio."})]),
            media_type="text/event-stream",
        )

    async def event_stream() -> AsyncGenerator[str, None]:
        """Generate SSE events for the agent creation flow.

        Yields:
            SSE ``data:`` lines.
        """
        _create_model, _create_provider = resolve_create_model_provider(req.model, req.provider)

        # ════════════════════════════════════════════════════════════════
        # FASE ITERACIÓN — si iterate=True, modificar creación existente
        # ════════════════════════════════════════════════════════════════
        if req.iterate:
            yield _sse({"type": "agent_action", "content": {"action": "iterating"}})

            recursos = await build_resource_context(
                agentes=req.agentes, tools=req.tools, tool_args=req.tool_args,
                skills=req.skills, rag=req.rag, with_skills=True, with_mcp=True,
            )

            agent_carpeta = str(_AGENTS_DIR)
            try:
                iter_prompt = agent.prompt(
                    "iterate_agent",
                    nombre=nombre or "(inferir)",
                    carpeta=agent_carpeta,
                    conversacion=_formatear_mensajes(mensajes),
                    **recursos,
                )
            except FileNotFoundError:
                logger.exception("Prompt iterate_agent.jinja no encontrado.")
                yield _sse({"type": "error", "content": _FRIENDLY_ERROR_AGENT})
                return

            try:
                tools = list(agent.tools.tools_registry(_AGENT_TOOLS_PERMS))
            except AttributeError as e:
                logger.exception("Error obteniendo tools: %s", e)
                yield _sse({"type": "error", "content": _FRIENDLY_ERROR_AGENT})
                return

            msgs: list[dict[str, Any]] = [
                {"role": "system", "content": iter_prompt},
                {"role": "user", "content": mensajes[-1]["content"] if mensajes else "Modificá el agente."},
            ]

            async for event in stream_tool_calling_loop(
                msgs, tools, _FRIENDLY_ERROR_AGENT, model=_create_model, provider=_create_provider
            ):
                yield _sse(event)
                if event["type"] == "error":
                    return

            yield _sse({"type": "agent_result_final", "content": {
                "status": "success",
                "message": f"Agente '{nombre}' modificado exitosamente.",
                "data": {"exist": "Sí", "agent": nombre, "agent_path": agent_carpeta},
            }})
            return

        # ════════════════════════════════════════════════════════════════
        # FASE 1: EVALUAR — ¿ya existe un agente que cubra esto?
        # ════════════════════════════════════════════════════════════════
        try:
            _AGENTS_DIR.mkdir(parents=True, exist_ok=True)
            agentes_locales = _listar_agentes_locales()
            if nombre:
                for ag in agentes_locales:
                    if ag["name"] == nombre:
                        yield _sse({"type": "agent_result_final", "content": {
                            "status": "success",
                            "message": f"Ya existe un agente con el nombre '{nombre}'.",
                            "data": {"exist": "Sí", "agent": nombre},
                        }})
                        return
        except Exception as e:
            logger.exception("Error en evaluación inicial: %s", e)

        # ════════════════════════════════════════════════════════════════
        # FASE 2: ENTREVISTA — stream texto + tool responder_interview
        # ════════════════════════════════════════════════════════════════
        try:
            prompt = agent.prompt(
                "interview_agent",
                descripcion=descripcion,
                nombre=nombre or "(inferir)",
                mensajes=_formatear_mensajes(mensajes),
                **await build_resource_context(
                    agentes=req.agentes, tools=req.tools, tool_args=req.tool_args,
                    skills=req.skills, rag=req.rag, with_skills=True, with_mcp=True,
                ),
            )
        except FileNotFoundError:
            logger.exception("Prompt interview_agent.jinja no encontrado.")
            yield _sse({"type": "error", "content": _FRIENDLY_ERROR_AGENT})
            return

        collected_content = ""
        tool_calls_data = None

        _create_model, _create_provider = resolve_create_model_provider(req.model, req.provider)
        async for event in stream_interview_loop(
            prompt=prompt,
            interview_tool=_AGENT_INTERVIEW_TOOL,
            friendly_error=_FRIENDLY_ERROR_AGENT,
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
                return
            else:
                yield _sse({"type": "error", "content": "El LLM no devolvió una respuesta válida."})
                return

        action = tool_calls_data.get("action")

        # ── QUESTION ──
        if action == "question":
            question_text = tool_calls_data.get("question", "")
            yield _sse({"type": "agent_action", "content": {"action": "question", "question": question_text}})
            return

        # ── CREATE ──
        if action != "create":
            logger.warning("Acción desconocida del LLM: %s", action)
            yield _sse({"type": "error", "content": _FRIENDLY_ERROR_AGENT})
            return

        task = tool_calls_data.get("task", descripcion)
        name = nombre or tool_calls_data.get("name")
        llm_tools = tool_calls_data.get("tools") or []
        llm_skills = tool_calls_data.get("skills") or []
        temperature = tool_calls_data.get("temperature", 0.0)
        top_p = tool_calls_data.get("top_p", 0.5)

        # ════════════════════════════════════════════════════════════════
        # FASE 3: CREAR — ejecutar agente con tools (mismo loop que /skill)
        # ════════════════════════════════════════════════════════════════
        yield _sse({"type": "agent_action", "content": {"action": "creating"}})

        recursos = await build_resource_context(
            agentes=req.agentes, tools=req.tools, tool_args=req.tool_args,
            skills=req.skills, rag=req.rag, with_skills=True, with_mcp=True,
        )

        conversacion = _formatear_mensajes(mensajes) if mensajes else f"**Usuario**: {task}"
        carpeta = str(_AGENTS_DIR)
        tools_text = "\n".join(f"- {t}" for t in llm_tools) if llm_tools else "(ninguna declarada por el usuario, inferir las mínimas)"
        skills_text = "\n".join(f"- {s}" for s in llm_skills) if llm_skills else "(ninguna declarada por el usuario, inferir las mínimas)"
        try:
            sys_prompt = agent.prompt(
                "create_agent",
                nombre=name or "(inferir del contexto)",
                conversacion=conversacion,
                carpeta=carpeta,
                tools_seleccionadas=tools_text,
                skills_seleccionadas=skills_text,
                **recursos,
            )
        except FileNotFoundError:
            logger.exception("Prompt create_agent.jinja no encontrado.")
            yield _sse({"type": "error", "content": _FRIENDLY_ERROR_AGENT})
            return

        user_msg = (
            "Creá el agente. Pasos OBLIGATORIOS en orden: "
            "1) Leé las tools y skills disponibles con list_dir. "
            "2) Seleccioná las mínimas necesarias para el rol. "
            "3) Verificá con shell lo que el agente va a usar (librerías, comandos, rutas). "
            "4) Escribí el archivo .md con write en la carpeta de agents. "
            "5) Confirmame qué creaste."
        )

        # ── 3a. Resolver tools ──
        try:
            tools = list(agent.tools.tools_registry(_AGENT_TOOLS_PERMS))
        except AttributeError as e:
            logger.exception("Error obteniendo tools: %s", e)
            yield _sse({"type": "error", "content": _FRIENDLY_ERROR_AGENT})
            return

        # ── 3b. Loop de tool calling EXACTO ChatInterface (loop.py) ──
        msgs: list[dict[str, Any]] = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_msg},
        ]

        async for event in stream_tool_calling_loop(
            msgs, tools, _FRIENDLY_ERROR_AGENT, model=_create_model, provider=_create_provider
        ):
            yield _sse(event)
            if event["type"] == "error":
                return

        # ════════════════════════════════════════════════════════════════
        # FASE 4: BUSCAR lo que creó el agente
        # ════════════════════════════════════════════════════════════════
        if name:
            agent_path = _AGENTS_DIR / f"{name}.md"
            if agent_path.is_file():
                yield _sse({"type": "agent_result_final", "content": {
                    "status": "success",
                    "message": f"Agente '{name}' creado exitosamente.",
                    "data": {"exist": "No", "agent": name, "agent_path": str(agent_path)},
                }})
                return

        # Fallback: escanear agentes recién creados
        cutoff = _time.time() - 300  # 5 min
        candidatos = []
        if _AGENTS_DIR.is_dir():
            for entry in _AGENTS_DIR.iterdir():
                if not entry.is_file() or not entry.name.endswith(".md"):
                    continue
                try:
                    mtime = entry.stat().st_mtime
                    if mtime >= cutoff:
                        candidatos.append(entry.stem)
                except Exception:
                    continue
        if candidatos:
            nueva_nombre = candidatos[0]
            agent_path = _AGENTS_DIR / f"{nueva_nombre}.md"
            yield _sse({"type": "agent_result_final", "content": {
                "status": "success",
                "message": f"Agente '{nueva_nombre}' creado exitosamente.",
                "data": {"exist": "No", "agent": nueva_nombre, "agent_path": str(agent_path)},
            }})
            return

        yield _sse({"type": "agent_result_final", "content": {
            "status": "error",
            "message": f"No se pudo verificar la creación del agente '{name or 'agente'}'.",
            "data": {"exist": "No", "agent": name or "agente", "agent_path": str(_AGENTS_DIR / f"{name or 'agente'}.md")},
        }})

    return StreamingResponse(
        track_creator_run("agent", req, event_stream()),
        media_type="text/event-stream",
    )


def _listar_agentes_locales() -> list[dict[str, str]]:
    """List local agents from the agents directory.

    Returns:
        List of dicts with ``name`` and ``description`` keys.
    """
    import yaml as _yaml

    if not _AGENTS_DIR.is_dir():
        return []

    result: list[dict[str, str]] = []
    for entry in sorted(_AGENTS_DIR.iterdir()):
        if not entry.is_file() or not entry.name.endswith(".md"):
            continue
        try:
            with open(entry, encoding="utf-8-sig") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            continue

        fm_data: dict[str, Any] = {}
        if content.lstrip().startswith("---"):
            lines = content.splitlines()
            end = None
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    end = i
                    break
            if end is not None:
                try:
                    fm_data = _yaml.safe_load("\n".join(lines[1:end])) or {}
                except _yaml.YAMLError:
                    fm_data = {}

        name = fm_data.get("name", entry.stem)
        description = fm_data.get("description", "")
        result.append({"name": name, "description": description})

    return result
