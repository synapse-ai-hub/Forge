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
import re
from datetime import datetime, timedelta
from typing import Any, Iterable

from backend.agent.utils.db import db_transaction
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.queries import load_query

_TASK_ID_RE = re.compile(r'<task\s+id="([^"]+)"')


def _now() -> str:
    """Return the current local time in the format used by ``created_at``."""
    return datetime.now().isoformat()


def record_block_dispatch(
    session_id: str,
    turn_number: int,
    step: int,
    calls: Iterable[tuple[int, str, str, dict[str, Any] | None]],
) -> None:
    """Record every call of a dispatched block as an open frontier row.

    Args:
        session_id: Session owning the block.
        turn_number: Turn owning the block.
        step: Step owning the block.
        calls: Iterable of ``(substep, tool_call_id, tool_name, args)``
            tuples, where substep is the call index inside the block.
            Args are stored complete, never truncated.
    """
    try:
        rows = [
            (
                session_id,
                turn_number,
                step,
                substep,
                tool_call_id or None,
                tool_name,
                json.dumps(args or {}, ensure_ascii=False),
                None,
                _now(),
                _now(),
            )
            for substep, tool_call_id, tool_name, args in calls
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


def set_task_child(
    session_id: str,
    turn_number: int,
    step: int,
    substep: int,
    child_id: str,
) -> None:
    """Attach the child session id to a task frontier row once known.

    The child session only exists after the task call runs, so the row is
    recorded with ``child_id`` NULL at dispatch and updated here on commit.

    Args:
        session_id: Session owning the row.
        turn_number: Turn owning the row.
        step: Step owning the row.
        substep: Call index inside the block.
        child_id: Child session id created by the task call.
    """
    try:
        with db_transaction() as conn:
            conn.execute(
                load_query("step_frontier/set_child.sql"),
                (child_id, _now(), session_id, turn_number, step, substep),
            )
    except Exception as exc:
        log_error(str(exc), source="frontier_helpers.py:set_task_child")


def extract_task_child_id(result_data: Any) -> str | None:
    """Extract the child session id from a task tool result.

    The task tool wraps its answer as ``<task id="...">`` XML in the
    result payload, so the parent can see the child id without any
    change to the task tool itself.

    Args:
        result_data: Tool result (contract dict or raw string).

    Returns:
        The child session id, or None when absent.
    """
    try:
        if isinstance(result_data, dict):
            text = result_data.get("data", "")
        else:
            text = result_data
        if not isinstance(text, str):
            return None
        match = _TASK_ID_RE.search(text)
        return match.group(1) if match else None
    except Exception as exc:
        log_error(str(exc), source="frontier_helpers.py:extract_task_child_id")
        return None


def load_open_frontier(session_id: str) -> list[dict[str, Any]]:
    """Load every unsettled frontier row of a session, in execution order.

    Args:
        session_id: Session owning the rows.

    Returns:
        List of row dicts (empty when nothing is pending). Never raises.
    """
    try:
        with db_transaction() as conn:
            cur = conn.execute(
                load_query("step_frontier/list_open_session.sql"), (session_id,)
            )
            return [dict(row) for row in cur.fetchall()]
    except Exception as exc:
        log_error(str(exc), source="frontier_helpers.py:load_open_frontier")
        return []


def _user_text(session_id: str, turn_number: int) -> str:
    """Return the user message content of a turn (empty string if none)."""
    try:
        with db_transaction() as conn:
            cur = conn.execute(
                load_query("messages/user_content_by_turn.sql"),
                (session_id, turn_number),
            )
            row = cur.fetchone()
            return row["content"] if row and row["content"] else ""
    except Exception as exc:
        log_error(str(exc), source="frontier_helpers.py:_user_text")
        return ""


def _tool_result_text(row: dict[str, Any]) -> str:
    """Return the last recorded tool result for a frontier row.

    Matches by exact ``tool_call_id`` first, falling back to
    ``(turn, step, tool_name)`` when the id is NULL (Google wire format).

    Args:
        row: Frontier row dict.

    Returns:
        The recorded result content, or "" when none exists.
    """
    try:
        with db_transaction() as conn:
            if row.get("tool_call_id"):
                cur = conn.execute(
                    load_query("messages/get_tool_result.sql"),
                    (row["session_id"], row["tool_call_id"]),
                )
            else:
                cur = conn.execute(
                    load_query("messages/get_tool_result_by_name.sql"),
                    (
                        row["session_id"],
                        row["turn_number"],
                        row["step"],
                        row["tool_name"],
                    ),
                )
            found = cur.fetchone()
            if found and found["content"]:
                return found["content"]
            return ""
    except Exception as exc:
        log_error(str(exc), source="frontier_helpers.py:_tool_result_text")
        return ""


def build_resume_message(session_id: str) -> str | None:
    """Build the ephemeral resume block for unsettled frontier rows.

    Facts only, nothing truncated: the original user request of each
    pending turn plus every pending task with its state, full args and
    last recorded result. Returns None when nothing is pending.

    Args:
        session_id: Session starting a new turn.

    Returns:
        The resume block text, or None. Never raises.
    """
    try:
        rows = load_open_frontier(session_id)
        if not rows:
            return None
        turns: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            turns.setdefault(row["turn_number"], []).append(row)
        parts: list[str] = []
        for turn in sorted(turns):
            lines = [f"Pedido del usuario en ese turno: {_user_text(session_id, turn)}"]
            for position, row in enumerate(turns[turn], start=1):
                result = _tool_result_text(row)
                detail = f"Último resultado registrado: {result}" if result else "Sin resultado registrado."
                child = row.get("child_id")
                if row["tool_name"] == "task":
                    lines.append(
                        f"{position}. task({row['tool_args']}) — "
                        f"sub-sesión: {child or 'no creada'}. {detail}"
                    )
                else:
                    suffix = f" sub-sesión: {child}." if child else ""
                    lines.append(
                        f"{position}. {row['tool_name']}({row['tool_args']}) — "
                        f"despachado, resultado no confirmado.{suffix} {detail}"
                    )
            parts.append(
                "[TRABAJO SIN CERRAR — turno "
                + str(turn)
                + ", paso "
                + str(turns[turn][0]["step"])
                + "]\n"
                + "\n".join(lines)
            )
        parts.append(
            "Continuá desde este estado: no repitas lo ya hecho, "
            "verificá antes de reejecutar."
        )
        return "\n\n".join(parts)
    except Exception as exc:
        log_error(str(exc), source="frontier_helpers.py:build_resume_message")
        return None


def collect_garbage(ttl_hours: float = 24.0) -> int:
    """Delete confirmed frontier rows older than the TTL.

    Only ``done`` rows are collected (a validated close deletes the whole
    turn, so survivors are crash leftovers). ``open`` rows are never
    collected: they are unsettled work a future turn must resume, no
    matter their age.

    Args:
        ttl_hours: Age in hours after which a done row is garbage.

    Returns:
        Number of deleted rows. Never raises.
    """
    try:
        cutoff = (datetime.now() - timedelta(hours=ttl_hours)).isoformat()
        with db_transaction() as conn:
            cur = conn.execute(
                load_query("step_frontier/delete_done_older_than.sql"), (cutoff,)
            )
            deleted = cur.rowcount or 0
            return deleted if deleted > 0 else 0
    except Exception as exc:
        log_error(str(exc), source="frontier_helpers.py:collect_garbage")
        return 0


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
