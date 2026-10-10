"""Validated step-close decision with optional JEV.

When the agent loop emits a final answer with no tool calls (the LLM done
signal), this module decides whether the step frontier is deleted. Without
JEV configured the LLM signal is accepted as-is (current behavior, zero
extra cost). With ``JEV_API_KEY`` and ``JEV_ENDPOINT`` set, a small external
judge validates the close: only a ``done`` verdict deletes the frontier,
anything else (or any failure) leaves the rows behind for the next turn.

Expected JEV contract (POST JSON, Bearer auth)::

    request:  {"user_request": str, "pending": [...], "proposed_final": str}
    response: {"done": true | false}

Every function manages its own failures and never raises: frontier tracking
must never break the agent loop. On any doubt the step closes (fail-open).
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from backend.agent.utils import frontier_helpers
from backend.agent.utils.db import db_transaction
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.queries import load_query


def jev_configured() -> bool:
    """Return True only when a JEV key and endpoint are both set."""
    try:
        return bool(os.getenv("JEV_API_KEY", "").strip()) and bool(
            os.getenv("JEV_ENDPOINT", "").strip()
        )
    except Exception as exc:
        log_error(str(exc), source="decision.py:jev_configured")
        return False


def parse_jev_verdict(payload: Any) -> bool | None:
    """Parse a JEV response payload into a done verdict.

    Args:
        payload: Decoded JSON body from the JEV endpoint.

    Returns:
        True/False for a ``{"done": bool}`` verdict, None when the
        payload does not carry one.
    """
    try:
        if isinstance(payload, dict):
            verdict = payload.get("done")
            if isinstance(verdict, bool):
                return verdict
        return None
    except Exception as exc:
        log_error(str(exc), source="decision.py:parse_jev_verdict")
        return None


def validate_with_jev(
    user_request: str, pending: list[dict[str, Any]], proposed_final: str
) -> bool | None:
    """Ask the configured JEV endpoint whether the step may close.

    Args:
        user_request: Original user message of the closing turn.
        pending: Unsettled frontier rows (facts only, complete).
        proposed_final: The final answer the agent wants to emit.

    Returns:
        True/False verdict, or None when JEV is not configured or any
        failure happens (fail-open: the caller accepts the LLM signal).
    """
    try:
        if not jev_configured():
            return None
        body = json.dumps(
            {
                "user_request": user_request,
                "pending": pending,
                "proposed_final": proposed_final,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            os.getenv("JEV_ENDPOINT", "").strip(),
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.getenv('JEV_API_KEY', '').strip()}",
            },
            method="POST",
        )
        timeout = float(os.getenv("JEV_TIMEOUT", "10") or 10)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return parse_jev_verdict(payload)
    except Exception as exc:
        log_error(str(exc), source="decision.py:validate_with_jev")
        return None


def should_close_step(session_id: str, turn_number: int, final_text: str) -> bool:
    """Decide whether a validated done signal deletes the step frontier.

    Without JEV the LLM done signal is accepted (zero extra cost). With
    JEV configured the judge validates the close against the original
    request, the unsettled rows and the proposed final answer.

    Args:
        session_id: Session closing the step.
        turn_number: Turn closing the step.
        final_text: Final answer the agent wants to emit.

    Returns:
        True when the frontier may be deleted. Never raises.
    """
    try:
        if not jev_configured():
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
        verdict = validate_with_jev(user_request, pending, final_text)
        return True if verdict is None else verdict
    except Exception as exc:
        log_error(str(exc), source="decision.py:should_close_step")
        return True
