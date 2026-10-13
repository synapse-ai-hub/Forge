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


def _save_decisor_row(session_id: str, turn_number: int,
                      step: int | None, data: dict[str, Any],
                      usage: dict[str, Any] | None,
                      verdict: float, closed: bool) -> None:
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
        closed: Whether the step was closed.
    """
    try:
        from backend.instances import session_manager

        if session_manager is None:
            return
        session_manager.save_message(
            session_id=session_id,
            role="decisor",
            content=json.dumps({
                "question": "close",
                "type": "noul",
                "verdict": verdict,
                "threshold": DECISION_CLOSE_THRESHOLD,
                "closed": closed,
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
