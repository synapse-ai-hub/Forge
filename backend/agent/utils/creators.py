"""Conversations of the creators (agent, skill, tool and workflow), stored in ``creators``.

Every turn of a creator endpoint runs on the agent loop with a
``CreatorSessionManager``: user, assistant and tool rows persist in
``creators`` grouped by ``creator_id``, exactly like ``messages`` does for
the chat. The history sidebar of each creator reads
:func:`list_conversations` and reopens a conversation with
:func:`get_conversation`, which rebuilds what the page showed.

Every function manages its own connection, never raises and logs failures:
storing must never break a creator. All timestamps are local time.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from backend.agent.utils.db import db_transaction, get_connection
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.queries import load_query

KINDS = ("agent", "skill", "tool", "workflow")
"""Kinds of creator that have a conversation."""

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_COLUMNS = (
    "creator_id", "kind", "role", "content", "reasoning", "tool_calls", "tool_results", "tool_name",
    "status", "message", "caller", "action", "item_name", "setup", "provider", "model",
    "prompt_tokens", "completion_tokens", "total_tokens", "total_time", "time_to_first_token",
    "cost_input", "cost_output", "cost_total", "turn_number", "step", "substep", "tool_call_id",
)


def is_valid_id(creator_id: str) -> bool:
    """Check that a conversation id is safe to store and to put in a URL.

    Args:
        creator_id: Id to check.

    Returns:
        True when it has 1 to 64 letters, digits, ``_`` or ``-``.
    """
    return isinstance(creator_id, str) and bool(_ID_RE.match(creator_id))


def add_row(creator_id: str | None, kind: str, role: str, **fields: Any) -> int | None:
    """Store one row of a conversation or one LLM call.

    Args:
        creator_id: Conversation the row belongs to, or None for calls outside one.
        kind: ``agent``, ``skill``, ``tool``, ``workflow`` or ``other``.
        role: ``user``, ``assistant``, ``tool``, ``result`` or ``call``.
        **fields: Other columns of ``creators`` (``content``, ``tool_name``, ``status``, ...).
            Values of ``tool_calls``, ``tool_results`` and ``setup`` may be dicts or lists:
            they are stored as JSON.

    Returns:
        The row id, or None when it could not be stored.
    """
    try:
        values = {"creator_id": creator_id, "kind": kind, "role": role, **fields}
        for key in ("tool_calls", "tool_results", "setup"):
            if key in values and values[key] is not None and not isinstance(values[key], str):
                values[key] = json.dumps(values[key], ensure_ascii=False, default=str)
        params = [values.get(column) for column in _COLUMNS]
        params.append(datetime.now().isoformat())
        with db_transaction() as conn:
            cur = conn.execute(load_query("creators/insert_row.sql"), params)
            return cur.lastrowid
    except Exception as exc:
        log_error(str(exc), source="creators.py:add_row")
        return None


def add_call(
    caller: str,
    provider: str,
    model: str,
    usage: dict[str, Any],
    costs: tuple[float, float, float],
) -> None:
    """Store one LLM call, deriving its kind from the caller.

    Args:
        caller: Who made the call, e.g. ``creator:skill:generate``.
        provider: Provider used.
        model: Model used.
        usage: ``prompt_tokens``, ``completion_tokens``, ``total_tokens`` and ``total_time``.
        costs: ``(cost_input, cost_output, cost_total)`` in USD.
    """
    parts = str(caller).split(":")
    kind = parts[1] if len(parts) > 1 and parts[0] == "creator" and parts[1] in KINDS else "other"
    add_row(
        None, kind, "call", caller=caller, provider=provider, model=model,
        prompt_tokens=usage.get("prompt_tokens", 0), completion_tokens=usage.get("completion_tokens", 0),
        total_tokens=usage.get("total_tokens", 0), total_time=usage.get("total_time"),
        cost_input=costs[0], cost_output=costs[1], cost_total=costs[2],
    )


def list_conversations(kind: str, limit: int = 50) -> list[dict[str, Any]]:
    """List the conversations of one kind of creator, most recent first.

    Args:
        kind: ``agent``, ``skill``, ``tool`` or ``workflow``.
        limit: Maximum number of conversations.

    Returns:
        One dict per conversation: ``creator_id``, ``kind``, ``created_at``, ``updated_at``,
        ``first_message``, ``item_name`` and ``status``.
    """
    try:
        with get_connection() as conn:
            rows = conn.execute(load_query("creators/list_conversations.sql"), (kind, int(limit))).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        log_error(str(exc), source="creators.py:list_conversations")
        return []


def delete_conversation(creator_id: str) -> bool:
    """Delete a conversation with its LLM calls.

    Args:
        creator_id: Conversation id.

    Returns:
        True when something was deleted.
    """
    try:
        with db_transaction() as conn:
            cur = conn.execute(load_query("creators/delete_conversation.sql"), (creator_id,))
            return (cur.rowcount or 0) > 0
    except Exception as exc:
        log_error(str(exc), source="creators.py:delete_conversation")
        return False


def _loads(value: Any, default: Any = None) -> Any:
    """Parse a JSON text column.

    Args:
        value: The stored text, or None.
        default: Value to return when it cannot be parsed.

    Returns:
        The parsed value, or ``default``.
    """
    if not value:
        return default
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def get_conversation(creator_id: str) -> dict[str, Any] | None:
    """Rebuild a conversation the way the creator page showed it.

    Args:
        creator_id: Conversation id.

    Returns:
        ``None`` when it does not exist. Otherwise a dict with ``creator_id``, ``kind``,
        ``setup`` (the form of the first request), ``messages`` (user and assistant messages
        with their blocks, tool calls and tool results), ``historial`` (the
        ``[{role, content}]`` the creator receives as ``mensajes``) and ``result`` (how the
        last request ended, or None).
    """
    try:
        with get_connection() as conn:
            rows = [dict(r) for r in conn.execute(load_query("creators/get_conversation.sql"), (creator_id,))]
    except Exception as exc:
        log_error(str(exc), source="creators.py:get_conversation")
        return None
    if not rows:
        return None

    setup: dict[str, Any] = {}
    messages: list[dict[str, Any]] = []
    historial: list[dict[str, str]] = []
    result: dict[str, Any] | None = None
    current: dict[str, Any] | None = None

    # The chat loop persists assistant rows with the full ``tool_calls`` list
    # (``[{id, name, args}]``) and tool rows with only ``tool_call_id`` +
    # ``content``. Index the args by call id so reopened conversations show
    # the arguments each tool ran with.
    args_by_call_id: dict[str, Any] = {}
    for row in rows:
        if row["role"] == "assistant" and row.get("tool_calls"):
            calls = _loads(row["tool_calls"], [])
            if isinstance(calls, list):
                for tc in calls:
                    if isinstance(tc, dict) and tc.get("id"):
                        args_by_call_id[str(tc["id"])] = tc.get("args", {})

    def close_assistant() -> None:
        """Add the text of the assistant message in progress to the history."""
        nonlocal current
        if current is not None and current["content"].strip():
            historial.append({"role": "assistant", "content": current["content"]})
        current = None

    for row in rows:
        role = row["role"]
        if role == "user":
            close_assistant()
            if not setup:
                setup = _loads(row["setup"], {})
            messages.append({"type": "user", "content": row["content"] or ""})
            historial.append({"role": "user", "content": row["content"] or ""})
        elif role in ("assistant", "tool"):
            if current is None:
                current = {"type": "assistant", "content": "", "blocks": [], "toolCalls": [], "toolResults": []}
                messages.append(current)
            if role == "assistant":
                if row["reasoning"]:
                    current["blocks"].append({"type": "reasoning", "content": row["reasoning"]})
                if row["content"]:
                    current["blocks"].append({"type": "text", "content": row["content"]})
                    current["content"] += row["content"]
            else:
                args = _loads(row["tool_calls"], {})
                if not args and row.get("tool_call_id"):
                    args = args_by_call_id.get(str(row["tool_call_id"]), {})
                value = _loads(row["tool_results"])
                if value is None:
                    value = row["content"]
                current["blocks"].append({"type": "tool", "name": row["tool_name"], "args": args, "result": value})
                current["toolCalls"].append({"tool": row["tool_name"], "parameters": args})
                current["toolResults"].append({"tool": row["tool_name"], "result": value})
        elif role == "result":
            close_assistant()
            result = {
                "status": row["status"], "message": row["message"] or "",
                "action": row["action"], "item_name": row["item_name"],
            }
    close_assistant()
    return {
        "creator_id": creator_id, "kind": rows[0]["kind"], "setup": setup,
        "messages": messages, "historial": historial, "result": result,
    }
