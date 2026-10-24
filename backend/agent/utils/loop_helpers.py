"""Helper functions for the agent loop.

Extracted from ``loop.py`` so the loop module stays focused on the
iteration logic. Each helper is a plain module-level function that
receives its dependencies as arguments (no hidden shared state).
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import re
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime
from typing import Any, Iterable

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.agent.agent import Agent
    from backend.agent.session import SessionManager

# ---------------------------------------------------------------------------
# Ensure the project root is in sys.path so absolute imports (backend.*)
# resolve correctly regardless of how the file is invoked.
# loop_helpers.py is at backend/agent/utils/ -> need 3 dirname() calls to reach root.
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(_current_dir)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.permissions import (
    get_agent_prompt,
    get_tool_permissions,
    is_tool_allowed,
    list_agents,
)
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.db import db_transaction, get_connection
from backend.agent.utils.queries import load_query
from backend.agent.utils.skill_loader import format_skills_section
from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.instances import agent
from backend.agent.utils.config_dir import get_agents_dir, get_config_dir

logger = logging.getLogger(__name__)

_tool_call_ctx: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "synapse_tool_call_ctx", default=None
)
"""Per-tool-call snapshot for parallel execution.

Each asyncio task running a tool call sets its own snapshot (parent
session id, depth, tool permissions, resolved sub-agent config and
dedicated sub-agent event queue) before invoking ``execute_tool``.
``execute_tool`` and the ``task`` tool prefer the snapshot over the
shared ``Tools`` attributes, so parallel calls (tools and sub-agents
alike) can never overwrite each other's context. Callers outside the
agent loop simply leave it unset and the legacy shared attributes
are used, exactly as before.
"""

_CONFIG_BASE_URL = os.getenv("CONFIG_BASE_URL", "http://127.0.0.1:8000/api/config")


def _mandatory_block(tools: Iterable[str]) -> str:
    """Load the MANDATORY rules block from ``prompts/mandatory.jinja``.

    Args:
        tools: Names of the tools enabled for the agent.

    Returns:
        The block content, or ``""`` if the prompt file is missing.
    """
    try:
        return agent.prompt("mandatory", tools=tools)
    except FileNotFoundError:
        logger.warning("Prompt mandatory.jinja no encontrado; no se inyecta MANDATORY.")
        return ""


def _security_block(tools: Iterable[str], decision: bool = False) -> str:
    """Load the security rules from ``prompts/seguridad.jinja``.

    Args:
        tools: Names of the tools enabled for the agent.
        decision: True when the decision model is enabled; the rules go to
            it (see ``is_message_blocked``) instead of the prompt, so the
            block is left out.

    Returns:
        The rendered rules, or ``""`` if the prompt file is missing.
    """
    if decision:
        return ""
    try:
        return agent.prompt("seguridad", tools=tools, decision=False).strip()
    except FileNotFoundError:
        logger.warning("Prompt seguridad.jinja no encontrado; no se inyecta Seguridad.")
        return ""


def _all_tool_names() -> list[str]:
    """List every tool of the registry (what an unrestricted agent gets).

    Returns:
        The tool names.
    """
    return [t["function"]["name"] for t in agent.tools.tools_registry({"*": "allow"})]


def _agent_tool_names(agent_name: str) -> list[str]:
    """List the tools a sub-agent gets (same filter as the agent loop).

    Args:
        agent_name: Name of the sub-agent.

    Returns:
        The tool names.
    """
    try:
        result = get_tool_permissions(agent_name)
        perms = json.loads(result["data"]) if result.get("status") == "success" else {}
        return [t["function"]["name"] for t in agent.tools.tools_registry(perms)]
    except Exception as exc:
        log_error(str(exc), source="loop_helpers.py:_agent_tool_names")
        return []


def load_context_text() -> str:
    """Load all context files from SQLite and return their content joined.

    Reads every row from the ``context_files`` table and joins the file name
    and extracted text with a visible separator.  Returns an empty string if
    no context files exist or the table cannot be read.

    Returns:
        A formatted string ready to be appended to the system prompt.
    """
    try:
        with get_connection() as conn:
            rows = conn.execute(
                load_query("context_files/list_all.sql"),
            ).fetchall()
        if not rows:
            return ""
        parts: list[str] = []
        for row in rows:
            parts.append(f"--- {row['filename']} ---\n{row['content']}")
        return "==================================\n".join(parts)
    except Exception as exc:
        logger.warning("No se pudieron cargar archivos de contexto: %s", exc)
        return ""


def fetch_context_window_turns() -> int:
    """Query the config endpoint for the current context-window setting.

    Falls back to ``-1`` (all turns) if the endpoint is unreachable.

    Returns:
        The ``max_turns`` value reported by ``GET /api/config/context-window``.
    """
    try:
        url = f"{_CONFIG_BASE_URL}/context-window"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return int(data.get("max_turns", -1))
    except Exception as exc:
        logger.warning("Failed to fetch context window from endpoint: %s", exc)
        log_error(str(exc), source="loop_helpers.py:fetch_context_window_turns")
        return -1


def router_agents(tools: Iterable[str], task_perms: dict | None = None) -> list[dict[str, str]]:
    """List the agents the router can delegate to.

    Args:
        tools: Names of the tools enabled for the router; without ``task`` there are no agents.
        task_perms: Nested ``task`` permission; when given, only the agents it allows are listed.

    Returns:
        One dict per agent with ``name`` and ``description`` (the ``agentes`` of ``system_prompt.jinja``).
    """
    if "task" not in tools:
        return []
    agents_result = list_agents()
    agents = (
        json.loads(agents_result["data"])
        if agents_result.get("status") == "success"
        else []
    )
    if isinstance(task_perms, dict) and task_perms:
        from backend.agent.permissions import wildcard_match

        agents = [
            a for a in agents
            if any(
                action == "allow" and wildcard_match(key, a["name"])
                for key, action in task_perms.items()
            )
        ]
    return agents


def _read_agent_md() -> str:
    """Read the shared ``AGENT.md`` behavior file.

    Returns:
        The file content, or ``""`` when it does not exist or cannot be read.
    """
    agent_md_path = get_agents_dir() / "AGENT.md"
    if not agent_md_path.is_file():
        return ""
    try:
        with open(agent_md_path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Error al leer AGENT.md: %s; no se inyecta Behavior.", exc)
        log_error(str(exc), source="loop_helpers.py:_read_agent_md")
        return ""


def get_temp_dir() -> str:
    """Create the shared temporary directory and return its path.

    Returns:
        The absolute path of the ``temp`` directory inside the config dir.
    """
    temp_dir = get_config_dir() / "temp"
    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("No se pudo crear el directorio temporal %s: %s", temp_dir, exc)
        log_error(str(exc), source="loop_helpers.py:get_temp_dir")
    return str(temp_dir)


def build_subagent_sections(
    tool_permissions: dict | None = None,
    skill_permissions: dict | None = None,
) -> tuple[str, str]:
    """Resolve the skills and delegable-agents sections for a sub-agent.

    Shared by ``agent_loop.run()`` and the ``task`` tool so a delegated
    sub-agent always receives the same sections no matter the entry point.

    Args:
        tool_permissions: Effective tool permissions of the sub-agent.
        skill_permissions: Skill permissions of the sub-agent.

    Returns:
        Tuple ``(skills_section, agents_section)``; each is ``""`` when empty.
    """
    skills_section = format_skills_section(skill_permissions=skill_permissions)
    # Only the agents its ``task`` permission allows (none without it).
    task_perms = (tool_permissions or {}).get("task", {})
    agents_section = agent.prompt(
        "agentes_subagente",
        agentes=router_agents(("task",) if task_perms else (), task_perms),
    )
    return skills_section, agents_section


def build_system_prompt(
    agent_name: str | None = None,
    tools: Iterable[str] | None = None,
    task_perms: dict | None = None,
    skills_section: str = "",
    agents_section: str = "",
    temp_dir: str = "",
) -> str:
    """Build the system prompt for an agent.

    The assembly lives in Jinja: ``system_prompt.jinja`` for the router
    (its own body plus every optional section) and ``subagent_prompt.jinja``
    for sub-agents (their markdown as ``base`` plus the same sections).
    This function only resolves each piece of content and passes it as a
    template variable; no string surgery here.

    - If *agent_name* is ``None`` (router): ``system_prompt.jinja`` is always the
      base prompt. If ``AGENT.md`` exists in the agents config directory, it is
      injected as a ``## Behavior`` section before ``## MANDATORY:``.
      In both cases, append the current date and the list of available
      agents (from the agents folder). No placeholders, no ``.format()``.
    - If *agent_name* is provided (sub-agent): resolve the system prompt
      from the agent's markdown via ``get_agent_prompt``.

    Args:
        agent_name: Optional sub-agent name. ``None`` means the router.
        tools: Names of the tools enabled for the agent. The prompt only
            includes the sections of the tools it can use. ``None`` means
            all tools for the router and the agent's own tools for a
            sub-agent.
        task_perms: Router only. Nested ``task`` permission; when given,
            the ``## Agentes`` section lists only the agents it allows.
            The section is left out when the router has no ``task`` tool.
        skills_section: Pre-rendered skills catalog (``## Skills Disponibles``
            body without the header). Empty means the section is left out.
        agents_section: Sub-agents only. Pre-rendered agents block
            (``agentes_subagente.jinja`` output, header included). Empty
            means the section is left out.
        temp_dir: Temporary directory path. Empty means the section is left out.

    Returns:
        The system prompt string.
    """

    # Date
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
  
    
    if agent_name is not None:
        result = get_agent_prompt(agent_name)
        if result.get("status") == "success":
            base = result.get("data", "") or ""
            if tools is None:
                tools = _agent_tool_names(agent_name)
            return agent.prompt(
                "subagent_prompt",
                base=base,
                # AGENT.md (comportamiento general) se inyecta antes de MANDATORY.
                behavior=_read_agent_md(),
                mandatory=_mandatory_block(tools),
                seguridad=_security_block(tools),
                fecha=fecha,
                skills_section=skills_section,
                agents_section=agents_section,
                temp_dir=temp_dir,
            )
        logger.warning(
            "Agent '%s' no encontrado; usando system prompt del router.", agent_name
        )

    # Router: system_prompt.jinja es SIEMPRE la base; AGENT.md se inyecta como ## Behavior.
    if tools is None:
        tools = _all_tool_names()

    # Fase 6: el router decide cuándo paralelizar. Llamadas independientes
    # en el mismo bloque corren en paralelo con gather y barrera.
    try:
        paralelizacion = agent.prompt("paralelizacion") if tools else ""
    except FileNotFoundError:
        logger.warning("Prompt paralelizacion.md no encontrado; no se inyecta Paralelización.")
        paralelizacion = ""

    return agent.prompt(
        "system_prompt",
        tools=tools,
        # The agents section is part of the template (system_prompt.jinja).
        agentes=router_agents(tools, task_perms),
        paralelizacion=paralelizacion,
        # AGENT.md (comportamiento general) se inyecta antes de MANDATORY.
        behavior=_read_agent_md(),
        mandatory=_mandatory_block(tools),
        # Reglas de seguridad al final (después de lo que viene del usuario/admin).
        # Con el modelo de decisión habilitado las reglas van a él, no al prompt.
        seguridad=_security_block(tools, decision=agent.decision_ready),
        fecha=fecha,
        skills_section=skills_section,
        temp_dir=temp_dir,
    )


def build_user_message(
    user_message: str,
    context: str = "",
    file_contents: list[tuple[str, str]] | None = None,
    frontier: str = "",
) -> str:
    """Render the current user content via ``user_prompt.jinja``.

    Variable per-turn data (context files, attachments, pending frontier)
    travels in the user message, never in the system prompt. The system
    prompt keeps only stable instructions. History keeps traveling as the
    messages array with its roles (see ``build_initial_messages``).

    Args:
        user_message: Raw current message (router text or delegation prompt).
        context: Context-files text. Router only; sub-agents stay isolated
            (pass ``""``).
        file_contents: Optional list of ``(filename, text)`` attachments,
            rendered as the ``<inicio_adjuntos>`` block.
        frontier: Pending-work resume text (``build_resume_message`` output).
            Empty means the section is left out.

    Returns:
        The rendered user content. Never raises: on any failure it falls
        back to the plain message plus attachments.
    """
    attachments_section = ""
    if file_contents:
        try:
            parts = [f"**Archivo: {fn}**\n{text}" for fn, text in file_contents]
            attachments_section = (
                "<inicio_adjuntos>\n" + "\n".join(parts) + "\n<fin_adjuntos>"
            )
        except Exception as exc:
            logger.warning("Error building attachments section: %s", exc)
            log_error(str(exc), source="loop_helpers.py:build_user_message")
    try:
        return agent.prompt(
            "user_prompt",
            user_message=user_message,
            context=context or "",
            attachments_section=attachments_section,
            frontier=frontier or "",
        )
    except Exception as exc:
        logger.warning(
            "Prompt user_prompt.jinja no encontrado o roto; usando mensaje plano."
        )
        log_error(str(exc), source="loop_helpers.py:build_user_message")
        if attachments_section:
            return f"{user_message}\n\n{attachments_section}"
        return user_message


def build_initial_messages(
    session_manager: SessionManager,
    session_id: str,
    system_prompt: str,
    user_message: str,
    max_turns: int = -1,
) -> list[dict[str, Any]]:
    """Build the initial messages array.

    Structure::

        [{"role": "system", "content": ...},
         ...session history (filtered by max_turns)...,
         {"role": "user", "content": current_message}]

    Args:
        session_manager: The ``SessionManager`` instance.
        session_id: Session ID to load history.
        system_prompt: Built system prompt.
        user_message: Current user message.
        max_turns: Number of recent turns to load (``-1`` = all).

    Returns:
        Messages array ready for the API.
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
    ]


    history = session_manager.load_messages(session_id, max_turns=max_turns)
    for msg in history:
        role = msg.get("role", "")
        if role == "system":
            continue  # Use our system prompt, not the saved one
        if role == "title":
            continue  # Title-tracking row: never sent to the LLM
        if role == "decisor":
            continue  # Decision-tracking row: never sent to the LLM

        entry: dict[str, Any] = {"role": role}

        content = msg.get("content")
        if content is not None:
            entry["content"] = content

        tool_calls = msg.get("tool_calls")
        if tool_calls:
            entry["tool_calls"] = tool_calls

        if role == "tool":
            tool_call_id = msg.get("tool_call_id")
            if tool_call_id:
                entry["tool_call_id"] = tool_call_id
            tool_name = msg.get("tool_name")
            if tool_name:
                entry["tool_name"] = tool_name

        messages.append(entry)

    messages.append({"role": "user", "content": user_message})

    return messages


async def execute_tool(agent: Agent, tc: dict[str, Any]) -> Any:
    """Execute a tool call by name, enforcing runtime permissions.

    Defense in depth: ``filter_tools`` decides which tools are *shown* to
    the LLM, but every *execution* is re-validated here against the
    effective permissions of the running agent (deny by default). A denied
    attempt returns a permission error as a contract response — the loop
    keeps running and the LLM can react to the error.

    Delegates to ``agent.tools._execute_tool`` which handles both native
    and external tools and returns the unified contract
    ``{status, message, data, usage}``.

    The full contract is returned so the frontend can read the authoritative
    ``status`` (``"success"`` / ``"error"``) and mark the tool accordingly.
    The LLM-facing payload (``data`` on success, ``{"error": message}`` on
    error) is extracted by the caller (loop.py) when building the tool
    message, so the model's view is unchanged.

    Args:
        agent: The ``Agent`` instance (provides ``tools``).
        tc: Normalized tool call with ``name`` and ``args``.

    Returns:
        The unified contract dict ``{status, message, data, usage}``.
    """
    tool_name = tc["name"]
    tool_args = tc.get("args", {})

    # --- Runtime permission check (deny by default) ---
    # A parallel-loop snapshot (ContextVar) takes precedence over the shared
    # Tools attribute, so concurrent calls cannot overwrite each other.
    snapshot = _tool_call_ctx.get()
    if snapshot is not None and "tool_permissions" in snapshot:
        effective_perms = snapshot["tool_permissions"]
    else:
        effective_perms = getattr(agent.tools, "_current_tool_permissions", None)
    if not is_tool_allowed(effective_perms, tool_name, tool_args):
        logger.warning(
            "Permission denied: tool '%s' is not explicitly allowed for the "
            "running agent.",
            tool_name,
        )
        log_error(
            f"Permission denied for tool '{tool_name}'.",
            source="loop_helpers.py:execute_tool(permission)",
        )
        return make_error_response(
            message=f"Permission denied for tool '{tool_name}'.",
            usage=zero_usage(),
        )

    try:
        result = await agent.tools._execute_tool(tool_name, **tool_args)
    except Exception as e:
        logger.exception("Tool '%s' failed", tool_name)
        log_error(str(e), source="loop_helpers.py:execute_tool")
        return make_error_response(
            message=f"Tool '{tool_name}' failed: {e}",
            usage=zero_usage(),
        )

    if isinstance(result, dict) and result.get("status") in ("success", "error"):
        if result.get("status") == "error":
            logger.error("Tool '%s' error: %s", tool_name, result.get("message", "Tool failed"))
        return result

    # Fallback: wrap a non-contract result as success with the raw value as data.
    return make_success_response(
        message=f"Tool '{tool_name}' executed.",
        data=result,
        usage=zero_usage(),
    )


_RATE_LIMIT_PATTERNS = (
    "rate limit",
    "too many requests",
    "request too large",
    "tokens per min",
    "tpm",
)
"""Case-insensitive substrings that identify a rate-limit / quota error."""

_RATE_LIMIT_CODES = ("429", "413")
"""HTTP status codes (word-boundary matched) that identify a rate-limit error."""

_TRANSIENT_PATTERNS = (
    "connection",
    "timed out",
    "timeout",
    "overloaded",
    "temporarily unavailable",
)
"""Case-insensitive substrings that identify a transient (retryable) error."""

_TRANSIENT_CODES = ("500", "502", "503", "504")
"""HTTP status codes (word-boundary matched) that identify a transient error."""


def classify_llm_error(exc: Exception) -> str:
    """Classify an LLM streaming exception into a retry category.

    Providers wrap HTTP errors differently (OpenRouter/Ollama), so the
    classification is tolerant: it inspects ``str(exc)`` looking for known
    rate-limit and transient-failure markers. Numeric status codes are
    matched with word boundaries so they never match inside other numbers.

    Args:
        exc: The exception raised while consuming the LLM stream.

    Returns:
        One of ``"rate_limit"`` (429/413, quota or tokens-per-minute errors),
        ``"transient"`` (timeouts, connection errors, 5xx, overloaded) or
        ``"fatal"`` (anything else: auth, bad request, etc.).
    """
    message = str(exc).lower()

    if any(pattern in message for pattern in _RATE_LIMIT_PATTERNS):
        return "rate_limit"
    if any(re.search(rf"\b{code}\b", message) for code in _RATE_LIMIT_CODES):
        return "rate_limit"

    if any(pattern in message for pattern in _TRANSIENT_PATTERNS):
        return "transient"
    if any(re.search(rf"\b{code}\b", message) for code in _TRANSIENT_CODES):
        return "transient"

    return "fatal"
