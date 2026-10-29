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

Each call is stored as a row of its run in ``workflow_runs`` (kind ``output``,
``decision``, ``judge`` or ``explain``), with its verdict or text and its spend.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from backend.agent.llm.decision import DECISION_MODEL_NOT_FOUND_PREFIX
from backend.agent.utils import workflow_db
from backend.agent.utils.decision import DECISION_CLOSE_THRESHOLD
from backend.agent.utils.error_logger import log_error

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.agent.agent import Agent

logger = logging.getLogger(__name__)

GENERIC_FAILURE_TEXT = (
    "El workflow no pudo completarse. Probá ejecutarlo de nuevo más tarde; "
    "si el problema sigue, abrí la notificación y usá «Revisar con el agente»."
)
"""Fallback shown when no LLM is available to explain a failure."""


def _as_str(value: Any) -> str:
    """Convert a value to text, whole.

    Args:
        value: Value to convert.

    Returns:
        The text, or an empty string for ``None``.
    """
    return "" if value is None else str(value)


def _chat_model(agent: Agent) -> tuple[str | None, str | None]:
    """Get the model the app uses for chat.

    Args:
        agent: Agent singleton.

    Returns:
        ``(model, provider)``, or ``(None, None)`` when none is configured.
    """
    try:
        model = agent.default_model
        provider = agent.provider
        if model:
            return model, provider
    except Exception as exc:
        log_error(str(exc), source="workflow_judge.py:_chat_model")
    return None, None


def _parse_verdict(raw: str) -> tuple[bool, str] | None:
    """Parse the JSON verdict of the LLM judge.

    Args:
        raw: Text answered by the LLM.

    Returns:
        ``(ok, reason)``, or ``None`` when the text is not a readable verdict.
    """
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
"""Tries of the output call."""


def _load_output_instructions(workflow_name: str) -> str:
    """Load the optional per-workflow output instructions.

    Args:
        workflow_name: Workflow name (``<name>_output.toml`` in the prompts dir).

    Returns:
        The rendered toml text, or an empty string when absent.
    """
    try:
        from backend.agent.utils.workflow_loader import load_prompt_file

        loaded = load_prompt_file(f"{workflow_name}_output")
        if isinstance(loaded, dict) and loaded.get("status") == "success":
            return str(loaded.get("data") or "").strip()
    except Exception:
        pass
    return ""


async def generate_output(
    agent: Agent,
    workflow_name: str,
    run_id: str,
    description: str,
    nodes: list[dict[str, Any]],
    results: dict[str, str],
) -> str | None:
    """Generate the output of a run from the results of all its nodes.

    One ``llm_process`` call with the chat model: instructions go as
    ``system``, every node result goes as ``user``. Each node contributes
    what it returned (the ``data`` of its contract). Transient failures
    are tried again with a growing wait.

    Args:
        agent: Agent singleton (LLM access).
        workflow_name: Workflow name.
        run_id: Run being closed (for the usage row).
        description: Workflow description (what is expected of it).
        nodes: Normalized workflow nodes.
        results: Node id → committed result.

    Returns:
        The generated output, or ``None`` when it could not be produced.
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
        nodes_text = "\n\n".join(
            f"#### {node_id} ({node_type})\n\n{text}" for node_id, node_type, text in items
        ) or "(sin nodos)"
        system = agent.prompt("output_workflow")
        specific = _load_output_instructions(workflow_name)
        user_parts = [
            f"### Workflow\n\n{workflow_name}",
            f"### Qué hace el workflow\n\n{description or '(sin descripción)'}",
            f"### Resultados de los nodos\n\n{nodes_text}",
        ]
        if specific:
            user_parts.append(f"### Instrucciones específicas del reporte\n\n{specific}")
        user = "\n\n".join(user_parts)
        for attempt in range(OUTPUT_ATTEMPTS):
            response = await agent.llm_process(
                model=model,
                provider=provider,
                prompt=user,
                system_content=system,
                temperature=0.2,
                top_p=0.7,
                reasoning=False,
            )
            if isinstance(response, dict):
                workflow_db.record_engine_row(
                    run_id, "output", provider, model, response.get("usage"),
                    status=str(response.get("status") or "error"),
                    result=str(response.get("data") or ""),
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


def _decision_model_not_found(response: Any) -> bool:
    """Check whether a decision answer means the configured model does not exist.

    Args:
        response: Contract answer of ``Agent.decision``.

    Returns:
        ``True`` when the model is unavailable because its slug was not found
        (not when it is simply disabled or unconfigured).
    """
    if not isinstance(response, dict):
        return False
    if response.get("status") != "success":
        return False
    data = response.get("data") or {}
    if not isinstance(data, dict) or data.get("available"):
        return False
    return str(response.get("message") or "").startswith(DECISION_MODEL_NOT_FOUND_PREFIX)


async def _notify_missing_decision_model(
    workflow_name: str,
    source: str,
) -> None:
    """Tell the user that the configured decision model does not exist.

    Clean text only: the technical detail stays in the db log, it never
    reaches the UI. The notification carries no ``run_id`` on purpose: it
    is a configuration warning, not the result of the run, so opening it
    shows its own message instead of the run's output.

    Args:
        workflow_name: Workflow of the run.
        source: ``"play"``, ``"schedule"`` or ``"tool"`` (tool runs do not notify).
    """
    try:
        if source not in ("play", "schedule"):
            return
        from backend.agent.utils.notifications_helpers import notify

        await notify(
            kind="workflow" if source == "play" else "schedule",
            workflow_name=workflow_name,
            title=workflow_name,
            status="error",
            message=(
                "El modelo de decisión configurado no existe o no está disponible. "
                "El workflow se evaluó sin decisor; revisá la configuración del modelo."
            ),
        )
    except Exception as exc:
        log_error(str(exc), source="workflow_judge.py:_notify_missing_decision_model")


async def judge_run(
    agent: Agent,
    workflow_name: str,
    run_id: str,
    description: str,
    nodes: list[dict[str, Any]],
    results: dict[str, str],
    final_text: str,
    source: str = "play",
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
        source: ``"play"``, ``"schedule"`` or ``"tool"`` (only used to notify
            when the configured decision model does not exist).

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
                "result": _as_str(results.get(n.get("id", ""), "")),
            }
            for n in nodes
            if isinstance(n, dict)
        ]
        if getattr(agent, "decision_ready", False):
            state = {
                "workflow": workflow_name,
                "description": description,
                "nodes": node_items,
                "final": _as_str(final_text),
            }
            questions = {
                "done": {
                    "type": "noul",
                    "instructions": agent.prompt("judge_workflow", decision=True),
                }
            }
            response = await agent.decision(state, questions)
            data = (response or {}).get("data") or {}
            if _decision_model_not_found(response):
                await _notify_missing_decision_model(workflow_name, source)
            if data.get("available"):
                verdict = ((data.get("answers") or {}).get("done") or {}).get("noul")
                readable = isinstance(verdict, (int, float)) and not isinstance(verdict, bool)
                approved = readable and float(verdict) >= DECISION_CLOSE_THRESHOLD
                workflow_db.record_engine_row(
                    run_id, "decision", data.get("provider"), data.get("model"),
                    (response or {}).get("usage"),
                    status="approved" if approved else ("rejected" if readable else "error"),
                    result=json.dumps(data.get("answers") or {}, ensure_ascii=False),
                )
                if readable:
                    if approved:
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
            final_text=_as_str(final_text),
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
        if not isinstance(response, dict) or response.get("status") != "success":
            # The judge could not run (no model, provider down): approve
            # silently, as if it were disabled. No error row.
            return True, ""
        parsed = _parse_verdict(str(response.get("data") or ""))
        workflow_db.record_engine_row(
            run_id, "judge", provider, model, response.get("usage"),
            status="error" if parsed is None else ("approved" if parsed[0] else "rejected"),
            result=str(response.get("data") or ""),
        )
        if parsed is None:
            return True, ""
        return parsed
    except Exception as exc:
        log_error(str(exc), source="workflow_judge.py:judge_run")
        return True, ""


async def explain_failure(
    agent: Agent,
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
            f"- Nodo «{f.get('node', '?')}» (tipo {f.get('type', '?')}): {_as_str(f.get('error', ''))}"
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
        workflow_db.record_engine_row(
            run_id, "explain", provider, model, response.get("usage"),
            status=str(response.get("status") or "error"),
            result=str(response.get("data") or ""),
        )
        text = str(response.get("data") or "").strip()
        if response.get("status") != "success" or not text:
            return GENERIC_FAILURE_TEXT
        return text
    except Exception as exc:
        log_error(str(exc), source="workflow_judge.py:explain_failure")
        return GENERIC_FAILURE_TEXT
