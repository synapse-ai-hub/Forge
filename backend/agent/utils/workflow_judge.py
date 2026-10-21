"""LLM-backed judgement and failure explanation of workflow runs.

Three LLM-backed steps, all fail-safe (they never raise):

- :func:`generate_output` writes the output of a run that completed every
  node (a report, or the state of what ran) from the results of all of them.

- :func:`judge_run` decides whether a run that completed every node really
  finished well. With the decision model ready it asks ``Agent.decision``
  (``noul`` question); otherwise a plain LLM call answers a JSON verdict.
  Both receive the results of the nodes.
- :func:`explain_failure` asks the LLM to tell the user, in plain language,
  why a run failed. The technical exception goes to ``error_log`` elsewhere;
  this text is what the user reads in the notification.

The spend of each call is stored in its run (``workflow_runs.usage_calls``;
purpose ``output`` / ``judge`` / ``explain``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from backend.agent.utils import workflow_db
from backend.agent.utils.decision import DECISION_CLOSE_THRESHOLD
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)

_NODE_RESULT_LIMIT = 6000
"""Characters of each node result sent to the judge (keeps the call bounded)."""

GENERIC_FAILURE_TEXT = (
    "El workflow no pudo completarse. Probá ejecutarlo de nuevo más tarde; "
    "si el problema sigue, revisá el detalle en la sesión de la ejecución."
)
"""Fallback shown when no LLM is available to explain a failure."""


def _clip(text: Any, limit: int = _NODE_RESULT_LIMIT) -> str:
    """Return ``text`` as a string cut to ``limit`` characters."""
    value = "" if text is None else str(text)
    if len(value) <= limit:
        return value
    return value[:limit] + "… (recortado)"


def _chat_model(agent) -> tuple[str | None, str | None]:
    """Return the ``(model, provider)`` the app uses for chat, if any."""
    try:
        model = agent.default_model
        provider = agent.provider
        if model:
            return model, provider
    except Exception as exc:
        log_error(str(exc), source="workflow_judge.py:_chat_model")
    return None, None


def _parse_verdict(raw: str) -> tuple[bool, str] | None:
    """Parse the JSON verdict of the LLM judge, or ``None`` when unreadable."""
    match = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("ok"), bool):
        return None
    return data["ok"], str(data.get("reason") or "").strip()


OUTPUT_ATTEMPTS = 3
"""Tries of the output call before the final node's result is used instead."""

_OUTPUT_TOTAL_LIMIT = 120000
"""Characters of node results sent to the output call (shared among the nodes)."""


async def generate_output(
    agent,
    workflow_name: str,
    run_id: str,
    description: str,
    nodes: list[dict[str, Any]],
    results: dict[str, str],
) -> str | None:
    """Generate the output of a run from the results of all its nodes.

    One ``llm_process`` call with the chat model. Each node contributes what
    it returned (the ``data`` of its contract). Transient failures are tried
    again with a growing wait.

    Args:
        agent: Agent singleton (LLM access).
        workflow_name: Workflow name.
        run_id: Run being closed (for the usage row).
        description: Workflow description (what is expected of it).
        nodes: Normalized workflow nodes.
        results: Node id → committed result.

    Returns:
        The generated output, or ``None`` when it could not be produced (the
        caller keeps the result of the final node).
    """
    try:
        model, provider = _chat_model(agent)
        if not model:
            return None
        items = [
            (n.get("id", ""), n.get("type", ""), str(results.get(n.get("id", ""), "") or ""))
            for n in nodes
            if isinstance(n, dict)
        ]
        share = max(_OUTPUT_TOTAL_LIMIT // max(len(items), 1), 2000)
        nodes_text = "\n\n".join(
            f"#### {node_id} ({node_type})\n\n{_clip(text, share)}" for node_id, node_type, text in items
        ) or "(sin nodos)"
        prompt = agent.prompt(
            "output_workflow",
            name=workflow_name,
            description=description or "(sin descripción)",
            nodes_text=nodes_text,
        )
        for attempt in range(OUTPUT_ATTEMPTS):
            response = await agent.llm_process(
                model=model,
                provider=provider,
                prompt=prompt,
                temperature=0.2,
                top_p=0.7,
                reasoning=False,
            )
            if isinstance(response, dict):
                workflow_db.record_usage(
                    workflow_name, run_id, "output", provider, model, response.get("usage"),
                )
                text = str(response.get("data") or "").strip()
                if response.get("status") == "success" and text:
                    return text
            if attempt < OUTPUT_ATTEMPTS - 1:
                await asyncio.sleep(2 ** (attempt + 1))
        return None
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log_error(str(exc), source="workflow_judge.py:generate_output")
        return None


async def judge_run(
    agent,
    workflow_name: str,
    run_id: str,
    description: str,
    nodes: list[dict[str, Any]],
    results: dict[str, str],
    final_text: str,
) -> tuple[bool, str]:
    """Decide whether a run that completed every node finished well.

    Args:
        agent: Agent singleton (decision model and LLM access).
        workflow_name: Workflow name.
        run_id: Run being judged (for the usage row).
        description: Workflow description (what was expected).
        nodes: Normalized workflow nodes.
        results: Node id → committed result.
        final_text: Final answer of the run.

    Returns:
        ``(ok, reason)``. ``reason`` is plain language and only meaningful
        when ``ok`` is ``False``. Any failure of the judge itself returns
        ``(True, "")``: the node statuses already said the run completed.
    """
    try:
        node_items = [
            {
                "id": n.get("id", ""),
                "type": n.get("type", ""),
                "result": _clip(results.get(n.get("id", ""), "")),
            }
            for n in nodes
            if isinstance(n, dict)
        ]
        if getattr(agent, "decision_ready", False):
            state = {
                "workflow": workflow_name,
                "description": description,
                "nodes": node_items,
                "final": _clip(final_text),
            }
            questions = {
                "done": {
                    "type": "noul",
                    "instructions": agent.prompt("judge_workflow", decision=True),
                }
            }
            response = await agent.decision(state, questions)
            data = (response or {}).get("data") or {}
            if data.get("available"):
                workflow_db.record_usage(
                    workflow_name, run_id, "judge",
                    data.get("provider"), data.get("model"),
                    (response or {}).get("usage"),
                )
                verdict = ((data.get("answers") or {}).get("done") or {}).get("noul")
                if isinstance(verdict, (int, float)) and not isinstance(verdict, bool):
                    if float(verdict) >= DECISION_CLOSE_THRESHOLD:
                        return True, ""
                    return False, (
                        "El workflow se ejecutó, pero el resultado no parece cumplir "
                        "con lo que se esperaba de él."
                    )
            # Decision model unavailable or unreadable: fall through to the LLM.

        model, provider = _chat_model(agent)
        if not model:
            return True, ""
        nodes_text = "\n\n".join(
            f"- {item['id']} ({item['type']}):\n{item['result']}" for item in node_items
        ) or "(sin nodos)"
        prompt = agent.prompt(
            "judge_workflow",
            decision=False,
            name=workflow_name,
            description=description or "(sin descripción)",
            nodes_text=nodes_text,
            final_text=_clip(final_text),
        )
        response = await agent.llm_process(
            model=model,
            provider=provider,
            prompt=prompt,
            temperature=0.0,
            top_p=0.6,
            max_tokens=800,
            json_format=True,
            reasoning=False,
        )
        if not isinstance(response, dict):
            return True, ""
        workflow_db.record_usage(
            workflow_name, run_id, "judge", provider, model, response.get("usage"),
        )
        if response.get("status") != "success":
            return True, ""
        parsed = _parse_verdict(str(response.get("data") or ""))
        if parsed is None:
            return True, ""
        return parsed
    except Exception as exc:
        log_error(str(exc), source="workflow_judge.py:judge_run")
        return True, ""


async def explain_failure(
    agent,
    workflow_name: str,
    run_id: str,
    description: str,
    failures: list[dict[str, str]],
    attempts: int,
) -> str:
    """Explain in plain language why a run failed.

    Args:
        agent: Agent singleton (LLM access).
        workflow_name: Workflow name.
        run_id: Failed run (for the usage row).
        description: Workflow description.
        failures: One dict per failed node with ``node``, ``type`` and
            ``error`` (the technical message).
        attempts: Attempts the run consumed.

    Returns:
        A user-friendly explanation. Falls back to
        :data:`GENERIC_FAILURE_TEXT` when no LLM can produce it.
    """
    try:
        model, provider = _chat_model(agent)
        if not model:
            return GENERIC_FAILURE_TEXT
        failures_text = "\n".join(
            f"- Nodo «{f.get('node', '?')}» (tipo {f.get('type', '?')}): {_clip(f.get('error', ''), 1500)}"
            for f in failures
        ) or "- (no se registró el detalle del fallo)"
        prompt = agent.prompt(
            "explain_workflow_error",
            name=workflow_name,
            description=description or "(sin descripción)",
            attempts=attempts,
            failures_text=failures_text,
        )
        response = await agent.llm_process(
            model=model,
            provider=provider,
            prompt=prompt,
            temperature=0.2,
            top_p=0.7,
            max_tokens=500,
            reasoning=False,
        )
        if not isinstance(response, dict):
            return GENERIC_FAILURE_TEXT
        workflow_db.record_usage(
            workflow_name, run_id, "explain", provider, model, response.get("usage"),
        )
        text = str(response.get("data") or "").strip()
        if response.get("status") != "success" or not text:
            return GENERIC_FAILURE_TEXT
        return text
    except Exception as exc:
        log_error(str(exc), source="workflow_judge.py:explain_failure")
        return GENERIC_FAILURE_TEXT
