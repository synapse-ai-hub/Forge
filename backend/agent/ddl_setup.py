"""Database schema setup for the agent.

Creates the tables using ``CREATE TABLE IF NOT EXISTS`` so the operation is idempotent and can be
called once at startup without per-session overhead. There are no migrations: the database is
created from scratch with every new build.
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
    "ddl/creators.sql",
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

    Raises:
        sqlite3.Error: If a DDL statement fails.
    """
    script = "\n".join(load_query(name) for name in _DDL_SCRIPTS)
    conn.executescript(script)
