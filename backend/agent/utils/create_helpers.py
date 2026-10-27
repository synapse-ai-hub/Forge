"""Shared helpers of the creation flows (skills, tools, agents and workflows).

This module holds what the creation endpoints share: the resolution of the
model/provider of a creator turn and the resource context the agent and
workflow creators see in their prompts (everything the system has plus what
the user picked in the permission cards of the setup form).

Imported by ``backend/routes/create/``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections.abc import Awaitable, Callable
from typing import Any, AsyncGenerator

# ---------------------------------------------------------------------------
# Ensure the project root is in sys.path for absolute imports
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(_current_dir)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.loop.constants import LLM_BACKOFF_BASE_SECONDS, MAX_LLM_RETRIES
from backend.agent.permissions import get_tool_permissions
from backend.agent.utils import provider_keys
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.rate_limit_handler import classify_error_category, get_retry_delay
from backend.instances import agent

logger = logging.getLogger(__name__)

_DEFAULT_MAX_ITERATIONS = 25
_DEFAULT_TEMPERATURE = 0.3
_DEFAULT_TOP_P = 0.8
_DEFAULT_MAX_TOKENS = 3000


async def build_resource_context(
    agentes: list[str] | None = None,
    tools: list[str] | None = None,
    tool_args: dict[str, dict[str, Any]] | None = None,
    skills: list[str] | None = None,
    rag: list[str] | None = None,
    with_skills: bool = False,
    with_mcp: bool = False,
) -> dict[str, Any]:
    """Collect what a creator has to see: everything the system has, and what the user picked.

    The creators see all the agents, tools, skills and RAG collections (the router only sees
    what its permissions allow). The user picks resources in the permission cards of the form:
    those are mandatory, the creator may add others. The data goes to the jinja prompts as it
    is (``recursos_creador.jinja`` renders it); nothing is formatted here.

    Args:
        agentes: Agents the user picked.
        tools: Tools the user picked.
        tool_args: Arguments the user filled for the tools they picked (tool name → arguments).
        skills: Skills the user picked.
        rag: RAG collections the user picked.
        with_skills: Whether the skills are part of what the creator can use.
        with_mcp: Whether the MCP servers are part of what the creator can use.

    Returns:
        The variables of the prompts: ``seleccion`` (what the user picked) and
        ``agentes_disponibles``, ``tools_disponibles``, ``skills_disponibles``,
        ``rag_disponibles`` and ``mcp_disponibles`` (everything that exists).
    """
    from backend.agent.utils.agent_helpers import get_agents_list, get_mcp_list, get_skills_list, get_tools_list
    from backend.agent.utils.rag_helpers import list_collections

    agentes_disponibles = []
    for item in get_agents_list():
        permissions = json.loads(get_tool_permissions(item["name"]).get("data") or "{}")
        agentes_disponibles.append({
            **item,
            "tools": sorted(name for name, action in permissions.items() if action == "allow" or isinstance(action, dict)),
        })
    mcp_disponibles: list[dict[str, Any]] = []
    if with_mcp:
        try:
            mcp_disponibles = [m for m in await get_mcp_list() if m.get("status") != "disabled"]
        except Exception as exc:
            logger.warning("No se pudieron listar los servidores MCP: %s", exc)
    return {
        "seleccion": {
            "agentes": list(agentes or []),
            "tools": list(tools or []),
            "tool_args": dict(tool_args or {}),
            "skills": list(skills or []),
            "rag": list(rag or []),
        },
        "agentes_disponibles": agentes_disponibles,
        "tools_disponibles": get_tools_list(),
        "skills_disponibles": get_skills_list() if with_skills else [],
        "rag_disponibles": list_collections(),
        "mcp_disponibles": mcp_disponibles,
    }


def _resolve_create_model_provider() -> tuple[str | None, str]:
    """Resolve the (model, provider) used by the creation flows.

    The agent's current selection is preferred when that provider
    has a live client; otherwise the first OpenAI-compatible provider
    with a live client is used together with its first catalogued
    model. Falls back to the agent's saved selection.

    Returns:
        Tuple of ``(model, provider)``. ``model`` may be ``None``
        when no provider is configured at all.
    """
    current_model = getattr(agent, "_resolved_model", None)
    current_provider = (getattr(agent, "provider", None) or "").strip()
    if current_model and current_provider and _cloud_client_available(current_provider):
        return current_model, current_provider
    try:
        get_client = getattr(agent, "get_openai_client", None)
        if callable(get_client):
            for _pid, _info in provider_keys.PROVIDER_REGISTRY.items():
                if str(_info.get("api_type") or "") != "openai-compatible":
                    continue
                prov_u = _pid
                if get_client(prov_u) is None:
                    continue
                try:
                    from backend.agent.utils import model_catalog
                    cached = model_catalog.get_models(_pid)
                except Exception:
                    cached = []
                if cached:
                    return cached[0], prov_u
    except Exception:
        pass
    return current_model, current_provider or "LOCAL"


def _cloud_client_available(prov_u: str) -> bool:
    """Check whether a cloud provider has an instantiated client.

    Args:
        prov_u: Provider name as configured (models.dev id).

    Returns:
        ``True`` when the provider can serve a creation task right now.
    """
    try:
        if prov_u == "google":
            return getattr(agent, "google_client", None) is not None
        get_client = getattr(agent, "get_openai_client", None)
        if callable(get_client):
            return get_client(prov_u) is not None
        return False
    except Exception:
        return False


def resolve_create_model_provider(
    model: str | None = None, provider: str | None = None
) -> tuple[str, str]:
    """Resolve the (model, provider) honoring the user's per-task selection.

    The creation interfaces let the user pick a cloud provider and model for
    a single creation task (ephemeral, never persisted). Only cloud providers
    with an instantiated client are accepted; anything else falls back to the
    default resolution (``_resolve_create_model_provider``).

    Args:
        model: Model identifier chosen by the user.
        provider: Curated cloud provider name chosen by the user (any
            OpenAI-compatible provider or ``google``).

    Returns:
        Tuple of ``(model, provider)``.
    """
    prov_u = (provider or "").strip()
    model_clean = (model or "").strip()
    if model_clean and _cloud_client_available(prov_u):
        return model_clean, prov_u
    return _resolve_create_model_provider()


def _llm_retry_plan(exc: Exception, attempt: int) -> tuple[float, str] | None:
    """Decide whether a failed in-memory LLM call is retried, like the chat loop.

    Only ``rate_limit`` and ``transient`` errors are retried, up to
    ``MAX_LLM_RETRIES`` times, with exponential back-off that honors the
    provider's ``retry_after`` hint. Fatal, budget and too-large errors end
    the flow.

    Args:
        exc: Exception raised by the LLM call.
        attempt: Retries already made for this iteration (0 on the first failure).

    Returns:
        ``(delay_seconds, notice)`` when the call must be retried, else ``None``.
    """
    category = classify_error_category(exc)
    if category not in ("rate_limit", "transient") or attempt >= MAX_LLM_RETRIES:
        return None
    delay = max(
        LLM_BACKOFF_BASE_SECONDS * (2 ** attempt),
        get_retry_delay(exc, LLM_BACKOFF_BASE_SECONDS, 60.0),
    )
    if category == "rate_limit":
        notice = f"Rate limit alcanzado, reintentando (intento {attempt + 1} de {MAX_LLM_RETRIES})..."
    else:
        notice = "Error transitorio, reintentando..."
    return delay, notice


async def stream_tool_calling_loop(
    msgs: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    friendly_error: str,
    model: str | None = None,
    provider: str | None = None,
    max_iter: int = _DEFAULT_MAX_ITERATIONS,
    temperature: float = _DEFAULT_TEMPERATURE,
    top_p: float = _DEFAULT_TOP_P,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
    run_tool: Callable[[str, dict[str, Any]], Awaitable[Any]] | None = None,
    on_usage: Callable[[str | None, str | None, dict[str, Any] | None], None] | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Run an in-memory tool-calling loop and yield SSE event dicts.

    Unlike the chat loop, nothing is persisted: ``msgs`` is mutated in place
    (assistant message with tool calls + tool result messages are appended)
    so callers can inspect the full conversation afterwards. Used by flows
    that run outside any session: the workflow-runner agent node (with its
    own ``run_tool`` and spend tracking) and the workflow YAML generator
    (no tools).

    Args:
        msgs: Mutable conversation list; system and user messages are
            expected to already be present.
        tools: Tool definitions passed to the provider for function calling.
        friendly_error: User-friendly error message yielded on failure.
        model: Model identifier sent to the provider. If ``None``,
            resolved via ``_resolve_create_model_provider``.
        provider: Provider name (any curated provider id or ``"LOCAL"``). If ``None``,
            resolved via ``_resolve_create_model_provider``.
        max_iter: Maximum number of loop iterations.
        temperature: Sampling temperature.
        top_p: Nucleus sampling parameter.
        max_tokens: Maximum output tokens per request.
        run_tool: Coroutine function that runs a tool call from its name and
            arguments; ``agent.tools._execute_tool`` when ``None``.
        on_usage: Called with the provider, the model and the usage report of
            every LLM call (zero tokens when no usage was captured); when
            ``None`` the call is recorded in ``creators``.

    Yields:
        SSE event dicts: ``chunk``, ``reasoning``, ``tool_call``,
        ``tool_result``, ``retry``, ``aborted`` or ``error``.
    """
    if model is None or provider is None:
        model, provider = _resolve_create_model_provider()

    def _usage(iter_usage: dict[str, Any] | None) -> None:
        """Hand the usage of one LLM call to ``on_usage`` or record it in ``creators``.

        Args:
            iter_usage: Usage report of the call, or ``None`` when none was captured.
        """
        try:
            if on_usage is not None:
                on_usage(provider, model, iter_usage)
                return
            from backend.agent.utils.spend_handler import record_creator_call

            record_creator_call("creator:generate", provider, model, iter_usage)
        except Exception:
            pass

    # Only the tools offered to the LLM may run (deny by default).
    offered_tools = {(t.get("function") or {}).get("name") for t in tools}
    iteration = 0
    llm_attempt = 0
    while iteration < max_iter:
        iteration += 1

        collected_content = ""
        tool_calls = None
        iter_usage: dict[str, Any] | None = None

        try:
            async for event in agent.llm_streaming(
                model=model,
                provider=provider,
                messages=msgs,
                tools=tools,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                cleaned_output=True,
            ):
                if event["type"] == "chunk":
                    collected_content += event.get("content", "")
                    yield {"type": "chunk", "content": event.get("content", "")}

                elif event["type"] == "reasoning":
                    yield {"type": "reasoning", "content": event.get("content", "")}

                elif event["type"] == "usage":
                    iter_usage = event.get("content") or {}

                elif event["type"] == "tool_calls_detected":
                    tool_calls = event["content"]
                    break

                elif event["type"] == "aborted":
                    yield {"type": "aborted", "content": "Stream cancelado."}
                    return

        except Exception as e:
            logger.exception("Error en streaming create agent: %s", e)
            _usage(iter_usage)
            # The failed attempt never reached the agent's spend record:
            # count it here (zero tokens when no usage was captured).
            try:
                agent._record_spend(provider, model, iter_usage)
            except Exception:
                pass
            plan = _llm_retry_plan(e, llm_attempt)
            if plan is None:
                yield {"type": "error", "content": friendly_error}
                return
            delay, notice = plan
            logger.warning("Creator LLM error, retrying in %.0fs: %s", delay, e)
            yield {"type": "retry", "content": notice}
            await asyncio.sleep(delay)
            llm_attempt += 1
            iteration -= 1
            continue
        llm_attempt = 0

        # Contemplate this LLM call (it never produces messages rows).
        _usage(iter_usage)

        if tool_calls:
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": collected_content,
                "tool_calls": tool_calls,
            }
            msgs.append(assistant_msg)

            for tc in tool_calls:
                tc_id = tc.get("id", "")
                tc_name = tc.get("name", "")
                tc_args = tc.get("args", {})

                yield {"type": "tool_call", "content": {"name": tc_name, "args": tc_args}}

                try:
                    if tc_name not in offered_tools:
                        result = {"status": "error", "message": f"Permission denied for tool '{tc_name}'."}
                        log_error(
                            f"Permission denied for tool '{tc_name}'.",
                            source="create_helpers.py:create(permission)",
                        )
                    elif run_tool is not None:
                        result = await run_tool(tc_name, tc_args)
                    else:
                        result = await agent.tools._execute_tool(tc_name, **tc_args)
                except Exception as e:
                    logger.exception("Tool '%s' failed", tc_name)
                    log_error(str(e), source="create_helpers.py:create")
                    result = {"status": "error", "message": str(e)}

                # Extract the result content
                if isinstance(result, dict):
                    if result.get("status") == "error":
                        result_content = result.get("message", "Error desconocido")
                    else:
                        result_content = result.get("data", json.dumps(result))
                else:
                    result_content = str(result)

                if not isinstance(result_content, str):
                    result_content = json.dumps(result_content)

                yield {
                    "type": "tool_result",
                    "content": {"name": tc_name, "result": result_content},
                }

                msgs.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": result_content,
                })

            # Continue loop — next iteration streams the response with tool results
        else:
            # No tool calls — finished
            break
