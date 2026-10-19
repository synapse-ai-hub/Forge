"""Persistence helpers for workflows: registry, runs, node commits and usage.

Tables: ``workflows`` (name is the id), ``workflow_runs`` (one row per
execution), ``workflow_run_steps`` (one commit row per node execution) and
``workflow_usage`` (spend of the LLM calls the engine makes by itself).

Every function manages its own connection, never raises and logs failures:
persisting a run must never break its execution. All timestamps are local
time (``datetime.now()``), never UTC.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from backend.agent.utils.db import db_transaction, get_connection
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.queries import load_query

MAX_ATTEMPTS = 3
"""Total attempts of a run (the first execution counts as one)."""


def _now() -> str:
    """Return the current local time as an ISO string."""
    return datetime.now().isoformat()


def ensure_workflow(name: str) -> None:
    """Register a workflow in ``workflows`` (idempotent).

    Args:
        name: Workflow name (the id).
    """
    try:
        now = _now()
        with db_transaction() as conn:
            conn.execute(load_query("workflows/upsert_workflow.sql"), (name, now, now))
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:ensure_workflow")


def create_run(
    name: str,
    session_id: str | None,
    parent_session_id: str | None = None,
    source: str = "play",
) -> str | None:
    """Open a run in ``running`` state.

    Args:
        name: Workflow name.
        session_id: Session that holds the execution (parent of the node
            child sessions).
        parent_session_id: Session of the agent that called the workflow
            through the tool, if any.
        source: ``"play"`` (UI) or ``"tool"`` (called by an agent).

    Returns:
        The new run id, or ``None`` when it could not be stored.
    """
    ensure_workflow(name)
    run_id = uuid.uuid4().hex
    try:
        with db_transaction() as conn:
            conn.execute(
                load_query("workflows/insert_run.sql"),
                (run_id, name, session_id, parent_session_id, source, _now()),
            )
        return run_id
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:create_run")
        return None


def set_run_session(run_id: str, session_id: str) -> None:
    """Attach the execution session to a run."""
    try:
        with db_transaction() as conn:
            conn.execute(load_query("workflows/set_run_session.sql"), (session_id, run_id))
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:set_run_session")


def get_run(run_id: str) -> dict[str, Any] | None:
    """Return one run as a dict, or ``None`` when it does not exist."""
    try:
        with get_connection() as conn:
            row = conn.execute(load_query("workflows/get_run.sql"), (run_id,)).fetchone()
            return dict(row) if row else None
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:get_run")
        return None


def list_running_runs() -> list[dict[str, Any]]:
    """Return the runs still marked as ``running``."""
    try:
        with get_connection() as conn:
            rows = conn.execute(load_query("workflows/list_running.sql")).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:list_running_runs")
        return []


def list_last_runs() -> dict[str, dict[str, Any]]:
    """Return the latest run of every workflow, keyed by workflow name."""
    try:
        with get_connection() as conn:
            rows = conn.execute(load_query("workflows/list_last_runs.sql")).fetchall()
            return {r["workflow_name"]: dict(r) for r in rows}
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:list_last_runs")
        return {}


def list_runs(name: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent runs, newest first.

    Args:
        name: Restrict to one workflow, or ``None`` for all.
        limit: Maximum number of runs.
    """
    try:
        with get_connection() as conn:
            rows = conn.execute(
                load_query("workflows/list_runs.sql"), (name, name, int(limit))
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:list_runs")
        return []


def set_run_attempt(run_id: str, attempt: int) -> None:
    """Start another attempt of a run (it goes back to ``running``)."""
    try:
        with db_transaction() as conn:
            conn.execute(load_query("workflows/set_run_attempt.sql"), (attempt, run_id))
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:set_run_attempt")


def finish_run(
    run_id: str,
    status: str,
    result: str | None = None,
    error_text: str | None = None,
) -> None:
    """Close a run.

    Args:
        run_id: Run identifier.
        status: ``success``, ``error`` or ``cancelled``.
        result: Final answer of the run.
        error_text: Plain-language explanation when the run failed.
    """
    try:
        with db_transaction() as conn:
            conn.execute(
                load_query("workflows/finish_run.sql"),
                (status, _now(), result, error_text, run_id),
            )
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:finish_run")


def open_step(
    run_id: str,
    attempt: int,
    step: int,
    substep: int,
    node_id: str,
    node_type: str,
    args: dict[str, Any] | None = None,
) -> int | None:
    """Record a dispatched node as an open commit row.

    Returns:
        The commit row id, or ``None`` when it could not be stored.
    """
    try:
        now = _now()
        with db_transaction() as conn:
            cur = conn.execute(
                load_query("workflows/insert_step.sql"),
                (
                    run_id, attempt, step, substep, node_id, node_type,
                    json.dumps(args or {}, ensure_ascii=False), now, now,
                ),
            )
            return cur.lastrowid
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:open_step")
        return None


def commit_step(row_id: int | None, result: str, child_session_id: str | None = None) -> None:
    """Commit the complete result of a node (row goes to ``done``)."""
    if row_id is None:
        return
    try:
        with db_transaction() as conn:
            conn.execute(
                load_query("workflows/mark_step_done.sql"),
                (result, child_session_id, _now(), row_id),
            )
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:commit_step")


def fail_step(row_id: int | None, error: str, child_session_id: str | None = None) -> None:
    """Mark a node as failed with its technical error."""
    if row_id is None:
        return
    try:
        with db_transaction() as conn:
            conn.execute(
                load_query("workflows/mark_step_failed.sql"),
                (error, child_session_id, _now(), row_id),
            )
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:fail_step")


def fail_open_steps(run_id: str, reason: str) -> None:
    """Mark the nodes left in flight by a cut as failed."""
    try:
        with db_transaction() as conn:
            conn.execute(
                load_query("workflows/fail_open_steps.sql"), (reason, _now(), run_id)
            )
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:fail_open_steps")


def load_done_steps(run_id: str) -> list[dict[str, Any]]:
    """Return the committed nodes of a run, in execution order."""
    try:
        with get_connection() as conn:
            rows = conn.execute(load_query("workflows/list_done_steps.sql"), (run_id,)).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:load_done_steps")
        return []


def invalidate_steps_after(run_id: str, step: int) -> None:
    """Mark as stale the committed nodes after ``step`` (they will be re-run)."""
    try:
        with db_transaction() as conn:
            conn.execute(
                load_query("workflows/stale_steps_after.sql"), (_now(), run_id, step)
            )
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:invalidate_steps_after")


def list_steps(run_id: str) -> list[dict[str, Any]]:
    """Return every node execution of a run, in order."""
    try:
        with get_connection() as conn:
            rows = conn.execute(load_query("workflows/list_steps.sql"), (run_id,)).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:list_steps")
        return []


def record_usage(
    workflow_name: str,
    run_id: str,
    purpose: str,
    provider: str | None,
    model: str | None,
    usage: dict[str, Any] | None,
) -> bool:
    """Record the spend of an LLM call made by the workflow engine.

    ``spend`` is not touched here: ``llm_process`` already contemplates it.

    Args:
        workflow_name: Workflow that made the call.
        run_id: Run that made the call.
        purpose: ``"judge"`` or ``"explain"``.
        provider: Provider used.
        model: Model used.
        usage: Usage report (``prompt_tokens``, ``completion_tokens``,
            ``total_tokens``, ``total_time``).

    Returns:
        ``True`` when the row was stored.
    """
    try:
        from backend.agent.utils.spend_handler import calculate_cost

        usage = usage or {}
        provider_value = (provider or "unknown").strip()
        model_value = (model or "unknown").strip()
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or 0) or (prompt_tokens + completion_tokens)
        cost_input, cost_output, cost_total = calculate_cost(
            provider_value, model_value, prompt_tokens, completion_tokens
        )
        with db_transaction() as conn:
            conn.execute(
                load_query("workflows/insert_usage.sql"),
                (
                    workflow_name, run_id, purpose, provider_value, model_value,
                    prompt_tokens, completion_tokens, total_tokens,
                    usage.get("total_time"), cost_input, cost_output, cost_total, _now(),
                ),
            )
        return True
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:record_usage")
        return False


def delete_workflow(name: str) -> bool:
    """Remove a workflow from the registry with its runs, commits, spend and notifications.

    The sessions created by its runs stay in the history.

    Args:
        name: Workflow name (the id).

    Returns:
        ``True`` when everything was removed.
    """
    try:
        with db_transaction() as conn:
            conn.execute(load_query("notifications/delete_by_workflow.sql"), (name,))
            conn.execute(load_query("workflows/delete_usage.sql"), (name,))
            conn.execute(load_query("workflows/delete_steps.sql"), (name,))
            conn.execute(load_query("workflows/delete_runs.sql"), (name,))
            conn.execute(load_query("workflows/delete_workflow.sql"), (name,))
        return True
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:delete_workflow")
        return False
