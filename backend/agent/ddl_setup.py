"""Database schema setup for the agent.

Creates the tables using ``CREATE TABLE IF NOT EXISTS`` so the operation is idempotent and can be
called once at startup without per-session overhead, plus the legacy
``turn_latency`` and ``attachments`` FOREIGN KEY migrations.
"""

from __future__ import annotations

import logging
import sqlite3

from backend.agent.utils.queries import load_query

logger = logging.getLogger(__name__)

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
    "ddl/router_config.sql",
    "ddl/email_accounts.sql",
    "ddl/email_domains.sql",
)


def setup_database(conn: sqlite3.Connection) -> None:
    """Create all agent tables on the given connection.

    Idempotent: uses ``CREATE TABLE IF NOT EXISTS`` so calling it repeatedly
    (or after the tables already exist) adds no latency and recreates nothing.

    Also migrates legacy ``turn_latency`` and ``attachments`` tables that
    still carry a ``FOREIGN KEY (session_id) REFERENCES sessions``
    (creator conversations have no row in ``sessions`` and must never
    fail the turn).

    Args:
        conn: An open ``sqlite3.Connection`` (already configured with PRAGMAs).

    Raises:
        sqlite3.Error: If a DDL statement fails.
    """
    script = "\n".join(load_query(name) for name in _DDL_SCRIPTS)
    conn.executescript(script)
    _migrate_turn_latency_no_fk(conn)
    _migrate_attachments_no_fk(conn)


def _migrate_turn_latency_no_fk(conn: sqlite3.Connection) -> None:
    """Drop the legacy FOREIGN KEY of ``turn_latency`` when present.

    SQLite cannot drop a foreign key in place, so the table is rebuilt
    without it, preserving existing rows.

    Args:
        conn: An open ``sqlite3.Connection``.
    """
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='turn_latency'"
        ).fetchone()
        sql = (row[0] if row else "") or ""
        if "turn_latency" not in sql or "FOREIGN KEY" not in sql.upper():
            return
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS turn_latency_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                turn_number INTEGER NOT NULL,
                latency REAL
            );
            INSERT OR IGNORE INTO turn_latency_new (id, session_id, turn_number, latency)
                SELECT id, session_id, turn_number, latency FROM turn_latency;
            DROP TABLE turn_latency;
            ALTER TABLE turn_latency_new RENAME TO turn_latency;
            CREATE INDEX IF NOT EXISTS idx_turn_latency_session_turn
                ON turn_latency(session_id, turn_number);
            """
        )
        conn.commit()
    except Exception:
        logger.exception("Failed to migrate turn_latency without FK")
        try:
            conn.rollback()
        except Exception:
            pass


def _migrate_attachments_no_fk(conn: sqlite3.Connection) -> None:
    """Drop the legacy FOREIGN KEY of ``attachments`` when present.

    Creators store their files with ``session_id = creator_id`` which has
    no row in ``sessions``. Rebuilds the table without FK, preserving rows.

    Args:
        conn: An open ``sqlite3.Connection``.
    """
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='attachments'"
        ).fetchone()
        sql = (row[0] if row else "") or ""
        if "attachments" not in sql or "FOREIGN KEY" not in sql.upper():
            return
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS attachments_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                turn_number INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                size INTEGER,
                content BLOB,
                created_at TEXT NOT NULL
            );
            INSERT OR IGNORE INTO attachments_new (id, session_id, turn_number, file_name, size, content, created_at)
                SELECT id, session_id, turn_number, file_name, size, content, created_at FROM attachments;
            DROP TABLE attachments;
            ALTER TABLE attachments_new RENAME TO attachments;
            CREATE INDEX IF NOT EXISTS idx_attachments_session_turn
                ON attachments(session_id, turn_number);
            """
        )
        conn.commit()
    except Exception:
        logger.exception("Failed to migrate attachments without FK")
        try:
            conn.rollback()
        except Exception:
            pass
