"""Decision-model gates: step close, pending-work continuity and message guardrail.

Without a decision model enabled every gate is a no-op: the LLM done signal
is accepted, the pending work is kept and the user message is not checked
(zero extra cost). With the decision section enabled and a provider + model
selected, ``Agent.decision`` backs three gates:

- ``should_close_step``: only a ``done`` verdict with enough confidence
  deletes the step frontier; anything else leaves the rows for the next turn.
- ``should_keep_pending``: a confident topic change discards the pending work.
- ``is_message_blocked``: a confident attack verdict blocks the user message
  before the LLM runs.

Every function manages its own failures and never raises: the gates must
never break the agent loop. On any doubt the step closes, the pending work is
kept and the message goes through (fail-open).
"""

from __future__ import annotations

import json
from typing import Any

from backend.agent.utils import frontier_helpers
from backend.agent.utils.db import db_transaction
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.queries import load_query

DECISION_CLOSE_THRESHOLD = 0.8
"""Minimum ``noul`` confidence to accept a ``done`` verdict.

Conservative initial value: below it the frontier is kept for the next
turn. Tune manually after testing decision models.
"""

DECISION_GUARD_THRESHOLD = 0.8
"""Minimum ``noul`` confidence (that the message is an attack) to block it.

Conservative: only a confident verdict blocks. Tune manually.
"""


async def is_message_blocked(session_id: str, turn_number: int,
                             message: str, tools: list[str]) -> bool:
    """Ask the decision model whether the user message is an attack.

    Input guardrail, called at turn start before the LLM runs. Without the
    decision model enabled it makes no call (zero cost): the rules go in
    the router prompt instead. Otherwise the message is sent as the
    decision state with a single ``noul`` question whose instructions are
    ``prompts/seguridad.jinja`` rendered with ``decision=True`` (the same
    rules); only a confident ``yes`` blocks.
    Any failure lets the message through (fail-open). The verdict is
    persisted as a ``"decisor"`` message.

    Args:
        session_id: Session receiving the message.
        turn_number: Turn of the message.
        message: User message (with attachments, if any).
        tools: Names of the tools enabled for the router (the rules that
            apply depend on them).

    Returns:
        True when the message must be blocked. Never raises.
    """
    try:
        from backend.instances import agent

        if not agent.decision_ready:
            return False
        try:
            instructions = agent.prompt("seguridad", tools=tools, decision=True)
        except Exception as exc:
            log_error(str(exc), source="decision.py:is_message_blocked(prompt)")
            return False
        questions: dict[str, Any] = {
            "guard": {"type": "noul", "instructions": instructions}
        }
        response = await agent.decision({"user_message": message}, questions)
        data = (response or {}).get("data") or {}
        if not data.get("available"):
            return False
        answers = data.get("answers") or {}
        verdict = (answers.get("guard") or {}).get("noul")
        if not isinstance(verdict, (int, float)) or isinstance(verdict, bool):
            return False
        blocked = float(verdict) >= DECISION_GUARD_THRESHOLD
        _save_decisor_row(session_id, turn_number, None, data,
                          (response or {}).get("usage"),
                          float(verdict), blocked, question="guard")
        return blocked
    except Exception as exc:
        log_error(str(exc), source="decision.py:is_message_blocked")
        return False


async def should_close_step(session_id: str, turn_number: int,
                            final_text: str,
                            step: int | None = None) -> bool:
    """Decide whether a validated done signal deletes the step frontier.

    Without a decision model enabled/selected the LLM done signal is
    accepted (zero extra cost). Otherwise the original request, the
    unsettled rows and the proposed final answer are sent as the decision
    state with a single ``noul`` question. The verdict is persisted as a
    ``"decisor"`` message (same session, turn and step) so it stays in
    order in the table but is never sent to the LLM.

    Args:
        session_id: Session closing the step.
        turn_number: Turn closing the step.
        final_text: Final answer the agent wants to emit.
        step: Step within the turn (for the ``decisor`` row).

    Returns:
        True when the frontier may be deleted. Never raises.
    """
    try:
        from backend.instances import agent

        if agent is None or not agent.decision_enabled:
            return True
        with db_transaction() as conn:
            cur = conn.execute(
                load_query("messages/user_content_by_turn.sql"),
                (session_id, turn_number),
            )
            row = cur.fetchone()
            user_request = row["content"] if row and row["content"] else ""
        pending = [
            {
                "tool_name": item["tool_name"],
                "tool_args": item["tool_args"],
                "state": item["state"],
                "child_id": item.get("child_id"),
            }
            for item in frontier_helpers.load_open_frontier(session_id)
            if item["turn_number"] == turn_number
        ]
        state: dict[str, Any] = {
            "user_request": user_request,
            "pending": pending,
            "proposed_final": final_text,
        }
        try:
            instructions = agent.prompt("decision_close")
        except Exception as exc:
            log_error(str(exc), source="decision.py:should_close_step(prompt)")
            return True
        questions: dict[str, Any] = {
            "close": {
                "type": "noul",
                "instructions": instructions,
            }
        }
        response = await agent.decision(state, questions)
        data = (response or {}).get("data") or {}
        if not data.get("available"):
            return True
        answers = data.get("answers") or {}
        verdict = (answers.get("close") or {}).get("noul")
        if not isinstance(verdict, (int, float)) or isinstance(verdict, bool):
            return True
        closed = bool(verdict) and float(verdict) >= DECISION_CLOSE_THRESHOLD
        _save_decisor_row(session_id, turn_number, step, data,
                          (response or {}).get("usage"),
                          float(verdict), closed)
        return closed
    except Exception as exc:
        log_error(str(exc), source="decision.py:should_close_step")
        return True


async def should_keep_pending(session_id: str, new_message: str,
                              manager: Any | None = None) -> bool:
    """Decide whether the new user message continues the pending work.

    Continuity gate, called at turn start before the resume block is
    injected. Without a decision model enabled/selected the pending work
    is always kept (current behavior, zero extra cost). Otherwise the
    pending rows and the new message are sent as the decision state with
    a single ``noul`` question loaded from ``prompts/decision_continue.jinja``.

    Only a confident ``no`` discards: the verdict is the probability of
    "continues", so values below ``1 - DECISION_CLOSE_THRESHOLD`` mean a
    confident topic change. Anything else (including any failure) keeps
    the pending rows.

    Args:
        session_id: Session starting a new turn.
        new_message: New user message text.
        manager: Session manager owning the session. ``None`` means the
            global chat manager (``sessions`` / ``messages``); creator
            runs pass their ``CreatorSessionManager`` so the verdict row
            lands in ``creators`` instead of ``messages``.

    Returns:
        True when the pending frontier must be kept. Never raises.
    """
    try:
        from backend.instances import agent

        if agent is None or not agent.decision_enabled:
            return True
        pending = [
            {
                "tool_name": item["tool_name"],
                "tool_args": item["tool_args"],
                "state": item["state"],
                "child_id": item.get("child_id"),
                "turn_number": item["turn_number"],
            }
            for item in frontier_helpers.load_open_frontier(session_id)
        ]
        if not pending:
            return True
        try:
            instructions = agent.prompt("decision_continue")
        except Exception as exc:
            log_error(str(exc), source="decision.py:should_keep_pending(prompt)")
            return True
        state: dict[str, Any] = {
            "pending": pending,
            "new_request": new_message,
        }
        questions: dict[str, Any] = {
            "continue": {
                "type": "noul",
                "instructions": instructions,
            }
        }
        response = await agent.decision(state, questions)
        data = (response or {}).get("data") or {}
        if not data.get("available"):
            return True
        answers = data.get("answers") or {}
        verdict = (answers.get("continue") or {}).get("noul")
        if not isinstance(verdict, (int, float)) or isinstance(verdict, bool):
            return True
        keep = float(verdict) > (1.0 - DECISION_CLOSE_THRESHOLD)
        try:
            if manager is not None:
                turn_number = int(manager.get_last_turn_number(session_id) or 0)
            else:
                with db_transaction() as conn:
                    cur = conn.execute(
                        load_query("messages/get_max_turn_or_zero.sql"),
                        (session_id,),
                    )
                    row = cur.fetchone()
                    turn_number = int(row["max_turn"]) if row and row["max_turn"] is not None else 0
        except Exception:
            turn_number = 0
        _save_decisor_row(session_id, turn_number, None, data,
                          (response or {}).get("usage"),
                          float(verdict), keep, question="continue",
                          manager=manager)
        return keep
    except Exception as exc:
        log_error(str(exc), source="decision.py:should_keep_pending")
        return True


def _save_decisor_row(session_id: str, turn_number: int,
                      step: int | None, data: dict[str, Any],
                      usage: dict[str, Any] | None,
                      verdict: float, outcome: bool,
                      question: str = "close",
                      manager: Any | None = None) -> None:
    """Persist the decision verdict as a ``"decisor"`` message.

    Same session, turn and step as the surrounding flow, so the row stays
    in order in the table. Never raises.

    Args:
        session_id: Session identifier.
        turn_number: Current turn number.
        step: Current step within the turn.
        data: ``Agent.decision`` response data (model, provider).
        usage: Token / time report from the decision call.
        verdict: ``noul`` probability returned by the model.
        outcome: Gate result — True means closed (close gate), kept
            (continue gate) or blocked (guard gate).
        question: Question name (``"close"``, ``"continue"`` or ``"guard"``).
        manager: Session manager owning the session. ``None`` means the
            global chat manager; creator runs pass their
            ``CreatorSessionManager`` so the row lands in ``creators``.
    """
    try:
        if manager is None:
            from backend.instances import session_manager as manager

        if manager is None:
            return
        result_key = {"close": "closed", "continue": "kept", "guard": "blocked"}[question]
        manager.save_message(
            session_id=session_id,
            role="decisor",
            content=json.dumps({
                "question": question,
                "type": "noul",
                "verdict": verdict,
                "threshold": (DECISION_GUARD_THRESHOLD if question == "guard"
                              else DECISION_CLOSE_THRESHOLD),
                result_key: outcome,
            }),
            status="success",
            usage=usage if isinstance(usage, dict) else None,
            model=data.get("model"),
            provider=data.get("provider"),
            turn_number=turn_number,
            step=step,
        )
    except Exception as exc:
        log_error(str(exc), source="decision.py:_save_decisor_row")


async def verify_creator(manager: Any, creator_id: str) -> dict[str, Any]:
    """Run the on-demand verification of a creator conversation.

    Builds the same decision state the close gate uses (user request,
    open frontier rows, proposed final answer) from the ``creators``
    table and asks whether the work fulfils what the user asked. With a
    decision model enabled the shared ``decision_close`` criteria apply;
    without one an LLM with JSON output decides. The verdict is persisted
    as a ``"decisor"`` row in ``creators`` and, when it is done, the step
    frontier of the conversation is deleted.

    Args:
        manager: ``CreatorSessionManager`` owning the conversation.
        creator_id: Creator conversation id.

    Returns:
        ``{"done": bool, "reason": str}``. Never raises: on any failure
        the work is reported as not done with the failure as reason.
    """
    try:
        from backend.agent.utils.creators import get_conversation
        from backend.instances import agent

        conv = get_conversation(creator_id)
        if conv is None:
            return {"done": False, "reason": "La conversación no existe."}
        historial = conv.get("historial") or []
        if not historial:
            return {"done": False, "reason": "La conversación todavía no tiene mensajes."}
        setup = conv.get("setup") or {}
        request_lines = []
        if setup.get("name"):
            request_lines.append(f"Nombre: {setup['name']}")
        if setup.get("descripcion"):
            request_lines.append(f"Descripción: {setup['descripcion']}")
        first_user = next((m.get("content", "") for m in historial if m.get("role") == "user"), "")
        user_request = "\n".join(request_lines + [first_user]).strip()
        assistants = [m.get("content", "") for m in historial if m.get("role") == "assistant" and m.get("content")]
        result = conv.get("result") or {}
        created = str(result.get("message") or "").strip()
        final_parts = [assistants[-1]] if assistants else []
        if created:
            final_parts.append(f"Resultado registrado: {created}")
        proposed_final = "\n\n".join(final_parts)
        pending = [
            {
                "tool_name": item["tool_name"],
                "tool_args": item["tool_args"],
                "state": item["state"],
                "child_id": item.get("child_id"),
            }
            for item in frontier_helpers.load_open_frontier(creator_id)
        ]
        state: dict[str, Any] = {
            "user_request": user_request,
            "pending": pending,
            "proposed_final": proposed_final.strip(),
        }
        usage: dict[str, Any] | None = None
        model: str | None = None
        provider: str | None = None
        done = False
        reason = ""
        if agent is not None and agent.decision_enabled:
            try:
                instructions = agent.prompt("decision_close")
            except Exception as exc:
                log_error(str(exc), source="decision.py:verify_creator(prompt)")
                return {"done": False, "reason": "No se pudo cargar el prompt de verificación."}
            response = await agent.decision(state, {
                "close": {"type": "noul", "instructions": instructions},
            })
            data = (response or {}).get("data") or {}
            if not data.get("available"):
                return {"done": False, "reason": "El modelo de decisión no está disponible."}
            answers = data.get("answers") or {}
            verdict = (answers.get("close") or {}).get("noul")
            if not isinstance(verdict, (int, float)) or isinstance(verdict, bool):
                return {"done": False, "reason": "El modelo de decisión no devolvió un veredicto."}
            done = bool(verdict) and float(verdict) >= DECISION_CLOSE_THRESHOLD
            reason = ("Cumple con lo pedido." if done
                      else "Todavía no cumple con lo pedido.")
            usage = (response or {}).get("usage")
            model = data.get("model")
            provider = data.get("provider")
            _save_decisor_row(creator_id, _creator_turn(manager, creator_id), None,
                              data, usage, float(verdict), done,
                              manager=manager)
        else:
            if agent is None:
                return {"done": False, "reason": "El agente no está disponible."}
            prompt = (
                "Evaluá si el trabajo realizado cumple con lo pedido por el usuario.\n\n"
                f"Pedido del usuario:\n{user_request}\n\n"
                f"Última respuesta:\n{proposed_final.strip()}\n\n"
                f"Pendientes abiertos: {len(pending)}\n\n"
                'Respondé SOLO con un JSON: {"done": true/false, "reason": "motivo breve"}. '
                "Solo done=true si cumple de forma completa y no quedan pendientes."
            )
            response = await agent.llm_process(
                model=agent._resolved_model,
                prompt=prompt,
                response_format="json",
                reasoning=False,
            )
            if not isinstance(response, dict) or response.get("status") == "error":
                return {"done": False, "reason": "No se pudo evaluar: el modelo no está disponible."}
            data = response.get("data") or ""
            try:
                parsed = json.loads(data) if isinstance(data, str) else {}
            except (ValueError, TypeError):
                parsed = {}
            if not parsed:
                return {"done": False, "reason": "No se pudo evaluar: el modelo no devolvió un veredicto."}
            done = bool(parsed.get("done")) and not pending
            if parsed.get("done") and pending:
                reason = f"Quedan {len(pending)} pasos pendientes abiertos."
            else:
                reason = str(parsed.get("reason") or ("Cumple con lo pedido." if done else "Todavía no cumple con lo pedido."))
            usage = (response or {}).get("usage")
            _save_decisor_row(creator_id, _creator_turn(manager, creator_id), None,
                              {"model": agent._resolved_model, "provider": agent.provider},
                              usage, 1.0 if done else 0.0, done,
                              manager=manager)
        if done:
            try:
                frontier_helpers.clear_session(creator_id)
            except Exception as exc:
                log_error(str(exc), source="decision.py:verify_creator(clear)")
        return {"done": done, "reason": reason}
    except Exception as exc:
        log_error(str(exc), source="decision.py:verify_creator")
        return {"done": False, "reason": "Falló la verificación."}


def _creator_turn(manager: Any, creator_id: str) -> int:
    """Return the last turn of a creator conversation, 0 when unknown.

    Args:
        manager: ``CreatorSessionManager`` owning the conversation.
        creator_id: Creator conversation id.

    Returns:
        The last turn number. Never raises.
    """
    try:
        return int(manager.get_last_turn_number(creator_id) or 0)
    except Exception:
        return 0
