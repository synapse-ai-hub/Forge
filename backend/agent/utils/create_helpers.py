"""Shared tool-calling loop for the creation flows (skills and tools).

This module implements the agent tool-calling loop used by the creation
endpoints in ``backend/routes/create.py``. It is the single source of
truth for the loop so the same behaviour (streaming events, tool
execution, message accumulation) is shared between the skill and tool
creation flows instead of being duplicated inline in the routes.

The loop streams LLM events (chunks, reasoning, tool calls), executes
each requested tool through ``agent.tools._execute_tool`` and appends the
assistant/tool messages to the provided ``msgs`` list in place.

Imported by ``backend/routes/create.py``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, AsyncGenerator

# ---------------------------------------------------------------------------
# Ensure the project root is in sys.path for absolute imports
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(_current_dir)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.loop.constants import LLM_BACKOFF_BASE_SECONDS, MAX_LLM_RETRIES
from backend.agent.permissions import is_tool_allowed
from backend.agent.utils import provider_keys
from backend.agent.utils.rate_limit_handler import classify_error_category, get_retry_delay
from backend.instances import agent

logger = logging.getLogger(__name__)

_DEFAULT_MAX_ITERATIONS = 25
_DEFAULT_TEMPERATURE = 0.3
_DEFAULT_TOP_P = 0.8
_DEFAULT_MAX_TOKENS = 3000

_INTERVIEW_TOOLS_PERMS: dict[str, str] = {
    "read": "allow",
    "write": "allow",
    "edit": "allow",
    "shell": "allow",
    "list_dir": "allow",
    "glob": "allow",
    "grep": "allow",
    "websearch": "allow",
    "webfetch": "allow",
    "query_model_capabilities": "allow",
}
"""Native tools enabled during creation interviews (read/explore + web)."""


def _llm_retry_plan(exc: Exception, attempt: int) -> tuple[float, str] | None:
    """Decide whether a failed creator LLM call is retried, like the chat loop.

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


async def stream_interview_loop(
    prompt: str,
    interview_tool: dict[str, Any],
    friendly_error: str,
    model: str | None = None,
    provider: str | None = None,
    max_iter: int = _DEFAULT_MAX_ITERATIONS,
    temperature: float = _DEFAULT_TEMPERATURE,
    top_p: float = _DEFAULT_TOP_P,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> AsyncGenerator[dict[str, Any], None]:
    """Run the interview phase of a creation flow with real tools enabled.

    Streams the LLM response with the inline interview tool plus the native
    tools in ``_INTERVIEW_TOOLS_PERMS`` (read/explore + web). When the model
    calls one of the native tools it is executed through
    ``agent.tools._execute_tool`` and the conversation continues so the model
    can inspect files or search the web before answering. When the model calls
    the interview tool the loop ends.

    Args:
        prompt: Fully formatted interview prompt (first user message).
        interview_tool: Inline tool schema that closes the interview
            (e.g. ``responder_interview``).
        friendly_error: User-friendly error message yielded on failure.
        model: Model identifier sent to the provider. If ``None``,
            resolved via ``_resolve_create_model_provider``.
        provider: Provider name. If ``None``, resolved via
            ``_resolve_create_model_provider``.
        max_iter: Maximum number of loop iterations.
        temperature: Sampling temperature.
        top_p: Nucleus sampling parameter.
        max_tokens: Maximum output tokens per request.

    Yields:
        SSE event dicts: ``chunk``, ``reasoning``, ``tool_call``,
        ``tool_result``, ``aborted``, ``error`` and finally
        ``_interview_args`` with the interview tool arguments (or ``None``
        if the interview tool was never called; internal event, not for
        the client).
    """
    if model is None or provider is None:
        model, provider = _resolve_create_model_provider()

    interview_name = (interview_tool.get("function") or {}).get("name", "")
    tools: list[dict[str, Any]] = [interview_tool]
    try:
        tools += list(agent.tools.tools_registry(_INTERVIEW_TOOLS_PERMS))
    except Exception as e:
        logger.warning("No se pudieron listar tools para la entrevista: %s", e)

    msgs: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

    _iteration = 0
    llm_attempt = 0
    while _iteration < max_iter:
        _iteration += 1
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
            logger.exception("Error en streaming interview: %s", e)
            try:
                from backend.agent.utils.spend_handler import record_creator_call

                record_creator_call("creator:interview", provider, model, iter_usage)
            except Exception:
                pass
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
            logger.warning("Interview LLM error, retrying in %.0fs: %s", delay, e)
            yield {"type": "retry", "content": notice}
            await asyncio.sleep(delay)
            llm_attempt += 1
            _iteration -= 1
            continue
        llm_attempt = 0

        # Contemplate this interview LLM call (tracked in creator_calls
        # since it never produces messages rows).
        try:
            from backend.agent.utils.spend_handler import record_creator_call

            record_creator_call("creator:interview", provider, model, iter_usage)
        except Exception:
            pass

        if not tool_calls:
            break

        # Interview tool → close the phase and hand the args to the caller.
        interview_tc = next(
            (tc for tc in tool_calls if tc.get("name") == interview_name), None
        )
        if interview_tc is not None:
            yield {"type": "_interview_args", "content": interview_tc.get("args", {})}
            return

        # Native tools → execute and keep interviewing with the results.
        msgs.append({
            "role": "assistant",
            "content": collected_content,
            "tool_calls": tool_calls,
        })
        for tc in tool_calls:
            tc_id = tc.get("id", "")
            tc_name = tc.get("name", "")
            tc_args = tc.get("args", {})

            yield {"type": "tool_call", "content": {"name": tc_name, "args": tc_args}}

            try:
                if not is_tool_allowed(_INTERVIEW_TOOLS_PERMS, tc_name, tc_args):
                    result = {"status": "error", "message": f"Permission denied for tool '{tc_name}'."}
                else:
                    result = await agent.tools._execute_tool(tc_name, **tc_args)
            except Exception as e:
                logger.exception("Tool '%s' failed during interview", tc_name)
                result = {"status": "error", "message": str(e)}

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

    # Interview tool never called within the iteration budget.
    yield {"type": "_interview_args", "content": None}


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
) -> AsyncGenerator[dict[str, Any], None]:
    """Run the agent tool-calling loop and yield SSE event dicts.

    Streams the LLM response with the given ``tools`` and executes every
    tool call through ``agent.tools._execute_tool``. ``msgs`` is mutated in
    place (assistant message with tool calls + tool result messages are
    appended) so callers can inspect the full conversation afterwards.

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

    Yields:
        SSE event dicts: ``chunk``, ``reasoning``, ``tool_call``,
        ``tool_result``, ``aborted`` or ``error``.
    """
    if model is None or provider is None:
        model, provider = _resolve_create_model_provider()
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
            try:
                from backend.agent.utils.spend_handler import record_creator_call

                record_creator_call("creator:generate", provider, model, iter_usage)
            except Exception:
                pass
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

        # Contemplate this generation LLM call (tracked in creator_calls
        # since it never produces messages rows).
        try:
            from backend.agent.utils.spend_handler import record_creator_call

            record_creator_call("creator:generate", provider, model, iter_usage)
        except Exception:
            pass

        # ── Process tool calls ──────────────────────────────────────────
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
                    else:
                        result = await agent.tools._execute_tool(tc_name, **tc_args)
                except Exception as e:
                    logger.exception("Tool '%s' failed", tc_name)
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

            # Continue loop → next iteration streams the response with tool results
        else:
            # No tool calls → finished
            break
