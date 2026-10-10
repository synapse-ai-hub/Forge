"""Step frontier tracking for cut-flow resume.

Every dispatched tool call is recorded as an ``open`` row in the
``step_frontier`` table and flipped to ``done`` when its result commits.
Rows are only deleted when the step closes with a validated done signal, so
a cut flow leaves them behind for the next turn to resume from.

All functions manage their own connection, never raise, and log failures
instead: frontier tracking must never break the agent loop.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable

from backend.agent.utils.db import db_transaction
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.queries import load_query


def _now() -> str:
    """Return the current local time in the format used by ``created_at``."""
    return datetime.now().isoformat()


def record_block_dispatch(
    session_id: str,
    turn_number: int,
    step: int,
    calls: Iterable[tuple[int, str, dict[str, Any] | None]],
) -> None:
    """Record every call of a dispatched block as an open frontier row.

    Args:
        session_id: Session owning the block.
        turn_number: Turn owning the block.
        step: Step owning the block.
        calls: Iterable of ``(substep, tool_name, args)`` tuples, where
            substep is the call index inside the block. Args are stored
            complete, never truncated.
    """
    try:
        rows = [
            (
                session_id,
                turn_number,
                step,
                substep,
                tool_name,
                json.dumps(args or {}, ensure_ascii=False),
                None,
                _now(),
                _now(),
            )
            for substep, tool_name, args in calls
        ]
        if not rows:
            return
        sql = load_query("step_frontier/insert_open.sql")
        with db_transaction() as conn:
            conn.executemany(sql, rows)
    except Exception as exc:
        log_error(str(exc), source="frontier_helpers.py:record_block_dispatch")


def mark_call_done(
    session_id: str, turn_number: int, step: int, substep: int
) -> None:
    """Flip one frontier row to done once its result commits.

    Args:
        session_id: Session owning the row.
        turn_number: Turn owning the row.
        step: Step owning the row.
        substep: Call index inside the block.
    """
    try:
        with db_transaction() as conn:
            conn.execute(
                load_query("step_frontier/mark_done.sql"),
                (_now(), session_id, turn_number, step, substep),
            )
    except Exception as exc:
        log_error(str(exc), source="frontier_helpers.py:mark_call_done")


def clear_turn(session_id: str, turn_number: int) -> None:
    """Delete the whole frontier of a turn on validated step close.

    Args:
        session_id: Session owning the rows.
        turn_number: Turn owning the rows.
    """
    try:
        with db_transaction() as conn:
            conn.execute(
                load_query("step_frontier/delete_turn.sql"),
                (session_id, turn_number),
            )
    except Exception as exc:
        log_error(str(exc), source="frontier_helpers.py:clear_turn")
