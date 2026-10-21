"""Conversations of the creators (agent, skill, tool and workflow), stored in ``creators``.

Every request to a creator endpoint belongs to a conversation (``creator_id``). The
creator streams are wrapped with :func:`track_creator_run`, which forwards the SSE events
untouched while it stores what happens in ``creators`` like ``messages`` does: the user
message, the text the creator streamed, its tool calls with their results and, at the
end, how the request ended. While a request is active its conversation travels in a
``ContextVar``, so :func:`add_call` can store every LLM call (with its tokens and cost)
under it without the creators knowing about it.

The history sidebar of each creator reads :func:`list_conversations` and reopens a
conversation with :func:`get_conversation`, which rebuilds what the page showed.

Every function manages its own connection, never raises and logs failures: storing must
never break a creator. All timestamps are local time.
"""

from __future__ import annotations

import contextvars
import json
import re
import time
import uuid
from datetime import datetime
from typing import Any, AsyncIterator

from backend.agent.utils.db import db_transaction, get_connection
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.queries import load_query

KINDS = ("agent", "skill", "tool", "workflow")
"""Kinds of creator that have a conversation."""

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_current: contextvars.ContextVar[tuple[str, str] | None] = contextvars.ContextVar(
    "creator_conversation", default=None
)

_COLUMNS = (
    "creator_id", "kind", "role", "content", "reasoning", "tool_calls", "tool_results", "tool_name",
    "status", "message", "caller", "action", "item_name", "setup", "provider", "model",
    "prompt_tokens", "completion_tokens", "total_tokens", "total_time", "cost_input", "cost_output",
    "cost_total",
)


def is_valid_id(creator_id: str) -> bool:
    """Check that a conversation id is safe to store and to put in a URL.

    Args:
        creator_id: Id to check.

    Returns:
        True when it has 1 to 64 letters, digits, ``_`` or ``-``.
    """
    return isinstance(creator_id, str) and bool(_ID_RE.match(creator_id))


def current_conversation() -> tuple[str | None, str | None]:
    """Get the conversation of the request running in this context.

    Returns:
        ``(creator_id, kind)``, or ``(None, None)`` when there is none.
    """
    value = _current.get()
    return value if value else (None, None)


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
    """Store one LLM call under the conversation that made it, if any.

    Args:
        caller: Who made the call, e.g. ``creator:skill:generate``.
        provider: Provider used.
        model: Model used.
        usage: ``prompt_tokens``, ``completion_tokens``, ``total_tokens`` and ``total_time``.
        costs: ``(cost_input, cost_output, cost_total)`` in USD.
    """
    creator_id, kind = current_conversation()
    if kind is None:
        parts = str(caller).split(":")
        kind = parts[1] if len(parts) > 1 and parts[0] == "creator" and parts[1] in KINDS else "other"
    add_row(
        creator_id, kind, "call", caller=caller, provider=provider, model=model,
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
                value = _loads(row["tool_results"])
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


def _last_user_text(req: Any) -> str:
    """Get the message the user sent in a request.

    Args:
        req: The creator request.

    Returns:
        The last user message of ``mensajes``, or the description when there is none.
    """
    mensajes = getattr(req, "mensajes", None)
    if isinstance(mensajes, str):
        mensajes = _loads(mensajes, [])
    if isinstance(mensajes, list):
        for item in reversed(mensajes):
            if isinstance(item, dict) and item.get("role") == "user" and item.get("content"):
                return str(item["content"])
    return str(getattr(req, "descripcion", "") or "")


def _setup_of(req: Any) -> dict[str, Any]:
    """Describe the form of a request, without the conversation.

    Args:
        req: The creator request (a pydantic model or a namespace).

    Returns:
        The fields that rebuild the setup form of the page.
    """
    if hasattr(req, "model_dump"):
        data = req.model_dump()
    else:
        data = dict(vars(req))
    for key in ("mensajes", "creator_id"):
        data.pop(key, None)
    return data


class _Outcome:
    """What a creator stream did, read from the SSE events it emits."""

    def __init__(self, kind: str, requested_name: str | None, iterate: bool) -> None:
        """Create the outcome of a request.

        Args:
            kind: Kind of creator (agent, skill, tool or workflow).
            requested_name: Name the user asked for, when there is one.
            iterate: True when the request modifies an existing item.
        """
        self.kind = kind
        self.action: str | None = "iterate" if iterate else None
        self.item_name = requested_name
        self.status = "success"
        self.message = ""
        self.saw_result = False

    def observe(self, event: dict[str, Any]) -> None:
        """Update the outcome with one event of the stream.

        Args:
            event: Event emitted by the creator.
        """
        kind = event.get("type")
        content = event.get("content")
        if kind == "error":
            self.status = "error"
            self.message = str(content or "")
        elif kind == "aborted":
            self.status = "aborted"
        elif kind == f"{self.kind}_action" and isinstance(content, dict):
            step = content.get("action")
            if step == "creating":
                self.action = "create"
            elif step == "iterating":
                self.action = "iterate"
            elif step == "question":
                self.action = "question"
        elif (
            kind == f"{self.kind}_result_final" or (kind == f"{self.kind}_result" and "status" in (content or {}))
        ) and isinstance(content, dict):
            # The tool creator also emits ``tool_result`` for the results of its own tool
            # calls ({name, result}); the result of the creator always carries ``status``.
            self.saw_result = True
            data = content.get("data") or {}
            name = data.get(self.kind)
            if name:
                self.item_name = str(name)
            self.message = str(content.get("message") or "")
            if content.get("status") != "success":
                self.status = "error"
            elif self.action is None:
                self.action = "exists" if data.get("exist") == "Sí" else "create"

    def final_action(self) -> str | None:
        """Decide the action to store: a request that only talked with the user asked a question.

        Returns:
            The action, or ``None`` when it cannot be known.
        """
        if self.action is None and self.status == "success" and not self.saw_result:
            return "question"
        return self.action


class _Recorder:
    """Store the rows of a request while its SSE events go by."""

    def __init__(self, creator_id: str, kind: str) -> None:
        """Create the recorder.

        Args:
            creator_id: Conversation the request belongs to.
            kind: Kind of creator.
        """
        self.creator_id = creator_id
        self.kind = kind
        self.text = ""
        self.reasoning = ""
        self.pending_tool: dict[str, Any] | None = None

    def observe(self, event: dict[str, Any]) -> None:
        """Store what an event adds to the conversation.

        Args:
            event: Event emitted by the creator.
        """
        kind = event.get("type")
        content = event.get("content")
        if kind == "chunk":
            self.text += str(content or "")
        elif kind == "reasoning":
            self.reasoning += str(content or "")
        elif kind == "tool_call":
            self.flush_text()
            self._store_pending_tool()
            payload = content if isinstance(content, dict) else (_loads(content, {}) if isinstance(content, str) else {})
            args = payload.get("args", payload.get("parameters", {}))
            self.pending_tool = {"name": str(payload.get("name") or payload.get("tool") or "unknown"), "args": args}
        elif kind == "tool_result" and content:
            payload = content if isinstance(content, dict) else {"name": "unknown", "result": content}
            pending = self.pending_tool or {"name": str(payload.get("name") or "unknown"), "args": {}}
            result = payload["result"] if "result" in payload else payload
            add_row(
                self.creator_id, self.kind, "tool", tool_name=pending["name"],
                tool_calls=pending["args"], tool_results=result,
            )
            self.pending_tool = None

    def flush_text(self) -> None:
        """Store the text and reasoning streamed so far as an assistant row."""
        if self.text.strip() or self.reasoning.strip():
            add_row(
                self.creator_id, self.kind, "assistant",
                content=self.text or None, reasoning=self.reasoning.strip() or None,
            )
        self.text = ""
        self.reasoning = ""

    def _store_pending_tool(self) -> None:
        """Store a tool call that never got its result."""
        if self.pending_tool is not None:
            add_row(
                self.creator_id, self.kind, "tool", tool_name=self.pending_tool["name"],
                tool_calls=self.pending_tool["args"],
            )
            self.pending_tool = None

    def finish(self, outcome: _Outcome, duration: float, provider: str | None, model: str | None) -> None:
        """Store what is left and the row that says how the request ended.

        Args:
            outcome: What the stream did.
            duration: Seconds the request took.
            provider: Provider the request used.
            model: Model the request used.
        """
        self.flush_text()
        self._store_pending_tool()
        add_row(
            self.creator_id, self.kind, "result", status=outcome.status, message=outcome.message,
            action=outcome.final_action(), item_name=outcome.item_name, provider=provider, model=model,
            total_time=round(duration, 2),
        )


async def track_creator_run(
    kind: str,
    req: Any,
    stream: AsyncIterator[str],
) -> AsyncIterator[str]:
    """Store a creator request in its conversation while forwarding its SSE stream untouched.

    Args:
        kind: ``agent``, ``skill``, ``tool`` or ``workflow``.
        req: The creator request (``descripcion``, ``name``, ``mensajes``, ``iterate``,
            ``model``, ``provider`` and the optional ``creator_id`` of the conversation).
        stream: The SSE stream of the creator.

    Yields:
        Every event of ``stream``, unchanged.
    """
    started = time.time()
    model = provider = None
    try:
        from backend.agent.utils.create_helpers import resolve_create_model_provider

        model, provider = resolve_create_model_provider(
            getattr(req, "model", None), getattr(req, "provider", None)
        )
    except Exception as exc:
        log_error(str(exc), source="creators.py:track_creator_run(model)")
    creator_id = getattr(req, "creator_id", None)
    if not creator_id or not is_valid_id(creator_id):
        creator_id = uuid.uuid4().hex
    add_row(
        creator_id, kind, "user", content=_last_user_text(req), setup=_setup_of(req),
        provider=provider, model=model,
    )
    token = _current.set((creator_id, kind))
    outcome = _Outcome(kind, getattr(req, "name", None), bool(getattr(req, "iterate", False)))
    recorder = _Recorder(creator_id, kind)
    try:
        async for chunk in stream:
            if isinstance(chunk, str) and chunk.startswith("data: "):
                try:
                    event = json.loads(chunk[len("data: "):])
                except (ValueError, TypeError):
                    event = None
                if isinstance(event, dict):
                    outcome.observe(event)
                    recorder.observe(event)
            yield chunk
    except BaseException:
        # The client left or the request was cancelled mid-stream.
        if outcome.status == "success" and not outcome.saw_result:
            outcome.status = "aborted"
        raise
    finally:
        try:
            _current.reset(token)
        except ValueError:
            pass
        recorder.finish(outcome, time.time() - started, provider, model)
