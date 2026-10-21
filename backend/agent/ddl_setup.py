"""Database schema setup for the agent (no migrations).

Creates the tables using ``CREATE TABLE IF NOT EXISTS`` so the operation is idempotent and can be
called once at startup without per-session overhead.


NOTE: If columns are added or modified, migrations must be added here
and executed during update (pipeline/update) so existing user databases
are updated without data loss.
"""

from __future__ import annotations

import sqlite3

from backend.agent.utils.queries import load_query

# DDL scripts in agent_db/queries/ddl/, executed in a single script.
_DDL_SCRIPTS: tuple[str, ...] = (
    "ddl/sessions.sql",
    "ddl/messages.sql",
    "ddl/turn_latency.sql",
    "ddl/config_kv.sql",
    "ddl/providers.sql",
    "ddl/provider_api_keys.sql",
    "ddl/error_log.sql",
    "ddl/context_files.sql",
    "ddl/attachments.sql",
    "ddl/scheduled_tasks.sql",
    "ddl/task_runs.sql",
    "ddl/model_catalog.sql",
    "ddl/decision_catalog.sql",
    "ddl/billing.sql",
    "ddl/spend.sql",
    "ddl/spend_limits.sql",
    "ddl/external_usage.sql",
    "ddl/creator_calls.sql",
    "ddl/creator_runs.sql",
    "ddl/step_frontier.sql",
    "ddl/message_feedback.sql",
    "ddl/workflows.sql",
    "ddl/workflow_runs.sql",
    "ddl/workflow_run_steps.sql",
    "ddl/notifications.sql",
)


def setup_database(conn: sqlite3.Connection) -> None:
    """Create all agent tables on the given connection.

    Idempotent: uses ``CREATE TABLE IF NOT EXISTS`` so calling it repeatedly
    (or after the tables already exist) adds no latency and recreates nothing.

    Args:
        conn: An open ``sqlite3.Connection`` (already configured with PRAGMAs).
    """
    script = "\n".join(load_query(name) for name in _DDL_SCRIPTS)
    conn.executescript(script)
    _migrate_workflow_usage(conn)
    # What ended well is deleted (like step_frontier): the commits of a run are
    # only kept while it can still be resumed, or after it failed.
    conn.execute(
        "DELETE FROM workflow_run_steps WHERE run_id IN (SELECT id FROM workflow_runs WHERE status = 'success')"
    )


_USAGE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("prompt_tokens", "INTEGER NOT NULL DEFAULT 0"),
    ("completion_tokens", "INTEGER NOT NULL DEFAULT 0"),
    ("total_tokens", "INTEGER NOT NULL DEFAULT 0"),
    ("total_time", "REAL NOT NULL DEFAULT 0"),
    ("cost_input", "REAL NOT NULL DEFAULT 0"),
    ("cost_output", "REAL NOT NULL DEFAULT 0"),
    ("cost_total", "REAL NOT NULL DEFAULT 0"),
    ("usage_calls", "TEXT"),
)


def _migrate_workflow_usage(conn: sqlite3.Connection) -> None:
    """Fold the old ``workflow_usage`` table into ``workflow_runs`` (no data lost).

    Adds the spend columns to an existing ``workflow_runs``, moves every
    ``workflow_usage`` row into the ``usage_calls`` JSON and the sums of its
    run, then drops the table. Runs once: afterwards there is nothing to move.
    """
    import json

    existing = {row[1] for row in conn.execute("PRAGMA table_info(workflow_runs)")}
    for name, definition in _USAGE_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE workflow_runs ADD COLUMN {name} {definition}")
    has_old = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='workflow_usage'"
    ).fetchone()
    if not has_old:
        return
    calls: dict[str, list[dict]] = {}
    sums: dict[str, list[float]] = {}
    rows = conn.execute(
        "SELECT run_id, purpose, provider, model, prompt_tokens, completion_tokens, total_tokens, "
        "total_time, cost_input, cost_output, cost_total, created_at FROM workflow_usage ORDER BY id"
    ).fetchall()
    keys = ("purpose", "provider", "model", "prompt_tokens", "completion_tokens", "total_tokens",
            "total_time", "cost_input", "cost_output", "cost_total", "created_at")
    for row in rows:
        run_id = row[0]
        calls.setdefault(run_id, []).append(dict(zip(keys, row[1:])))
        acc = sums.setdefault(run_id, [0.0] * 7)
        for i, value in enumerate(row[4:11]):
            acc[i] += value or 0
    for run_id, items in calls.items():
        acc = sums[run_id]
        conn.execute(
            "UPDATE workflow_runs SET prompt_tokens=?, completion_tokens=?, total_tokens=?, total_time=?, "
            "cost_input=?, cost_output=?, cost_total=?, usage_calls=? WHERE id=?",
            (int(acc[0]), int(acc[1]), int(acc[2]), acc[3], acc[4], acc[5], acc[6],
             json.dumps(items, ensure_ascii=False), run_id),
        )
    conn.execute("DROP TABLE workflow_usage")
