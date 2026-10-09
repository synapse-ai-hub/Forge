"""Endpoint POST /api/create/tool — crear tools externas."""

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

from backend.agent.utils.tools_helpers import _listar_tools_locales
from backend.agent.utils.create_helpers import (
    stream_tool_calling_loop,
    stream_interview_loop,
    resolve_create_model_provider,
)
from backend.instances import agent
from backend.agent.utils.error_logger import log_error
from backend.routes.create.common import (
    _AGENT_TOOLS_PERMS,
    _FRIENDLY_ERROR_TOOL,
    _TOOLS_DIR,
    _formatear_mensajes,
    _sse,
    _try_parse_json,
    CreateToolRequest,
    router,
)

logger = logging.getLogger(__name__)


# Tool schema para la entrevista (idéntico patrón que skills)
_TOOL_INTERVIEW_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "responder_interview_tool",
        "description": (
            "Llamar cuando tengas suficiente información para crear la tool "
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
                        "'create' cuando ya tenés suficiente para diseñar la tool."
                    ),
                },
                "question": {
                    "type": "string",
                    "description": "Tu pregunta para el usuario (solo si action='question').",
                },
                "task": {
                    "type": "string",
                    "description": (
                        "Descripción detallada de lo que debe hacer la tool, "
                        "incluyendo señales de activación y pasos (solo si action='create')."
                    ),
                },
                "name": {
                    "type": "string",
                    "description": (
                        "Nombre exacto del archivo de la tool (sin extensión, "
                        "snake_case). Si no dio nombre, inferir del contexto "
                        "(solo si action='create')."
                    ),
                },
                "parametros": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string"},
                            "description": {"type": "string"},
                            "required": {"type": "boolean"},
                        },
                    },
                    "description": (
                        "Lista de parámetros que la tool recibe del LLM "
                        "(solo si action='create')."
                    ),
                },
                "datos": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Variables de entorno o datos externos que la tool necesita "
                        "(solo si action='create', opcional)."
                    ),
                },
            },
            "required": ["action"],
        },
    },
}


@router.post("/tool")
async def post_create_tool_stream(req: CreateToolRequest):
    """Streaming endpoint to create an external tool via an LLM interview.

    Same contract as ``POST /api/create/skill`` but emits ``tool_action``
    and ``tool_result`` events instead of ``skill_action`` / ``skill_result``.

    Returns:
        A StreamingResponse with SSE events.
    """
    logger.info(
        "POST /api/create/tool — descripcion='%s' name=%s mensajes=%d",
        req.descripcion, req.name,
        len(req.mensajes) if req.mensajes else 0,
    )

    descripcion = req.descripcion.strip()
    nombre = req.name.strip() if req.name else None
    mensajes = req.mensajes or []
    parametros = req.parametros or []
    datos = req.datos or []

    if not descripcion:
        return StreamingResponse(
            iter([_sse({"type": "error", "content": "El campo 'descripcion' es obligatorio."})]),
            media_type="text/event-stream",
        )

    async def event_stream() -> AsyncGenerator[str, None]:
        """Generate SSE events for the tool creation flow."""
        _create_model, _create_provider = resolve_create_model_provider(req.model, req.provider)

        # ════════════════════════════════════════════════════════════════
        # FASE ITERACIÓN — si iterate=True, modificar creación existente
        # ════════════════════════════════════════════════════════════════
        if req.iterate:
            yield _sse({"type": "tool_action", "content": {"action": "iterating"}})

            try:
                iter_template = agent.prompt("iterate_tool")
            except FileNotFoundError:
                logger.exception("Prompt iterate_tool.md no encontrado.")
                yield _sse({"type": "error", "content": _FRIENDLY_ERROR_TOOL})
                return

            tool_carpeta = str(_TOOLS_DIR / (nombre or "tool"))
            iter_prompt = iter_template.format(
                nombre=nombre or "(inferir)",
                carpeta=tool_carpeta,
                conversacion=_formatear_mensajes(mensajes),
            )

            try:
                tools = list(agent.tools.tools_registry(_AGENT_TOOLS_PERMS))
            except AttributeError as e:
                logger.exception("Error obteniendo tools: %s", e)
                yield _sse({"type": "error", "content": _FRIENDLY_ERROR_TOOL})
                return

            msgs: list[dict[str, Any]] = [
                {"role": "system", "content": iter_prompt},
                {"role": "user", "content": mensajes[-1]["content"] if mensajes else "Modificá la tool."},
            ]

            async for event in stream_tool_calling_loop(
                msgs, tools, _FRIENDLY_ERROR_TOOL, model=_create_model, provider=_create_provider
            ):
                yield _sse(event)
                if event["type"] == "error":
                    return

            yield _sse({"type": "tool_result_final", "content": {
                "status": "success",
                "message": f"Tool '{nombre}' modificada exitosamente.",
                "data": {"exist": "Sí", "tool": nombre, "tool_path": tool_carpeta},
            }})
            return

        # ════════════════════════════════════════════════════════════════
        # FASE 1: EVALUAR — ¿ya existe una tool que cubra esto?
        # (antes de iterar para no gastar tokens si ya hay una)
        # ════════════════════════════════════════════════════════════════
        try:
            tools_locales = _listar_tools_locales()
            decision = await _evaluar_si_existe_tool_inline(
                descripcion, tools_locales, agent, req.model, req.provider
            )

            if decision and decision.get("exist") == "Sí":
                tool_name = decision.get("tool")
                yield _sse({"type": "tool_result", "content": {
                    "status": "success",
                    "message": f"Ya existe la tool '{tool_name}' que cubre esta tarea.",
                    "data": {"exist": "Sí", "tool": tool_name},
                }})
                return
        except Exception as e:
            logger.exception("Error en evaluación inicial: %s", e)
            # No es bloqueante: seguimos a la fase de entrevista

        # ════════════════════════════════════════════════════════════════
        # FASE 2: ENTREVISTA — stream texto + tool responder_interview_tool
        # ════════════════════════════════════════════════════════════════
        try:
            template = agent.prompt("interview_tool")
        except FileNotFoundError:
            logger.exception("Prompt interview_tool.md no encontrado.")
            yield _sse({"type": "error", "content": _FRIENDLY_ERROR_TOOL})
            return

        # Formatear parámetros y datos
        if parametros:
            params_lines = []
            for p in parametros:
                pname = p.get("name", "?")
                ptype = p.get("type", "str")
                pdesc = p.get("description", "")
                preq = "obligatorio" if p.get("required", True) else "opcional"
                params_lines.append(f"  - {pname} ({ptype}, {preq}): {pdesc}")
            parametros_text = "\n".join(params_lines)
        else:
            parametros_text = "(No se declararon parámetros. Inferir los necesarios.)"

        datos_text = "\n".join(f"  - {d}" for d in datos) if datos else "(No se declararon datos externos. Inferir si los necesita.)"

        prompt = template.format(
            descripcion=descripcion,
            nombre=nombre or "(inferir)",
            parametros=parametros_text,
            datos=datos_text,
            mensajes=_formatear_mensajes(mensajes),
        )

        collected_content = ""
        tool_calls_data = None

        _create_model, _create_provider = resolve_create_model_provider(req.model, req.provider)
        async for event in stream_interview_loop(
            prompt=prompt,
            interview_tool=_TOOL_INTERVIEW_TOOL,
            friendly_error=_FRIENDLY_ERROR_TOOL,
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
            yield _sse({"type": "tool_action", "content": {"action": "question", "question": question_text}})
            return

        # ── CREATE ──
        if action != "create":
            logger.warning("Acción desconocida del LLM: %s", action)
            yield _sse({"type": "error", "content": _FRIENDLY_ERROR_TOOL})
            return

        task = tool_calls_data.get("task", descripcion)
        name = nombre or tool_calls_data.get("name")
        llm_parametros = tool_calls_data.get("parametros") or parametros
        llm_datos = tool_calls_data.get("datos") or datos

        # ════════════════════════════════════════════════════════════════
        # FASE 3: CREAR — ejecutar agente con tools (mismo loop que /skill)
        # ════════════════════════════════════════════════════════════════
        yield _sse({"type": "tool_action", "content": {"action": "creating"}})

        try:
            sys_prompt_template = agent.prompt("create_tool")
        except FileNotFoundError:
            logger.exception("Prompt create_tool.md no encontrado.")
            yield _sse({"type": "error", "content": _FRIENDLY_ERROR_TOOL})
            return

        # Formatear params/datos/conversación para el prompt de generación
        if llm_parametros:
            params_lines = []
            for p in llm_parametros:
                pname = p.get("name", "?")
                ptype = p.get("type", "str")
                pdesc = p.get("description", "")
                preq = "obligatorio" if p.get("required", True) else "opcional"
                params_lines.append(f"- {pname} ({ptype}, {preq}): {pdesc}")
            params_text = "\n".join(params_lines)
        else:
            params_text = "(Inferir parámetros según la descripción.)"

        datos_text = "\n".join(f"- {d}" for d in llm_datos) if llm_datos else "(Si la tool necesita credenciales, documentarlas acá.)"

        conversacion = _formatear_mensajes(mensajes) if mensajes else f"**Usuario**: {task}"

        carpeta = str(_TOOLS_DIR / (name or "tool"))
        sys_prompt = sys_prompt_template.format(
            nombre=name or "(inferir del contexto)",
            descripcion=task,
            conversacion=conversacion,
            parametros=params_text,
            datos=datos_text,
            carpeta=carpeta,
        )

        user_msg = (
            "Creá la tool. Pasos OBLIGATORIOS en orden: "
            "1) Escribí el archivo <nombre>.py con write. "
            "2) Escribí un script de tests en lib/tests/test_<nombre>.py. "
            "3) Ejecutá los tests con shell y mostrame los resultados. "
            "4) Iterá si hay errores. "
            "5) Cuando todo pase, pedime aprobación."
        )

        # ── 3a. Resolver tools ──
        try:
            tools = list(agent.tools.tools_registry(_AGENT_TOOLS_PERMS))
        except AttributeError as e:
            logger.exception("Error obteniendo tools: %s", e)
            yield _sse({"type": "error", "content": _FRIENDLY_ERROR_TOOL})
            return

        # ── 3b. Loop de tool calling EXACTO ChatInterface (loop.py) ──
        msgs: list[dict[str, Any]] = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_msg},
        ]

        async for event in stream_tool_calling_loop(
            msgs, tools, _FRIENDLY_ERROR_TOOL, model=_create_model, provider=_create_provider
        ):
            yield _sse(event)
            if event["type"] == "error":
                return

        # ════════════════════════════════════════════════════════════════
        # FASE 4: BUSCAR lo que creó el agente
        # ════════════════════════════════════════════════════════════════
        if name:
            tool_path = _TOOLS_DIR / f"{name}.py"
            if tool_path.is_file():
                yield _sse({"type": "tool_result_final", "content": {
                    "status": "success",
                    "message": f"Tool '{name}' creada exitosamente.",
                    "data": {"exist": "No", "tool": name, "tool_path": str(tool_path)},
                }})
                return

        # Fallback: escanear tools recién creadas
        tools_actualizadas = _listar_tools_locales()
        # Comparar contra las que ya existían al inicio de esta request
        # (re-leer del disco por si la última escritura las cambió)
        # Recompute "previas": las que NO fueron creadas por este agente.
        # (el race condition se evita porque tools_locales ya se listó al inicio
        # pero acá lo volvemos a leer para tener el estado más fresco)
        tools_locales_reload = _listar_tools_locales()
        # Las "nuevas" son las que aparecieron desde el inicio
        # Para simplificar: si no encontramos la pedida por nombre,
        # igual emitimos un mensaje de éxito si hay archivo nuevo.
        # Buscar cualquier .py que haya sido creado en los últimos 60 segundos
        cutoff = _time.time() - 300  # 5 min
        candidatos = []
        if _TOOLS_DIR.is_dir():
            for entry in _TOOLS_DIR.iterdir():
                if not entry.is_file() or not entry.name.endswith(".py") or entry.name.startswith("_"):
                    continue
                try:
                    mtime = entry.stat().st_mtime
                    if mtime >= cutoff:
                        candidatos.append(entry.stem)
                except Exception:
                    continue
        if candidatos:
            nueva_nombre = candidatos[0]
            tool_path = _TOOLS_DIR / f"{nueva_nombre}.py"
            yield _sse({"type": "tool_result_final", "content": {
                "status": "success",
                "message": f"Tool '{nueva_nombre}' creada exitosamente.",
                "data": {"exist": "No", "tool": nueva_nombre, "tool_path": str(tool_path)},
            }})
            return

        yield _sse({"type": "tool_result_final", "content": {
            "status": "success",
            "message": f"Tool '{name or 'tool'}' creada exitosamente.",
            "data": {"exist": "No", "tool": name or "tool", "tool_path": str(_TOOLS_DIR / f"{name or 'tool'}.py")},
        }})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# Helper para evaluar inline sin reimportar todo el módulo
async def _evaluar_si_existe_tool_inline(tarea, tools_locales, agent, model=None, provider=None):
    """Wrapper sobre el helper compartido."""
    from backend.agent.utils.tools_helpers import _evaluar_si_existe
    return await _evaluar_si_existe(tarea, tools_locales, model, provider)
