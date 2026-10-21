"""Persistence helpers for workflows: registry, runs and node commits.

Tables: ``workflows`` (name is the id), ``workflow_runs`` (laid out like
``messages``: the row of the run plus one row per node execution and per LLM
call of the engine, each with its step, substep, status, result and spend) and
``workflow_run_steps`` (the node commits a failed or cut run resumes from;
they are deleted when the run ends well).

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
    """Return the current local time.

    Returns:
        The time in ISO format.
    """
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
    """Attach the execution session to a run.

    Args:
        run_id: Run identifier.
        session_id: Session that holds the execution.
    """
    try:
        with db_transaction() as conn:
            conn.execute(load_query("workflows/set_run_session.sql"), (session_id, run_id))
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:set_run_session")


def get_run(run_id: str) -> dict[str, Any] | None:
    """Fetch one run.

    Args:
        run_id: Run identifier.

    Returns:
        The run as a dict, or ``None`` when it does not exist.
    """
    try:
        with get_connection() as conn:
            row = conn.execute(load_query("workflows/get_run.sql"), (run_id,)).fetchone()
            return dict(row) if row else None
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:get_run")
        return None


def list_running_runs() -> list[dict[str, Any]]:
    """List the runs still marked as ``running``.

    Returns:
        One dict per run.
    """
    try:
        with get_connection() as conn:
            rows = conn.execute(load_query("workflows/list_running.sql")).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:list_running_runs")
        return []


def list_last_runs() -> dict[str, dict[str, Any]]:
    """List the latest run of every workflow.

    Returns:
        Workflow name → its most recent run.
    """
    try:
        with get_connection() as conn:
            rows = conn.execute(load_query("workflows/list_last_runs.sql")).fetchall()
            return {r["workflow_name"]: dict(r) for r in rows}
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:list_last_runs")
        return {}


def list_runs(name: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """List the most recent runs, newest first.

    Args:
        name: Restrict to one workflow, or ``None`` for all.
        limit: Maximum number of runs.

    Returns:
        One dict per run.
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
    """Start another attempt of a run (it goes back to ``running``).

    Args:
        run_id: Run identifier.
        attempt: Attempt number (1..3).
    """
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

    Args:
        run_id: Run identifier.
        attempt: Attempt that dispatches the node.
        step: Step of the workflow.
        substep: Position of the node inside its step.
        node_id: Node id in the YAML.
        node_type: ``agent``, ``tool``, ``rag`` or ``run``.
        args: Arguments of the node.

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
    """Commit the complete result of a node (the row goes to ``done``).

    Args:
        row_id: Commit row id (``None`` is ignored).
        result: Complete output of the node.
        child_session_id: Session of the sub-agent, in agent nodes.
    """
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
    """Mark a node as failed with its technical error.

    Args:
        row_id: Commit row id (``None`` is ignored).
        error: Failure message.
        child_session_id: Session of the sub-agent, in agent nodes.
    """
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
    """Mark the nodes left in flight by a cut as failed.

    Args:
        run_id: Run identifier.
        reason: Failure message to store.
    """
    try:
        with db_transaction() as conn:
            conn.execute(
                load_query("workflows/fail_open_steps.sql"), (reason, _now(), run_id)
            )
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:fail_open_steps")


def load_done_steps(run_id: str) -> list[dict[str, Any]]:
    """List the committed nodes of a run.

    Args:
        run_id: Run identifier.

    Returns:
        One dict per committed node, in execution order.
    """
    try:
        with get_connection() as conn:
            rows = conn.execute(load_query("workflows/list_done_steps.sql"), (run_id,)).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:load_done_steps")
        return []


def invalidate_steps_after(run_id: str, step: int) -> None:
    """Mark as stale the committed nodes after a step (they will be run again).

    Args:
        run_id: Run identifier.
        step: Last step that stays valid.
    """
    try:
        with db_transaction() as conn:
            conn.execute(
                load_query("workflows/stale_steps_after.sql"), (_now(), run_id, step)
            )
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:invalidate_steps_after")


def list_steps(run_id: str) -> list[dict[str, Any]]:
    """List every node execution of a run.

    Args:
        run_id: Run identifier.

    Returns:
        One dict per execution, in order.
    """
    try:
        with get_connection() as conn:
            rows = conn.execute(load_query("workflows/list_steps.sql"), (run_id,)).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:list_steps")
        return []


def _child_usage(child_session_id: str | None) -> tuple[Any, ...]:
    """Add up the spend of a sub-agent session.

    Args:
        child_session_id: Session of the sub-agent, or ``None`` when the node has none.

    Returns:
        ``(provider, model, prompt_tokens, completion_tokens, total_tokens, total_time,
        cost_input, cost_output, cost_total)``; zeros and ``None`` without a session.
    """
    empty = (None, None, 0, 0, 0, 0.0, 0.0, 0.0, 0.0)
    if not child_session_id:
        return empty
    try:
        with get_connection() as conn:
            row = conn.execute(
                load_query("workflows/child_usage.sql"),
                (child_session_id, child_session_id, child_session_id),
            ).fetchone()
        if row is None:
            return empty
        return (
            row["provider"], row["model"], row["prompt_tokens"], row["completion_tokens"],
            row["total_tokens"], row["total_time"], row["cost_input"], row["cost_output"],
            row["cost_total"],
        )
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:_child_usage")
        return empty


def record_node(
    run_id: str,
    attempt: int,
    step: int,
    substep: int,
    node_id: str,
    node_type: str,
    status: str,
    result: str | None = None,
    error: str | None = None,
    child_session_id: str | None = None,
    started_at: str | None = None,
) -> bool:
    """Record one execution of a node as a row of its run.

    An agent node adds up the spend of its child session.

    Args:
        run_id: Run identifier.
        attempt: Attempt that executed the node.
        step: Step of the workflow.
        substep: Position of the node inside its step (parallel nodes).
        node_id: Node id in the YAML.
        node_type: ``agent``, ``tool``, ``rag`` or ``run``.
        status: ``success``, ``error`` or ``cancelled``.
        result: Complete output of the node, when it succeeded.
        error: Failure message, when it failed.
        child_session_id: Session of the sub-agent, in agent nodes.
        started_at: Local time the node was dispatched (now when ``None``).

    Returns:
        ``True`` when the row was stored.
    """
    try:
        now = _now()
        with db_transaction() as conn:
            cur = conn.execute(
                load_query("workflows/insert_node_row.sql"),
                (
                    attempt, step, substep, node_id, node_type, status, child_session_id,
                    result, error, *_child_usage(child_session_id), started_at or now, now, run_id,
                ),
            )
            return cur.rowcount > 0
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:record_node")
        return False


def record_engine_row(
    run_id: str,
    kind: str,
    provider: str | None,
    model: str | None,
    usage: dict[str, Any] | None,
    status: str | None = None,
    result: str | None = None,
) -> bool:
    """Record an LLM call made by the workflow engine as the next step of its run.

    The row has its own step and substep 0, the verdict or text the call
    produced and its spend. ``spend`` is not touched here: ``llm_process``
    already contemplates it.

    Args:
        run_id: Run that made the call.
        kind: ``"decision"``, ``"judge"``, ``"output"`` or ``"explain"``.
        provider: Provider used.
        model: Model used.
        usage: Usage report (``prompt_tokens``, ``completion_tokens``,
            ``total_tokens``, ``total_time``).
        status: ``approved`` or ``rejected`` (decision, judge), ``success`` or ``error``.
        result: Text the call produced (answers, verdict, output or explanation).

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
        total_time = float(usage.get("total_time") or 0)
        cost_input, cost_output, cost_total = calculate_cost(
            provider_value, model_value, prompt_tokens, completion_tokens
        )
        now = _now()
        with db_transaction() as conn:
            cur = conn.execute(
                load_query("workflows/insert_engine_row.sql"),
                (
                    kind, status, result, provider_value, model_value,
                    prompt_tokens, completion_tokens, total_tokens, total_time,
                    cost_input, cost_output, cost_total, now, now, run_id,
                ),
            )
            return cur.rowcount > 0
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:record_engine_row")
        return False


def delete_run_steps(run_id: str) -> bool:
    """Delete the node commits of a run that finished well.

    Nothing is left to resume, so what ended is removed.

    Args:
        run_id: Run identifier.

    Returns:
        ``True`` when the rows were deleted.
    """
    try:
        with db_transaction() as conn:
            conn.execute(load_query("workflows/delete_run_steps.sql"), (run_id,))
        return True
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:delete_run_steps")
        return False


def delete_workflow(name: str) -> bool:
    """Remove a workflow from the registry with its runs, commits and notifications.

    The sessions created by its runs stay in the history.

    Args:
        name: Workflow name (the id).

    Returns:
        ``True`` when everything was removed.
    """
    try:
        with db_transaction() as conn:
            conn.execute(load_query("notifications/delete_by_workflow.sql"), (name,))
            conn.execute(load_query("workflows/delete_steps.sql"), (name,))
            conn.execute(load_query("workflows/delete_runs.sql"), (name,))
            conn.execute(load_query("workflows/delete_workflow.sql"), (name,))
        return True
    except Exception as exc:
        log_error(str(exc), source="workflow_db.py:delete_workflow")
        return False
