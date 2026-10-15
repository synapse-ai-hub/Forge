"""Validated step-close decision with optional decision model.

When the agent loop emits a final answer with no tool calls (the LLM done
signal), this module decides whether the step frontier is deleted. Without
a decision model enabled the LLM signal is accepted as-is (current
behavior, zero extra cost). With the decision section enabled and a
provider + model selected, ``Agent.decision`` validates the close: only a
``done`` verdict with enough confidence deletes the frontier, anything
else (or any failure) leaves the rows behind for the next turn.

Every function manages its own failures and never raises: frontier tracking
must never break the agent loop. On any doubt the step closes (fail-open).
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


async def should_keep_pending(session_id: str, new_message: str) -> bool:
    """Decide whether the new user message continues the pending work.

    Continuity gate, called at turn start before the resume block is
    injected. Without a decision model enabled/selected the pending work
    is always kept (current behavior, zero extra cost). Otherwise the
    pending rows and the new message are sent as the decision state with
    a single ``noul`` question loaded from ``prompts/decision_continue.md``.

    Only a confident ``no`` discards: the verdict is the probability of
    "continues", so values below ``1 - DECISION_CLOSE_THRESHOLD`` mean a
    confident topic change. Anything else (including any failure) keeps
    the pending rows.

    Args:
        session_id: Session starting a new turn.
        new_message: New user message text.

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
                          float(verdict), keep, question="continue")
        return keep
    except Exception as exc:
        log_error(str(exc), source="decision.py:should_keep_pending")
        return True


def _save_decisor_row(session_id: str, turn_number: int,
                      step: int | None, data: dict[str, Any],
                      usage: dict[str, Any] | None,
                      verdict: float, outcome: bool,
                      question: str = "close") -> None:
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
        outcome: Gate result — True means closed (close gate) or kept (continue gate).
        question: Question name (``"close"`` or ``"continue"``).
    """
    try:
        from backend.instances import session_manager

        if session_manager is None:
            return
        result_key = "closed" if question == "close" else "kept"
        session_manager.save_message(
            session_id=session_id,
            role="decisor",
            content=json.dumps({
                "question": question,
                "type": "noul",
                "verdict": verdict,
                "threshold": DECISION_CLOSE_THRESHOLD,
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
