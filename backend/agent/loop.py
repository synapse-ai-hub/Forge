"""Agent loop — iterative loop with native tool calling.

Pattern
-------
1. Create/recover session in SQLite.
2. Load conversation history from SQLite.
3. Build system prompt (base + skills).
4. Resolve tools from ``agent.tools.tools_registry``.
5. ``while True``:
   a. Call LLM with ``messages`` + ``tools`` (no streaming).
   b. If response has ``tool_calls`` → execute each tool,
      append results as ``role: "tool"`` messages, continue.
   c. If no ``tool_calls`` → yield content as chunk and break (an empty
      response is retried up to ``MAX_EMPTY_RESPONSE_RETRIES`` times).
6. Persist every message in SQLite.

All OpenAI-compatible providers (``client.chat.completions.create``) and Ollama
(``ollama.chat``) support the ``tools`` parameter with JSON Schema
definitions. Tool calls arrive as structured data, not as text to parse.

LLM streaming errors are classified (rate-limit / transient / fatal) and
rate-limit or transient failures are retried with exponential back-off
(up to ``MAX_LLM_RETRIES`` retries); fatal errors and user cancellation
are never retried.

Sub-agent delegation
--------------------
The ``task`` tool resolves a sub-agent's system prompt and permissions
from its markdown, creates an integrated child session (``parent_id``),
and calls ``run`` again with the resolved arguments. This produces a
``run`` inside ``run`` (recursion) where each level is isolated by its
own session. The parent loop emits ``subagent_call`` / ``subagent_result``
SSE events (collapsible) around the delegation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time as _time
import yaml
from typing import Any, AsyncGenerator

import urllib.request
from dotenv import load_dotenv

# Custom SUBAGENT log level (registered in subagent_logger.py, imported via agent/__init__.py)

# ---------------------------------------------------------------------------
# Ensure the project root is in sys.path so absolute imports (backend.*)
# resolve correctly regardless of how the file is invoked.
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from datetime import datetime
from backend.agent.utils.error_logger import log_error, set_error_context, reset_error_context, get_error_context
from backend.agent.utils.skill_loader import format_skills_section
from backend.agent.permissions import (
    list_agents,
    get_tool_permissions,
    get_skill_permissions,
    get_agent_parameters,
)
from backend.agent.utils.clean_memory import liberar_modelo
from backend.agent.utils import provider_keys
from backend.agent.utils.model_catalog import get_provider_api_type
from backend.instances import agent, session_manager
from backend.agent.utils.loop_helpers import (
    build_initial_messages,
    build_system_prompt,
    execute_tool,
    fetch_context_window_turns,
)
from backend.agent.utils.model_resolver import (
    ensure_context_window,
    ollama_default_context,
)
from backend.agent.utils.spend_handler import check_spend_limit
from backend.agent.utils.rate_limit_handler import (
    classify_error_category,
    get_retry_delay,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config endpoint
# ---------------------------------------------------------------------------

_CONFIG_BASE_URL = os.getenv("CONFIG_BASE_URL", "http://127.0.0.1:8000/api/config")

MAX_ITERATIONS = 25
"""Maximum tool-calling iterations before forcing a response (safety net)."""

MAX_SUBAGENT_DEPTH = 3
"""Maximum nesting depth for sub-agent delegation (recursion guard)."""

MAX_EMPTY_RESPONSE_RETRIES = 2
"""Maximum retries when the final LLM response is empty (no content, no tool_calls)."""

MAX_LLM_RETRIES = 5
"""Maximum retries for the LLM streaming call on rate-limit/transient errors.

The first attempt plus up to ``MAX_LLM_RETRIES`` retries, with exponential
back-off waits of 2s, 4s, 8s, 16s and 32s (62s total).
"""

LLM_BACKOFF_BASE_SECONDS = 2.0
"""Base delay (seconds) for the exponential back-off between LLM retries."""


def _resolve_tool_api_type(effective_provider: str | None) -> str:
    """Resolve the API type used to pick the tool-message format.

    Reads the synced catalog first and falls back to the curated
    ``provider_keys.PROVIDER_REGISTRY`` when the catalog has no rows
    for the provider (sync never ran).

    Args:
        effective_provider: Provider name or ``None``.

    Returns:
        ``"openai-compatible"``, ``"google"``, ``"ollama"`` or
        ``"unknown"``.
    """
    try:
        api_type = get_provider_api_type(effective_provider or "")
    except Exception:
        api_type = "unknown"
    if api_type == "unknown":
        try:
            info = provider_keys.PROVIDER_REGISTRY.get(
                (effective_provider or "").strip(), {}
            )
            api_type = str(info.get("api_type") or "unknown")
        except Exception:
            api_type = "unknown"
    return api_type

# Tool schema for the router agent (agent_name=None). Fallback only: the
# router's guaranteed tools (task, help, search_memory, read, websearch,
# webfetch) are normally resolved from the tools registry via merged
# permissions. config.yaml can ADD extra tools but never remove these.
_ROUTER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "task",
            "description": "Delegate work to a sub-agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "description": "Name of the sub-agent to delegate to."
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Detailed task description for the sub-agent (user message)."
                    }
                },
                "required": ["agent_name", "prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "help",
            "description": "Lee la documentación interna del agente sobre su funcionamiento.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": (
                "Busca en conversaciones anteriores del usuario (memoria de "
                "largo plazo). Úsala cuando el usuario pregunte por "
                "conversaciones previas o mencione información que no está "
                "en la sesión actual."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Consulta en lenguaje natural sobre conversaciones pasadas."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Cantidad máxima de resultados (default 5)."
                    }
                },
                "required": ["query"]
            }
        }
    }
]
"""Tool schema list for the router agent (``task`` + ``help`` + ``search_memory``)."""


def _load_router_permissions() -> dict | None:
    """Load the router's permissions from ``~/.config/synapseForge/config.yaml``.

    Reads the ``permissions`` section (same structure as agent frontmatter:
    ``tool``, ``skill`` and ``task`` sub-blocks).

    Returns:
        The ``permissions`` dict, or ``None`` if the file does not exist,
        has no ``permissions`` section, or cannot be read.
    """
    from backend.agent.utils.config_dir import get_config_dir

    cfg_path = get_config_dir() / "config.yaml"
    if not cfg_path.is_file():
        return None
    try:
        with open(cfg_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        log_error(str(exc), source="loop.py:_load_router_permissions")
        return None
    perms = data.get("permissions")
    return perms if isinstance(perms, dict) else None


def _read_param_override(key: str) -> Any:
    """Read a global advanced-parameter override from ``config_kv``.

    Reads the value persisted by ``POST /api/config/models/select``
    (keys ``param_temperature``, ``param_top_p``, ``param_reasoning``,
    ``param_budget_tokens``, ``param_response_format``).
    The literal string ``"null"`` (or a missing/unparseable key) means
    "default" → returns ``None`` so the caller falls back to the next
    level of the precedence chain.

    Args:
        key: ``config_kv`` key to read.

    Returns:
        The parsed override value (``float`` for temperature/top_p,
        ``bool`` for reasoning, ``str`` for response_format) or ``None``
        when there is no explicit override.
    """
    try:
        raw = session_manager.get_config(key)
    except Exception as exc:
        logger.warning("No se pudo leer el parámetro %s: %s", key, exc)
        return None
    if raw is None or raw.strip().lower() == "null":
        return None
    try:
        if key == "param_reasoning":
            # Can be boolean (old format) or string (new format: "on"/"off"/"low"/"medium"/"high"/"max"/"default"/"none"/"0"/"1024"/etc.)
            val = raw.strip().lower()
            if val in ("true", "on"):
                return "on"
            elif val in ("false", "off"):
                return "off"
            else:
                return raw.strip()
        if key == "param_response_format":
            return raw.strip().lower()
        return float(raw)
    except (TypeError, ValueError):
        return None


class AgentLoop:
    """Agent loop with native tool calling.

    The loop iterates calling the LLM with available tools. The LLM
    autonomously decides whether to call a tool or produce the final
    response. The loop only ends when the LLM returns no ``tool_calls``.

    Attributes:
        max_iterations: Max tool-calling iterations before forced response.
    """

    def __init__(
        self,
        agent: Any,
        session_manager: Any,
        max_iterations: int = MAX_ITERATIONS,
    ) -> None:
        """Initialise the agent loop.

        Args:
            agent: ``Agent`` instance.
            session_manager: ``SessionManager`` for SQLite.
            max_iterations: Max tool-calling iterations.
        """
        self.max_iterations = max_iterations

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        session_id: str,
        user_message: str,
        file_contents: list[tuple[str, str]] | None = None,
        stream_cancel_event: asyncio.Event | None = None,
        system_prompt: str | None = None,
        tool_permissions: dict | None = None,
        skill_permissions: dict | None = None,
        parameters: dict | None = None,
        agent_name: str | None = None,
        depth: int = 0,
        parent_id: str | None = None,
        parent_model: str | None = None,
        parent_provider: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Run the agent loop for a single user message.

        Args:
            session_id: Unique session identifier.
            user_message: User message text.
            file_contents: Optional list of (filename, text) attachments.
            stream_cancel_event: Event to cancel streaming mid-response.
            system_prompt: Pre-resolved system prompt. If ``None``, it is
                built for the router (or for *agent_name* if provided).
            tool_permissions: Tool permission dict (from an agent's
                frontmatter). ``None``/``{}`` → no tools (deny by default).
            skill_permissions: Skill permission dict. ``None``/``{}`` → no
                skills (deny by default).
            parameters: Model/agent parameters (from frontmatter). May include
                ``model`` and ``provider`` overrides.
            agent_name: Sub-agent name being executed (``None`` = router).
            depth: Current sub-agent nesting depth (recursion guard).
            parent_id: Parent session identifier (for sub-agents).
            parent_model: Parent agent's effective model name. If provided and
                differs from this agent's model AND both run on ``LOCAL``, the
                parent model is liberated on entry and this agent's model is
                liberated on exit. API-side providers don't need VRAM liberation.
            parent_provider: Parent agent's effective provider (any curated provider id or ``"LOCAL"``).
                Used together with ``parent_model`` to decide whether to liberate
                the parent model (only meaningful when both are LOCAL).

        Yields:
            SSE events (raw ``"data: {...}\\n\\n"`` strings):
            - ``{"type": "chunk", "content": str}`` — text fragment.
            - ``{"type": "tool_call", "content": {"name", "args"}}`` — tool.
            - ``{"type": "tool_result", "content": {"name", "result"}}``.
            - ``{"type": "subagent_call", "content": {"agent_name", "prompt"}}``.
            - ``{"type": "subagent_result", "content": {"agent_name", "result"}}``.
            - ``"data: [DONE]\\n\\n"`` — stream end.

            On error, the stream yields a chunk SSE event followed by
            the raw ``[DONE]`` marker.
        """
        # --- 0.5. Set error logging context FIRST (covers recursion guard and all early errors) ---
        _t0 = _time.time()

        # # logger.info("[DEBUG_TIEMPO_SSE] run() started — session=%s, depth=%d, t=%.3f", session_id, depth, _t0)
        error_ctx_token = set_error_context(
            session_id=session_id,
            turn_number=0,  # Will be updated after getting actual turn_number
            agent_name=agent_name,
            depth=depth,
            parent_id=parent_id,
        )

        try:
            # --- Recursion guard for sub-agent delegation ---
            if depth >= MAX_SUBAGENT_DEPTH:
                log_error("Max sub-agent depth reached", source="loop.py:recursion_guard")
                yield f"data: {json.dumps({'type': 'chunk', 'content': 'No se puede delegar: se alcanzó la profundidad máxima de sub-agentes.'}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return

            # --- Track current session/depth/cancel_event on the Tools instance so that the
            #     `task` tool can create an integrated child session and propagate cancellation. ---
            agent.tools._current_session_id = session_id
            agent.tools._current_depth = depth
            agent.tools._stream_cancel_event = stream_cancel_event
            agent.tools._temp_files = set()

            # --- 0. Model (resuelto por el endpoint /api/config/models) ---
            model = agent._resolved_model

            # --- 0a. Resolve model parameters (temperature, top_p, reasoning, model override) ---
            # Precedence per parameter: explicit global override (persisted via
            # /api/config/models/select, non-null) → agent frontmatter
            # (`parameters`, via task tool or router) → hardcoded fallback.
            temperature = 0.0
            top_p = 0.5
            reasoning = True  # Default: reasoning enabled (boolean or string level)
            budget_tokens = None
            response_format = None  # Optional structured output (e.g. {"type": "json_object"})
            max_tokens = 8192
            if parameters:
                if parameters.get("temperature") is not None:
                    temperature = parameters["temperature"]
                if parameters.get("top_p") is not None:
                    top_p = parameters["top_p"]
                # reasoning can be: bool (legacy), string ("on"/"off"/"low"/"medium"/"high"/"max"/"default")
                if parameters.get("reasoning") is not None:
                    r = parameters["reasoning"]
                    if isinstance(r, bool):
                        reasoning = "on" if r else "off"
                    elif isinstance(r, str):
                        reasoning = r
                    else:
                        reasoning = str(r)
                # response_format from frontmatter (optional structured output)
                if parameters.get("response_format") is not None:
                    response_format = parameters["response_format"]
                # model override from frontmatter (optional)
                if parameters.get("model"):
                    model = parameters["model"]
                max_tokens = parameters.get("max_tokens", max_tokens)

            # Explicit global overrides win over frontmatter values; a "null"
            # (default) override never masks the agent's own frontmatter.
            override_temperature = _read_param_override("param_temperature")
            if override_temperature is not None:
                temperature = override_temperature
            override_top_p = _read_param_override("param_top_p")
            if override_top_p is not None:
                top_p = override_top_p
            override_reasoning = _read_param_override("param_reasoning")
            if override_reasoning is not None:
                reasoning = override_reasoning
            override_budget = _read_param_override("param_budget_tokens")
            if override_budget is not None:
                budget_tokens = override_budget
            override_response_format = _read_param_override("param_response_format")
            if override_response_format is not None:
                response_format = override_response_format

            # Resolve this loop's effective provider. If the agent's frontmatter
            # sets `parameters.provider`, use it for this loop only (passed
            # explicitly to llm_process / llm_streaming). Otherwise fall back
            # to the global agent.provider.
            effective_provider = agent.provider
            if parameters and parameters.get("provider"):
                effective_provider = parameters["provider"]
            if isinstance(effective_provider, str):
                effective_provider = effective_provider.strip() or None

            # Validate structured output against the effective model. If the
            # model declaratively does not support it, fall back to text
            # (warning only — never blocks the loop). Unknown passes.
            if response_format == "json":
                try:
                    if (effective_provider or "").strip() == "LOCAL":
                        from backend.agent.utils.model_resolver import (
                            get_model_reasoning_options,
                        )
                        local_caps = await asyncio.to_thread(
                            get_model_reasoning_options, effective_provider, model
                        )
                        supports_format = local_caps.get("response_format_supported")
                    else:
                        from backend.agent.utils.model_catalog import (
                            get_reasoning_options,
                        )
                        caps = await asyncio.to_thread(
                            get_reasoning_options,
                            (effective_provider or "").strip(),
                            model,
                        )
                        supports_format = caps.get("response_format_supported")
                except Exception as exc:
                    logger.warning("No se pudo validar response_format: %s", exc)
                    supports_format = None
                if supports_format is False:
                    logger.warning(
                        "Model '%s' does not support structured output. "
                        "Falling back to text.",
                        model,
                    )
                    response_format = "text"

            logger.info(
                "Agent loop started — model: %s, provider: %s, session: %s, agent: %s, depth: %d, temp: %s, top_p: %s, reasoning: %s",
                model, effective_provider, session_id, agent_name, depth, temperature, top_p, reasoning,
            )

            # --- Liberate parent model only when both parent and child run on
            #     LOCAL with different models. API-side providers don't consume VRAM
            #     so there's nothing to free/reload. ---
            parent_is_local = bool(parent_provider) and parent_provider.strip() == "LOCAL"
            child_is_local = bool(effective_provider) and effective_provider.strip() == "LOCAL"
            if parent_model and model != parent_model and parent_is_local and child_is_local:
                logger.info("Liberando modelo del parent (%s) — subagente usa %s", parent_model, model)
                ctx = get_error_context()
                await asyncio.to_thread(
                    liberar_modelo, parent_model,
                    ctx.get("session_id") if ctx else None,
                    ctx.get("turn_number") if ctx else None,
                    ctx.get("parent_id") if ctx else None,
                )

            # --- 1. Ensure session exists ---
            result = session_manager.create_session(session_id)
            if result.get("status") == "error" and "already exists" not in result.get("message", ""):
                msg = result.get("message", "Error al crear sesión")
                yield f"data: {json.dumps({'type': 'chunk', 'content': msg}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return

            # --- 1b. Get turn_number for this message ---
            turn_number = session_manager.get_last_turn_number(session_id) + 1

            # --- 1c. Update error logging context with actual turn_number ---
            reset_error_context(error_ctx_token)
            error_ctx_token = set_error_context(
                session_id=session_id,
                turn_number=turn_number,
                agent_name=agent_name,
                depth=depth,
                parent_id=parent_id,
            )

            # --- 1d. Create temp directory for agent's markdown file ---
            from backend.agent.utils.config_dir import get_config_dir
            temp_dir = get_config_dir() / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_path = str(temp_dir)
            

            # --- 2. Build system prompt ---
            if system_prompt is None:
                system_prompt = build_system_prompt(agent_name)

            # Sub-agents get their skills/agents appended (router prompt already
            # includes them via system_prompt.md placeholders).
            if agent_name is not None:
                skills_section = format_skills_section(skill_permissions=skill_permissions)
                agents_result = list_agents()
                all_agents = (
                    json.loads(agents_result["data"])
                    if agents_result.get("status") == "success"
                    else []
                )
                # Filtrar agentes según task permissions (solo mostrar los que puede llamar)
                task_perms = (tool_permissions or {}).get("task", {})
                agents = [
                    a for a in all_agents
                    if a["name"] in task_perms and task_perms[a["name"]] == "allow"
                ]
                system_prompt = (
                    f"{system_prompt}\n\n"
                    f"## Skills Disponibles\n{skills_section}\n\n"
                    f"## Agentes Disponibles\n{agents}"
                )

            # Append temp directory path to system prompt (concatenation, no .format)
            system_prompt = f"{system_prompt}\n\n## Directorio temporal\n{temp_path}"
            
            # --- 3. Resolve tools ---
            if agent_name is None:
                # Router: if config.yaml defines permissions, use them as
                # the complete set (no floor). If config.yaml has no
                # permissions, fall back to the guaranteed floor tools.
                router_perms = _load_router_permissions()
                if router_perms is not None:
                    # config.yaml defines permissions — use them exclusively.
                    tool_permissions = {}
                    for name, action in (router_perms.get("tool") or {}).items():
                        tool_permissions[name] = action
                    task_perms = router_perms.get("task")
                    if isinstance(task_perms, dict) and task_perms:
                        tool_permissions["task"] = task_perms
                    elif "task" not in tool_permissions:
                        tool_permissions["task"] = "allow"
                else:
                    # No config.yaml — use the guaranteed floor.
                    tool_permissions = {
                        "task": "allow",
                        "help": "allow",
                        "search_memory": "allow",
                        "read": "allow",
                        "websearch": "allow",
                        "webfetch": "allow",
                    }
                try:
                    tools = list(agent.tools.tools_registry(tool_permissions))
                except AttributeError as e:
                    log_error(str(e), source="loop.py:run(tools)")
                    tools = _ROUTER_TOOLS
            else:
                try:
                    tools = list(agent.tools.tools_registry(tool_permissions))
                except AttributeError as e:
                    log_error(str(e), source="loop.py:run(tools)")
                    tools = []
            logger.info("Tools available: %d", len(tools))

            # Expose the effective permissions to the execution layer so
            # execute_tool can enforce them (deny by default) on every call.
            agent.tools._current_tool_permissions = tool_permissions or {}

          

            # --- 4. Build initial messages array (history does NOT include current message) ---
            # Append attached files (if any) to the user message
            effective_message = user_message
            if file_contents:
                try:
                    parts: list[str] = []
                    for fn, text in file_contents:
                        parts.append(f"**Archivo: {fn}**\n{text}")
                    attachments_section = (
                        "<inicio_adjuntos>\n"
                        + "\n".join(parts)
                        + "\n<fin_adjuntos>"
                    )
                    effective_message = f"{user_message}\n\n{attachments_section}"
                except Exception as exc:
                    logger.warning("Error building attachments section: %s", exc)
                    log_error(str(exc), source="loop.py:run")

            messages = build_initial_messages(
                session_manager,
                session_id,
                system_prompt,
                effective_message,
                max_turns=await asyncio.to_thread(fetch_context_window_turns),
            )
            
            # --- 5. Save user message to DB (after building messages so history is clean) ---
            session_manager.save_message(
                session_id, "user", content=user_message, turn_number=turn_number,
            )

            # --- 5b. Generate title on first turn (root sessions only, non-blocking) ---
            # Sub-agents (depth > 0) skip title generation entirely: each one
            # creates a new session (turn 1) and generating a title would block
            # the loop. For root sessions the title is generated in a background
            # task so it doesn't block the response stream; the result is pushed
            # to a queue that the loop drains to emit the session_title event.
            title_queue: asyncio.Queue | None = None
            title_task: asyncio.Task | None = None
            if turn_number == 1 and depth == 0:
                try:
                    existing_titles = session_manager.get_all_titles()
                    if existing_titles:
                        titles_formatted = "\n".join(
                            [f"{i+1}. {t}" for i, t in enumerate(existing_titles)]
                        )
                    else:
                        titles_formatted = "Sin restricciones (primera conversación)"
                    title_prompt = agent.prompt("title").format(
                        message=user_message,
                        titles=titles_formatted,
                    )
                    title_queue = asyncio.Queue()

                    async def _generate_title() -> None:
                        try:
                            title_result = await agent.llm_process(
                                model=model,
                                prompt=title_prompt,
                                max_tokens=100,
                                temperature=temperature,
                                top_p=top_p,
                                reasoning=False,
                                provider=effective_provider,
                            )
                            raw_title = title_result.get("data", "") if isinstance(title_result, dict) else ""
                            title = (raw_title or "").strip().replace('"', "").replace("'", "")
                            if not title:
                                # Fallback: usar el primer mensaje del usuario truncado
                                title = user_message[:80].strip()
                            if title:
                                try:
                                    session_manager.update_session_title(session_id, title)
                                except Exception as exc:
                                    logger.warning("No se pudo guardar el título: %s", exc)
                                    log_error(str(exc), source="loop.py:run")
                                # Track the title call in messages (role="title"
                                # rows are skipped by the history builder, the
                                # history UI and the LLM context) so
                                # SUM(messages) == SUM(spend).
                                try:
                                    t_usage = title_result.get("usage") if isinstance(title_result, dict) else None
                                    session_manager.save_message(
                                        session_id, "title",
                                        content=f"Título generado: {title}",
                                        model=model,
                                        provider=effective_provider,
                                        turn_number=turn_number,
                                        step=0,
                                        status="success", message="title",
                                        usage=t_usage,
                                    )
                                except Exception:
                                    pass
                                await title_queue.put(title)
                        except Exception as exc:
                            logger.warning("No se pudo generar el título: %s", exc)
                            log_error(str(exc), source="loop.py:run")

                    title_task = asyncio.create_task(_generate_title())
                except Exception as exc:
                    logger.warning("No se pudo preparar el título: %s", exc)
                    log_error(str(exc), source="loop.py:run")
                    title_queue = None
                    title_task = None

            # --- 6. Agent loop (while True) ---
            iteration = 0
            step = 0
            empty_response_retries = 0
            empty_response_hint: dict[str, str] | None = None
            while iteration < self.max_iterations:
                iteration += 1
                step += 1
                # Accumulate usage across the inner retry loop so the single
                # messages row saved for this step carries the sum of every
                # LLM attempt (SUM(messages) == SUM(spend) per provider/model).
                step_prompt = 0
                step_completion = 0
                step_total = 0
                step_time = 0.0
                # Drain non-blocking title generation result (if ready)
                if title_queue is not None and not title_queue.empty():
                    try:
                        t = title_queue.get_nowait()
                        yield f"data: {json.dumps({'type': 'session_title', 'content': t}, ensure_ascii=False)}\n\n"
                    except asyncio.QueueEmpty:
                        pass
                logger.info(
                    "Iteration %d / %d — messages in context: %d, tools: %d",
                    iteration, self.max_iterations, len(messages), len(tools),
                )

                # ---- 6a. Call LLM with streaming (single API call, detects tool_calls) ----
                # Retry loop: on rate-limit (429/413) or transient errors the
                # stream consumption is retried with exponential back-off
                # (MAX_LLM_RETRIES times). Fatal errors and user cancellation
                # are never retried.
                collected_content = ""
                collected_reasoning = ""
                tool_calls = None
                usage_data: dict[str, Any] | None = None

                llm_attempt = 0
                while True:
                    # Reset partial state before every attempt so content from
                    # a failed attempt never leaks into the next one.
                    collected_content = ""
                    collected_reasoning = ""
                    tool_calls = None
                    usage_data = None

                    # Preventively block the request if the configured budget
                    # limit is exceeded (cloud providers only; LOCAL/Ollama has
                    # no cost). Both the model-specific and the provider-level
                    # limits are checked by ``check_spend_limit``.
                    if (effective_provider or "").strip() != "LOCAL":
                        can_proceed, _spend_info = check_spend_limit(
                            (effective_provider or "").strip(), model
                        )
                        if not can_proceed:
                            budget_msg = (
                                "*Se alcanzó el límite de presupuesto configurado "
                                "para este proveedor/modelo. No se pueden hacer más "
                                "solicitudes hasta que se incremente el límite.*"
                            )
                            session_manager.save_message(
                                session_id, "assistant", content=budget_msg,
                                model=model, turn_number=turn_number, step=step,
                            )
                            yield f"data: {json.dumps({'type': 'chunk', 'content': budget_msg}, ensure_ascii=False)}\n\n"
                            yield "data: [DONE]\n\n"
                            return

                    try:
                        async for event in agent.llm_streaming(
                            model=model, messages=messages, tools=tools,
                            stream_cancel_event=stream_cancel_event,
                            temperature=temperature, top_p=top_p, max_tokens=max_tokens,
                            reasoning=reasoning, budget_tokens=budget_tokens,
                            provider=effective_provider,
                            response_format=response_format,
                        ):
                            if event["type"] == "chunk":
                                collected_content += event.get("content", "")
                                yield f"data: {json.dumps({'type': 'chunk', 'content': event.get('content', '')}, ensure_ascii=False)}\n\n"
                            elif event["type"] == "reasoning":
                                collected_reasoning += event.get("content", "")
                                yield f"data: {json.dumps({'type': 'reasoning', 'content': event.get('content', '')}, ensure_ascii=False)}\n\n"
                            elif event["type"] == "tool_calls_detected":
                                tool_calls = event["content"]
                                break
                            elif event["type"] == "usage":
                                usage_data = event.get("content")
                                logger.info(
                                    "USAGE [%s] prompt=%s completion=%s total=%s time=%ss",
                                    model,
                                    event.get("content", {}).get("prompt_tokens"),
                                    event.get("content", {}).get("completion_tokens"),
                                    event.get("content", {}).get("total_tokens"),
                                    event.get("content", {}).get("total_time"),
                                )
                            elif event["type"] == "aborted":
                                # Guardar respuesta parcial antes de terminar (patrón ProspectingAgent/opencode)
                                # NOTE: se guarda siempre (aunque esté vacía) con
                                # status "aborted" para que SUM(messages) ==
                                # SUM(spend) también en cancelaciones.
                                _eff_usage = {
                                    "prompt_tokens": step_prompt + int((usage_data or {}).get("prompt_tokens") or 0),
                                    "completion_tokens": step_completion + int((usage_data or {}).get("completion_tokens") or 0),
                                    "total_tokens": step_total + int((usage_data or {}).get("total_tokens") or 0),
                                    "total_time": round(step_time + float((usage_data or {}).get("total_time") or 0), 2),
                                    "time_to_first_token": (usage_data or {}).get("time_to_first_token"),
                                }
                                session_manager.save_message(
                                    session_id, "assistant", content=collected_content,
                                    reasoning=collected_reasoning or None,
                                    model=model,
                                    provider=effective_provider,
                                    turn_number=turn_number, step=step,
                                    status="aborted", message="",
                                    usage=_eff_usage,
                                )
                                yield "data: [DONE]\n\n"
                                return
                    except Exception as e:
                        error_category = classify_error_category(e)
                        logger.exception("Error in agent streaming: %s", e)
                        log_error(str(e), source="loop.py:run(llm_stream)")

                        # User cancellation always wins: never retry.
                        if stream_cancel_event is not None and stream_cancel_event.is_set():
                            # The failed attempt never reached the agent's
                            # spend record: count it here (zero tokens when
                            # no usage was captured) so SUM(spend) == SUM(messages).
                            try:
                                agent._record_spend(effective_provider, model, usage_data)
                            except Exception:
                                pass
                            # Step accumulators hold completed attempts; usage_data
                            # holds the current attempt: combine both so the
                            # row carries every LLM call of this step exactly
                            # once (SUM(messages) == SUM(spend)).
                            _eff_usage = {
                                "prompt_tokens": step_prompt + int((usage_data or {}).get("prompt_tokens") or 0),
                                "completion_tokens": step_completion + int((usage_data or {}).get("completion_tokens") or 0),
                                "total_tokens": step_total + int((usage_data or {}).get("total_tokens") or 0),
                                "total_time": round(step_time + float((usage_data or {}).get("total_time") or 0), 2),
                                "time_to_first_token": (usage_data or {}).get("time_to_first_token"),
                            }
                            if collected_content:
                                session_manager.save_message(
                                    session_id, "assistant", content=collected_content,
                                    reasoning=collected_reasoning or None,
                                    model=model,
                                    provider=effective_provider,
                                    turn_number=turn_number, step=step,
                                    status="success", message="",
                                    usage=_eff_usage,
                                )
                            yield "data: [DONE]\n\n"
                            return
                        # Fatal and budget errors keep the current behavior: no retry.
                        if error_category in ("fatal", "budget"):
                            # Guardar respuesta parcial antes de terminar con error
                            # The failed attempt never reached the agent's
                            # spend record: count it here (zero tokens when
                            # no usage was captured) so SUM(spend) == SUM(messages).
                            try:
                                agent._record_spend(effective_provider, model, usage_data)
                            except Exception:
                                pass
                            # Step accumulators hold completed attempts; usage_data
                            # holds the current attempt: combine both so the
                            # row carries every LLM call of this step exactly
                            # once (SUM(messages) == SUM(spend)).
                            _eff_usage = {
                                "prompt_tokens": step_prompt + int((usage_data or {}).get("prompt_tokens") or 0),
                                "completion_tokens": step_completion + int((usage_data or {}).get("completion_tokens") or 0),
                                "total_tokens": step_total + int((usage_data or {}).get("total_tokens") or 0),
                                "total_time": round(step_time + float((usage_data or {}).get("total_time") or 0), 2),
                                "time_to_first_token": (usage_data or {}).get("time_to_first_token"),
                            }
                            if collected_content:
                                session_manager.save_message(
                                    session_id, "assistant", content=collected_content,
                                    reasoning=collected_reasoning or None,
                                    model=model,
                                    provider=effective_provider,
                                    turn_number=turn_number, step=step,
                                    status="error", message=str(e)[:500],
                                    usage=_eff_usage,
                                )
                            else:
                                session_manager.save_message(
                                    session_id, "assistant", content="Ocurrió un error al procesar la solicitud. Por favor, intentá de nuevo.", model=model, provider=effective_provider, turn_number=turn_number, step=step,
                                    status="error", message=str(e)[:500],
                                    usage=_eff_usage,
                                )
                            yield f"data: {json.dumps({'type': 'chunk', 'content': 'Ocurrió un error al procesar la solicitud. Por favor, intentá de nuevo.'}, ensure_ascii=False)}\n\n"
                            yield "data: [DONE]\n\n"
                            return

                        # Rate-limit / transient: retry with exponential back-off while attempts
                        # remain. The delay honors the provider's ``retry_after``
                        # hint when available, never dropping below the
                        # exponential back-off floor.
                        if llm_attempt < MAX_LLM_RETRIES:
                            delay = max(
                                LLM_BACKOFF_BASE_SECONDS * (2 ** llm_attempt),
                                get_retry_delay(e, LLM_BACKOFF_BASE_SECONDS, 60.0),
                            )
                            await asyncio.sleep(delay)
                            logger.warning(
                                "LLM %s error (attempt %d/%d): %s — retrying in %.0fs",
                                error_category, llm_attempt + 1, MAX_LLM_RETRIES + 1,
                                e, delay,
                            )
                            log_error(str(e), source="loop.py:run(llm_retry)")
                            if error_category == "rate_limit":
                                retry_msg = f"\n\n*Rate limit alcanzado, reintentando (intento {llm_attempt + 1} de {MAX_LLM_RETRIES})...*"
                            else:
                                retry_msg = "\n\n*Error transitorio, reintentando...*"
                            yield f"data: {json.dumps({'type': 'chunk', 'content': retry_msg}, ensure_ascii=False)}\n\n"
                            # Fold the failed attempt into the step accumulators
                            # exactly once (mirrors the spend record for this
                            # attempt) before retrying.
                            try:
                                step_prompt += int((usage_data or {}).get("prompt_tokens") or 0)
                                step_completion += int((usage_data or {}).get("completion_tokens") or 0)
                                step_total += int((usage_data or {}).get("total_tokens") or 0)
                                step_time += float((usage_data or {}).get("total_time") or 0)
                            except (TypeError, ValueError):
                                pass
                            # The failed attempt never reached the agent's
                            # spend record: count it here so every retry is
                            # tracked in spend (SUM(spend) == SUM(messages)).
                            try:
                                agent._record_spend(effective_provider, model, usage_data)
                            except Exception:
                                pass
                            llm_attempt += 1
                            continue

                        # Attempts exhausted: user-friendly final message.
                        if error_category == "rate_limit":
                            final_msg = "*Se alcanzó el límite de peticiones del proveedor después de varios reintentos. Probá de nuevo en un minuto o cambiá a otro modelo desde la configuración.*"
                        else:
                            final_msg = "*El proveedor no respondió después de varios reintentos. Probá de nuevo en unos momentos.*"
                        log_error(str(e), source="loop.py:run(llm_retry)")
                        # The final failed attempt never reached the agent's
                        # spend record: count it here (zero tokens when no
                        # usage was captured) so SUM(spend) == SUM(messages).
                        try:
                            agent._record_spend(effective_provider, model, usage_data)
                        except Exception:
                            pass
                        _eff_usage = {
                            "prompt_tokens": step_prompt + int((usage_data or {}).get("prompt_tokens") or 0),
                            "completion_tokens": step_completion + int((usage_data or {}).get("completion_tokens") or 0),
                            "total_tokens": step_total + int((usage_data or {}).get("total_tokens") or 0),
                            "total_time": round(step_time + float((usage_data or {}).get("total_time") or 0), 2),
                            "time_to_first_token": (usage_data or {}).get("time_to_first_token"),
                        }
                        if collected_content:
                            session_manager.save_message(
                                session_id, "assistant", content=collected_content,
                                reasoning=collected_reasoning or None,
                                model=model,
                                provider=effective_provider,
                                turn_number=turn_number, step=step,
                                status="error", message=str(e)[:500],
                                usage=_eff_usage,
                            )
                        else:
                            session_manager.save_message(
                                session_id, "assistant", content=final_msg, model=model,
                                provider=effective_provider,
                                turn_number=turn_number, step=step,
                                status="error", message=str(e)[:500],
                                usage=_eff_usage,
                            )
                        yield f"data: {json.dumps({'type': 'chunk', 'content': final_msg}, ensure_ascii=False)}\n\n"
                        yield "data: [DONE]\n\n"
                        return
                    break  # Stream consumed successfully
                # Fold this attempt into the step accumulators exactly once
                # (mirrors the single spend record for this attempt).
                try:
                    step_prompt += int((usage_data or {}).get("prompt_tokens") or 0)
                    step_completion += int((usage_data or {}).get("completion_tokens") or 0)
                    step_total += int((usage_data or {}).get("total_tokens") or 0)
                    step_time += float((usage_data or {}).get("total_time") or 0)
                except (TypeError, ValueError):
                    pass

                # Emit token counter after each LLM call (prompt_tokens is cumulative)
                if usage_data:
                    context_window = ensure_context_window(agent, model)
                    prompt_tokens = usage_data.get("prompt_tokens") or 0
                    percent = round((prompt_tokens / context_window) * 100, 2) if context_window else None
                    vram_gb = get_vram_gb()
                    yield f"data: {json.dumps({'type': 'token_counter', 'content': {'prompt_tokens': prompt_tokens, 'completion_tokens': usage_data.get('completion_tokens') or 0, 'total_tokens': usage_data.get('total_tokens') or 0, 'context_window': context_window, 'percent': percent, 'vram_gb': vram_gb, 'ollama_default_context': ollama_default_context(vram_gb)}}, ensure_ascii=False)}\n\n"

                logger.debug(
                    "LLM response — tool_calls: %s, content_length: %d",
                    len(tool_calls) if tool_calls else 0, len(collected_content),
                )

                # Remove the ephemeral "empty response" hint once the iteration
                # produces real content or tool calls (keeps the context clean).
                if empty_response_hint is not None and (tool_calls or collected_content.strip()):
                    try:
                        messages.remove(empty_response_hint)
                    except ValueError:
                        pass
                    empty_response_hint = None

                
                # ---- 6b. Process tool_calls (LLM wants to continue) ----
                if tool_calls:
                    # Save assistant message with tool_calls (collected_content may be empty)
                    assistant_msg: dict[str, Any] = {
                        "role": "assistant",
                        "content": collected_content,
                        "tool_calls": tool_calls,
                    }
                    messages.append(assistant_msg)

                    session_manager.save_message(
                        session_id, "assistant",
                        content=collected_content,
                        reasoning=collected_reasoning or None,
                        tool_calls=tool_calls,
                        model=model,
                        provider=effective_provider,
                        turn_number=turn_number,
                        step=step,
                        status="success",
                        message="",
                    usage={
                        "prompt_tokens": step_prompt + int((usage_data or {}).get("prompt_tokens") or 0),
                        "completion_tokens": step_completion + int((usage_data or {}).get("completion_tokens") or 0),
                        "total_tokens": step_total + int((usage_data or {}).get("total_tokens") or 0),
                        "total_time": round(step_time + float((usage_data or {}).get("total_time") or 0), 2),
                        "time_to_first_token": (usage_data or {}).get("time_to_first_token"),
                    },
                    )

                    # Collect tool results to update assistant message after all tools execute
                    tool_results: list[dict[str, Any]] = []

                    for tc in tool_calls:
                        is_subagent = tc.get("name") == "task"
                        
                        if is_subagent:
                            agent_name_sub = tc.get("args", {}).get("agent_name", "")
                            prompt_sub = tc.get("args", {}).get("prompt", "")
                           
                            # Resolve permissions ONCE and cache on tools instance so
                            # tools.py:task() can reuse them (avoids re-reading agent .md).
                            tool_perms_sub: dict = {}
                            tp = get_tool_permissions(agent_name_sub)
                            if tp.get("status") == "success":
                                try:
                                    tool_perms_sub = json.loads(tp["data"])
                                except (json.JSONDecodeError, TypeError):
                                    tool_perms_sub = {}

                            skill_perms_sub: dict = {}
                            sp = get_skill_permissions(agent_name_sub)
                            if sp.get("status") == "success":
                                try:
                                    skill_perms_sub = json.loads(sp["data"])
                                except (json.JSONDecodeError, TypeError):
                                    skill_perms_sub = {}

                            params_result = get_agent_parameters(agent_name_sub)
                            parameters_sub: dict = {}
                            if params_result.get("status") == "success":
                                try:
                                    parameters_sub = json.loads(params_result.get("data", "{}"))
                                except (json.JSONDecodeError, TypeError):
                                    parameters_sub = {}

                            agent.tools._task_config = {
                                "agent_name": agent_name_sub,
                                "tool_permissions": tool_perms_sub,
                                "skill_permissions": skill_perms_sub,
                                "parameters": parameters_sub,
                                # Parent's effective model/provider so the sub-agent
                                # loop can decide whether to liberate the parent model
                                # (only when both are LOCAL with different models).
                                "parent_model": model,
                                "parent_provider": effective_provider,
                            }

                            # Get actual skill names for the log (uses cached permissions, no extra .md read)
                            skills_section_sub = format_skills_section(skill_permissions=skill_perms_sub)
                            skill_names = [
                                line[4:].strip()
                                for line in skills_section_sub.split("\n")
                                if line.startswith("### ")
                            ]

                            logger.subagent(
                                "agent=%s prompt=%s tools=%s skills=%s params=%s",
                                agent_name_sub,
                                prompt_sub[:200] if prompt_sub else "",
                                list(tool_perms_sub.keys()),
                                skill_names,
                                parameters_sub,
                            )

                            
                            yield f"data: {json.dumps({'type': 'tool_call', 'content': {'name': 'task', 'args': {'agent_name': agent_name_sub, 'prompt': prompt_sub}}}, ensure_ascii=False)}\n\n"

                            # Create queue for real-time sub-agent event forwarding
                            subagent_queue: asyncio.Queue = asyncio.Queue()
                            agent.tools._subagent_event_queue = subagent_queue

                            # Start tool execution in background task
                            tool_task = asyncio.create_task(execute_tool(agent, tc))

                            try:
                                # Forward sub-agent events to SSE while tool runs
                                while not tool_task.done():
                                    # Check for cancel signal
                                    if stream_cancel_event and stream_cancel_event.is_set():
                                        logger.info("Cancel signal received, stopping sub-agent forwarding")
                                        tool_task.cancel()
                                        break
                                    try:
                                        event_data = await asyncio.wait_for(
                                            subagent_queue.get(), timeout=0.05
                                        )
                                        forwarded_type = event_data.get("content", {}).get("event", {}).get("type", "?")
                                        if forwarded_type in ("tool_call", "tool_result"):
                                            logger.subagent(
                                                ">> forwarding event type=%s child=%s",
                                                forwarded_type,
                                                event_data.get("content", {}).get("child_session_id", "?")[:8],
                                            )
                                        # Register sub-agent temp files for cleanup
                                        if forwarded_type == "tool_call":
                                            inner_event = event_data.get("content", {}).get("event", {})
                                            inner_content = inner_event.get("content", {})
                                            if inner_content.get("name") == "write":
                                                fp = inner_content.get("args", {}).get("file_path", "")
                                                if "TEMP_" in fp:
                                                    agent.tools._temp_files.add(fp)
                                        yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
                                    except asyncio.TimeoutError:
                                        continue

                                # Drain any remaining events after tool finishes
                                while not subagent_queue.empty():
                                    try:
                                        yield f"data: {json.dumps(subagent_queue.get_nowait(), ensure_ascii=False)}\n\n"
                                    except asyncio.QueueEmpty:
                                        break

                                try:
                                    result_data = tool_task.result()
                                except (asyncio.CancelledError, Exception):
                                    result_data = {"status": "error", "message": "Sub-agent cancelled", "data": ""}
                            finally:
                                agent.tools._subagent_event_queue = None
                                if not tool_task.done():
                                    tool_task.cancel()
                        else:
                            yield f"data: {json.dumps({'type': 'tool_call', 'content': {'name': tc['name'], 'args': tc['args']}}, ensure_ascii=False)}\n\n"
                            # Register temp files for cleanup
                            if tc['name'] == 'write' and 'TEMP_' in tc.get('args', {}).get('file_path', ''):
                                agent.tools._temp_files.add(tc['args']['file_path'])
                            result_data = await execute_tool(agent, tc)

                        # Restore parent session/depth state: a nested run (sub-agent)
                        # may have overwritten these on the shared Tools instance.
                        agent.tools._current_session_id = session_id
                        agent.tools._current_depth = depth
                        agent.tools._stream_cancel_event = stream_cancel_event
                        agent.tools._current_tool_permissions = tool_permissions or {}

                        # --- Re-resolve model after subagent (task tool) ---
                        # The subagent may have used a different model and liberated it.
                        # Parent needs to reload its model from persisted config.
                        if is_subagent:
                            try:
                                # Read resolved model from agent singleton (persisted in SQLite via config endpoint)
                                nuevo_modelo = agent._resolved_model
                                if nuevo_modelo and nuevo_modelo != model:
                                    logger.info("Re-resolviendo modelo tras subagente: %s -> %s", model, nuevo_modelo)
                                    ctx = get_error_context()
                                    await asyncio.to_thread(
                                        liberar_modelo, model,
                                        ctx.get("session_id") if ctx else None,
                                        ctx.get("turn_number") if ctx else None,
                                        ctx.get("parent_id") if ctx else None,
                                    )
                                    model = nuevo_modelo
                            except Exception as exc:
                                logger.warning("Error re-resolviendo modelo tras subagente: %s", exc)
                                log_error(str(exc), source="loop.py:run(post_task_resolve)")

                        if is_subagent:
                            yield f"data: {json.dumps({'type': 'tool_result', 'content': {'name': 'task', 'result': result_data}}, ensure_ascii=False)}\n\n"
                        else:
                            yield f"data: {json.dumps({'type': 'tool_result', 'content': {'name': tc['name'], 'result': result_data}}, ensure_ascii=False)}\n\n"

                        # Build tool result message (provider-dependent format).
                        # The frontend receives the full contract (status/message/data)
                        # so it can mark the tool as success/error; the LLM receives only
                        # the meaningful payload (data on success, {"error": message} on
                        # error) exactly as before.
                        if isinstance(result_data, dict) and result_data.get("status") == "error":
                            llm_payload = {"error": result_data.get("message", "Tool failed")}
                        elif isinstance(result_data, dict) and "data" in result_data:
                            llm_payload = result_data["data"]
                        else:
                            llm_payload = result_data
                        tool_content = (
                            json.dumps(llm_payload, ensure_ascii=False)
                            if isinstance(llm_payload, (dict, list))
                            else str(llm_payload)
                        )
                        # Tool result message format depends on the provider API
                        # family: OpenAI-style (tool_call_id) for LOCAL and all
                        # OpenAI-compatible providers, Gemini-style (tool_name)
                        # only for Google.
                        uses_openai_tool_format = (
                            _resolve_tool_api_type(effective_provider) != "google"
                        )
                        if uses_openai_tool_format:
                            tool_msg = {
                                "role": "tool",
                                "tool_call_id": tc.get("id", ""),
                                "content": tool_content,
                            }
                        else:
                            tool_msg = {
                                "role": "tool",
                                "tool_name": tc["name"],
                                "content": tool_content,
                            }

                        messages.append(tool_msg)

                        session_manager.save_message(
                            session_id, "tool",
                            content=tool_msg.get("content", ""),
                            tool_call_id=tool_msg.get("tool_call_id"),
                            tool_name=tool_msg.get("tool_name"),
                            turn_number=turn_number,
                            step=step,
                        )

                        # Collect result for assistant message's tool_results field
                        tool_results.append({
                            "tool_call_id": tc.get("id", ""),
                            "tool_name": tc["name"],
                            "result": result_data,
                        })

                    # Update assistant message with tool_results so frontend can display them on history load
                    session_manager.update_message_tool_results(session_id, turn_number, tool_results)

                    continue  # back to while loop

                # ---- 6c. No tool_calls → final response ----
                # Empty response guard: an empty final answer (no content, no
                # tool_calls) is treated as an invalid iteration and retried,
                # up to MAX_EMPTY_RESPONSE_RETRIES times. The guard consumes
                # normal iterations (no extra logic beyond its own counter).
                if not collected_content.strip():
                    if empty_response_retries < MAX_EMPTY_RESPONSE_RETRIES:
                        empty_response_retries += 1
                        logger.warning(
                            "Empty LLM response (no content, no tool_calls) — retry %d/%d",
                            empty_response_retries, MAX_EMPTY_RESPONSE_RETRIES,
                        )
                        log_error(
                            "Empty LLM response, retrying",
                            source="loop.py:empty_response_guard",
                        )
                        # Ephemeral system message guiding the model to produce
                        # real content; removed once the iteration succeeds.
                        # Remove any previous hint first so consecutive empty
                        # responses never stack duplicates in the context.
                        if empty_response_hint is not None:
                            try:
                                messages.remove(empty_response_hint)
                            except ValueError:
                                pass
                        empty_response_hint = {
                            "role": "system",
                            "content": (
                                "Tu respuesta anterior llegó vacía. DEBES responder "
                                "con contenido real para el usuario; no devuelvas "
                                "texto vacío."
                            ),
                        }
                        messages.append(empty_response_hint)
                        continue

                    final_msg = "*El modelo devolvió una respuesta vacía después de varios intentos. Probá reformular tu mensaje.*"
                    logger.warning(
                        "Empty LLM response persisted after exhausting %d retries",
                        MAX_EMPTY_RESPONSE_RETRIES,
                    )
                    log_error(
                        "Empty LLM response after exhausting retries",
                        source="loop.py:empty_response_guard",
                    )
                    session_manager.save_message(
                        session_id, "assistant", content=final_msg,
                        model=model,
                        provider=effective_provider,
                        turn_number=turn_number, step=step,
                        status="error", message="empty_response",
                        usage={
                            "prompt_tokens": step_prompt + int((usage_data or {}).get("prompt_tokens") or 0),
                            "completion_tokens": step_completion + int((usage_data or {}).get("completion_tokens") or 0),
                            "total_tokens": step_total + int((usage_data or {}).get("total_tokens") or 0),
                            "total_time": round(step_time + float((usage_data or {}).get("total_time") or 0), 2),
                            "time_to_first_token": (usage_data or {}).get("time_to_first_token"),
                        },
                    )
                    yield f"data: {json.dumps({'type': 'chunk', 'content': final_msg}, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                    if parent_model and model != parent_model and parent_is_local and child_is_local:
                        ctx = get_error_context()
                        await asyncio.to_thread(
                            liberar_modelo, model,
                            ctx.get("session_id") if ctx else None,
                            ctx.get("turn_number") if ctx else None,
                            ctx.get("parent_id") if ctx else None,
                        )
                    return

                cleaned = agent.clean(collected_content)
                session_manager.save_message(
                    session_id, "assistant", content=cleaned,
                    reasoning=collected_reasoning or None,
                    model=model,
                    provider=effective_provider,
                    turn_number=turn_number, step=step,
                    status="success",
                    message="",
                        usage={
                            "prompt_tokens": step_prompt + int((usage_data or {}).get("prompt_tokens") or 0),
                            "completion_tokens": step_completion + int((usage_data or {}).get("completion_tokens") or 0),
                            "total_tokens": step_total + int((usage_data or {}).get("total_tokens") or 0),
                            "total_time": round(step_time + float((usage_data or {}).get("total_time") or 0), 2),
                            "time_to_first_token": (usage_data or {}).get("time_to_first_token"),
                        },
                )

                # Emit the session title before [DONE] so the sidebar refreshes
                # with the generated title even if it finished after the loop.
                if title_queue is not None:
                    if title_task is not None and not title_task.done():
                        try:
                            await asyncio.wait_for(title_task, timeout=5)
                        except (asyncio.TimeoutError, asyncio.CancelledError):
                            pass
                    while not title_queue.empty():
                        try:
                            t = title_queue.get_nowait()
                            yield f"data: {json.dumps({'type': 'session_title', 'content': t}, ensure_ascii=False)}\n\n"
                        except asyncio.QueueEmpty:
                            break

                # --- 6c-bis. Index the completed turn into long-term memory ---
                # Fire-and-forget: runs in the background, never blocks or
                # breaks the SSE stream (failures are only logged). Scheduled
                # after the title drain so the indexed metadata can include
                # the session title. Only root sessions are indexed —
                # sub-agent child sessions duplicate the parent's content and
                # would pollute the memory index.
                if depth == 0:
                    try:
                        from backend.agent.utils.rag_helpers import index_turn_fire_and_forget

                        index_turn_fire_and_forget(
                            session_id=session_id,
                            turn_number=turn_number,
                            user_message=user_message,
                            assistant_message=cleaned or "",
                        )
                    except Exception as exc:
                        logger.warning("Memory indexing could not be scheduled: %s", exc)
                        log_error(str(exc), source="loop.py:run(memory_index)")

                _t_before_done = _time.time()

                # # logger.info("[DEBUG_TIEMPO_SSE] about to yield [DONE] — iteration=%d, t=%.3f", iteration, _t_before_done)
                yield "data: [DONE]\n\n"
                _t_after_done = _time.time()
                # # logger.info("[DEBUG_TIEMPO_SSE] after yield [DONE] — t=%.3f, diff=%.3f", _t_after_done, _t_after_done - _t_before_done)
                logger.info("Agent loop completed in %d iterations", iteration)
                # Liberate model only if subagent with different LOCAL model from parent
                if parent_model and model != parent_model and parent_is_local and child_is_local:
                    ctx = get_error_context()
                    await asyncio.to_thread(
                        liberar_modelo, model,
                        ctx.get("session_id") if ctx else None,
                        ctx.get("turn_number") if ctx else None,
                        ctx.get("parent_id") if ctx else None,
                    )
                return

            # ---- Max iterations ----
            logger.warning("Agent loop reached max_iterations (%d)", self.max_iterations)
            yield f"data: {json.dumps({'type': 'chunk', 'content': '\n\n*El agente alcanzó el límite de iteraciones.*'})}\n\n"
            yield "data: [DONE]\n\n"
            if parent_model and model != parent_model and parent_is_local and child_is_local:
                logger.info("Liberando modelo del subagente (%s) por max_iterations", model)
                ctx = get_error_context()
                await asyncio.to_thread(
                    liberar_modelo, model,
                    ctx.get("session_id") if ctx else None,
                    ctx.get("turn_number") if ctx else None,
                    ctx.get("parent_id") if ctx else None,
                )

        finally:
            # Ensure the background title task completes (or is cancelled) so
            # it doesn't linger after the loop ends.
            if title_task is not None and not title_task.done():
                try:
                    await asyncio.wait_for(title_task, timeout=5)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass
            _t_finally = _time.time()

            # # logger.info("[DEBUG_TIEMPO_SSE] run() finally — t=%.3f", _t_finally)
            # Cleanup TEMP_ files created during this loop
            _temp_files = getattr(agent.tools, "_temp_files", None)
            if _temp_files:
                for fp in list(_temp_files):
                    try:
                        if os.path.exists(fp):
                            os.remove(fp)
                            logger.info("Cleaned up temp file: %s", fp)
                    except Exception as exc:
                        logger.warning("Failed to clean up temp file %s: %s", fp, exc)
                agent.tools._temp_files = set()

            # Cleanup agent's temp markdown file ({agent_name}_temp.md in config dir)
            if agent_name is not None:
                try:
                    from backend.agent.utils.config_dir import get_config_dir
                    temp_md = get_config_dir() / f"{agent_name}_temp.md"
                    
                    if temp_md.exists():
                        temp_md.unlink()
                        logger.info("Cleaned up agent temp markdown: %s", temp_md)
                except Exception as exc:
                    logger.warning("Failed to clean up agent temp markdown for %s: %s", agent_name, exc)

            # Ensure error context is always reset, even on cancellation/exception
            # Guard against ContextVar leak when generator cancelled in different context
            try:
                reset_error_context(error_ctx_token)
                # # logger.info("[DEBUG_TIEMPO_SSE] run() finally — reset_error_context OK, t=%.3f", _time.time())
            except (ValueError, RuntimeError) as _exc:
                # logger.info("[DEBUG_TIEMPO_SSE] run() finally — reset_error_context FAILED: %s, t=%.3f", _exc, _time.time())
                pass


# ------------------------------------------------------------------
# Access point (entry point for direct testing)
# ------------------------------------------------------------------

if __name__ == "__main__":
    async def _main() -> None:
        from backend.instances import agent, session_manager

        session_id = sys.argv[1] if len(sys.argv) > 1 else "test-session"
        message = sys.argv[2] if len(sys.argv) > 2 else "Hola, ¿qué podés hacer?"

        loop = AgentLoop(
            agent=agent,
            session_manager=session_manager,
        )
        async for event in loop.run(session_id=session_id, user_message=message):
            print(event, flush=True)

    asyncio.run(_main())