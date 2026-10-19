"""Registry of the runs of the creators (agent, skill, tool and workflow).

Every request to a creator endpoint is one run and is stored in
``creator_runs``: what the creator did (asked a question, created, iterated or
found the item already existing), the item it produced, the result, the model
and the tokens and cost of the LLM calls it made.

The creator streams are wrapped with :func:`track_creator_run`. While a run is
active its id travels in a ``ContextVar``, so ``record_creator_call`` can add
the usage of every call to the run without the creators knowing about it.
``creator_calls`` keeps the detail of each call and ``spend`` is not touched.

Every function manages its own connection, never raises and logs failures:
tracking must never break a creator. All timestamps are local time.
"""

from __future__ import annotations

import contextvars
import json
import time
from datetime import datetime
from typing import Any, AsyncIterator

from backend.agent.utils.db import db_transaction, get_connection
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.queries import load_query

_DESCRIPTION_LIMIT = 500
"""Characters of the user's request stored with the run."""

_current_run: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "creator_run_id", default=None
)


def current_run_id() -> int | None:
    """Return the id of the creator run active in this context, if any."""
    return _current_run.get()


def start_run(
    kind: str,
    description: str,
    provider: str | None,
    model: str | None,
) -> int | None:
    """Open a run.

    Args:
        kind: ``agent``, ``skill``, ``tool`` or ``workflow``.
        description: The user's request (cut to a bounded length).
        provider: Provider the run uses.
        model: Model the run uses.

    Returns:
        The run id, or ``None`` when it could not be stored.
    """
    try:
        with db_transaction() as conn:
            cur = conn.execute(
                load_query("creators/insert_run.sql"),
                (
                    kind,
                    (description or "")[:_DESCRIPTION_LIMIT],
                    provider,
                    model,
                    datetime.now().isoformat(),
                ),
            )
            return cur.lastrowid
    except Exception as exc:
        log_error(str(exc), source="creator_runs.py:start_run")
        return None


def add_usage(
    run_id: int,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    cost_input: float,
    cost_output: float,
    cost_total: float,
) -> None:
    """Add the usage of one LLM call to its run."""
    try:
        with db_transaction() as conn:
            conn.execute(
                load_query("creators/add_usage.sql"),
                (
                    prompt_tokens, completion_tokens, total_tokens,
                    cost_input, cost_output, cost_total, run_id,
                ),
            )
    except Exception as exc:
        log_error(str(exc), source="creator_runs.py:add_usage")


def finish_run(
    run_id: int,
    action: str | None,
    item_name: str | None,
    status: str,
    duration: float,
) -> None:
    """Close a run with what it did and how it ended."""
    try:
        with db_transaction() as conn:
            conn.execute(
                load_query("creators/finish_run.sql"),
                (action, item_name, status, round(duration, 2), datetime.now().isoformat(), run_id),
            )
    except Exception as exc:
        log_error(str(exc), source="creator_runs.py:finish_run")


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent runs, newest first."""
    try:
        with get_connection() as conn:
            rows = conn.execute(load_query("creators/list_runs.sql"), (int(limit),)).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        log_error(str(exc), source="creator_runs.py:list_runs")
        return []


class _Outcome:
    """What a creator stream did, read from the SSE events it emits."""

    def __init__(self, kind: str, requested_name: str | None, iterate: bool) -> None:
        self.kind = kind
        self.action: str | None = "iterate" if iterate else None
        self.item_name = requested_name
        self.status = "success"
        self.saw_result = False

    def observe(self, event: dict[str, Any]) -> None:
        """Update the outcome with one event of the stream."""
        kind = event.get("type")
        content = event.get("content")
        if kind == "error":
            self.status = "error"
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
        elif kind in (f"{self.kind}_result_final", f"{self.kind}_result") and isinstance(content, dict):
            self.saw_result = True
            data = content.get("data") or {}
            name = data.get(self.kind)
            if name:
                self.item_name = str(name)
            if content.get("status") != "success":
                self.status = "error"
            elif self.action is None:
                self.action = "exists" if data.get("exist") == "Sí" else "create"

    def final_action(self) -> str | None:
        """Action to store: a run that only talked with the user asked a question."""
        if self.action is None and self.status == "success" and not self.saw_result:
            return "question"
        return self.action


async def track_creator_run(
    kind: str,
    req: Any,
    stream: AsyncIterator[str],
) -> AsyncIterator[str]:
    """Record the run of a creator while forwarding its SSE stream untouched.

    Args:
        kind: ``agent``, ``skill``, ``tool`` or ``workflow``.
        req: The creator request (``descripcion``, ``name``, ``iterate``,
            ``model``, ``provider``).
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
        log_error(str(exc), source="creator_runs.py:track_creator_run(model)")
    run_id = start_run(kind, getattr(req, "descripcion", ""), provider, model)
    token = _current_run.set(run_id)
    outcome = _Outcome(kind, getattr(req, "name", None), bool(getattr(req, "iterate", False)))
    try:
        async for chunk in stream:
            if run_id is not None and isinstance(chunk, str) and chunk.startswith("data: "):
                try:
                    outcome.observe(json.loads(chunk[len("data: "):]))
                except (ValueError, TypeError):
                    pass
            yield chunk
    except BaseException:
        # The client left or the request was cancelled mid-stream.
        if outcome.status == "success" and not outcome.saw_result:
            outcome.status = "aborted"
        raise
    finally:
        try:
            _current_run.reset(token)
        except ValueError:
            pass
        if run_id is not None:
            finish_run(
                run_id,
                outcome.final_action(),
                outcome.item_name,
                outcome.status,
                time.time() - started,
            )
