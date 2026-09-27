"""Database schema setup for the agent (no migrations).

Creates the ``sessions``, ``messages`` and ``config_kv`` tables using
``CREATE TABLE IF NOT EXISTS`` so the operation is idempotent and can be
called once at startup without per-session overhead.

NOTE: This module intentionally contains NO migration logic. When the
schema changes, the old database file is deleted and recreated from
scratch — the ``IF NOT EXISTS`` guard then simply creates the new tables.

NOTE: If columns are added or modified, migrations must be added here
and executed during update (pipeline/update) so existing user databases
are updated without data loss.
"""

from __future__ import annotations

import sqlite3

from backend.agent.utils.contract import zero_usage


def setup_database(conn: sqlite3.Connection) -> None:
    """Create all agent tables on the given connection.

    Idempotent: uses ``CREATE TABLE IF NOT EXISTS`` so calling it repeatedly
    (or after the tables already exist) adds no latency and recreates nothing.

    Args:
        conn: An open ``sqlite3.Connection`` (already configured with PRAGMAs).
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata TEXT,
            title TEXT,
            parent_id TEXT,
            FOREIGN KEY (parent_id) REFERENCES sessions(session_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            reasoning TEXT,
            tool_calls TEXT,
            tool_results TEXT,
            status TEXT,
            message TEXT,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_tokens INTEGER,
            total_time REAL,
            time_to_first_token REAL,
            tool_call_id TEXT,
            tool_name TEXT,
            model TEXT,
            provider TEXT,
            cost_input REAL,
            cost_output REAL,
            cost_total REAL,
            turn_number INTEGER,
            step INTEGER DEFAULT 0,
            substep INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_parent_id ON sessions(parent_id);

        CREATE TABLE IF NOT EXISTS turn_latency (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            turn_number INTEGER NOT NULL,
            latency REAL,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_turn_latency_session_turn ON turn_latency(session_id, turn_number);

        CREATE TABLE IF NOT EXISTS config_kv (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS providers (
            provider TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            models TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS provider_api_keys (
            provider TEXT PRIMARY KEY,
            api_key_encrypted TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS error_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            parent_id TEXT,
            turn_number INTEGER,
            exception TEXT NOT NULL,
            source TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_error_log_session_id ON error_log(session_id);
        CREATE INDEX IF NOT EXISTS idx_error_log_created_at ON error_log(created_at);

        CREATE TABLE IF NOT EXISTS context_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            turn_number INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            size INTEGER,
            content BLOB,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_attachments_session_turn
            ON attachments(session_id, turn_number);

        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            prompt TEXT NOT NULL,
            time TEXT NOT NULL DEFAULT '09:00',
            days TEXT NOT NULL DEFAULT '[0,1,2,3,4,5,6]',
            enabled INTEGER NOT NULL DEFAULT 1,
            repetitions TEXT,
            tool_permissions TEXT,
            skill_permissions TEXT,
            parameters TEXT,
            last_run_date TEXT,
            slot_runs TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS task_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            session_id TEXT,
            status TEXT NOT NULL,
            detail TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            FOREIGN KEY (task_id) REFERENCES scheduled_tasks(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_task_runs_task_id ON task_runs(task_id);
        CREATE INDEX IF NOT EXISTS idx_task_runs_started_at ON task_runs(started_at);

        CREATE TABLE IF NOT EXISTS model_catalog (
            provider TEXT NOT NULL,
            model_id TEXT NOT NULL,
            name TEXT,
            description TEXT,
            family TEXT,
            context_window INTEGER,
            input_limit INTEGER,
            output_limit INTEGER,
            reasoning INTEGER DEFAULT 0,
            reasoning_options TEXT,
            tool_call INTEGER DEFAULT 0,
            attachment INTEGER DEFAULT 0,
            temperature INTEGER DEFAULT 0,
            structured_output INTEGER DEFAULT 0,
            modalities_input TEXT,
            modalities_output TEXT,
            cost_input REAL,
            cost_output REAL,
            cost_cache_read REAL,
            cost_cache_write REAL,
            open_weights INTEGER DEFAULT 0,
            status TEXT,
            api TEXT,
            npm TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE(provider, model_id)
        );

        CREATE INDEX IF NOT EXISTS idx_model_catalog_provider ON model_catalog(provider);
        CREATE INDEX IF NOT EXISTS idx_model_catalog_model ON model_catalog(model_id);
        CREATE INDEX IF NOT EXISTS idx_model_catalog_reasoning ON model_catalog(reasoning);
        CREATE INDEX IF NOT EXISTS idx_model_catalog_context ON model_catalog(context_window);

        CREATE TABLE IF NOT EXISTS billing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            requests INTEGER DEFAULT 0,
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            cost REAL DEFAULT 0.0,
            provider_limits TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(provider)
        );

        CREATE INDEX IF NOT EXISTS idx_billing_provider ON billing(provider);

        CREATE TABLE IF NOT EXISTS spend (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            month TEXT NOT NULL,
            requests INTEGER DEFAULT 0,
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            cost_input REAL DEFAULT 0.0,
            cost_output REAL DEFAULT 0.0,
            cost_total REAL DEFAULT 0.0,
            updated_at TEXT NOT NULL,
            UNIQUE(provider, model, month)
        );

        CREATE INDEX IF NOT EXISTS idx_spend_provider_model ON spend(provider, model, month);

        CREATE TABLE IF NOT EXISTS spend_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            model TEXT,
            limit_amount REAL NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(provider, model)
        );

        CREATE INDEX IF NOT EXISTS idx_spend_limits_provider_model ON spend_limits(provider, model);

        CREATE TABLE IF NOT EXISTS external_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            units INTEGER DEFAULT 0,
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            duration REAL,
            session_id TEXT,
            turn_number INTEGER,
            step INTEGER,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_external_usage_kind ON external_usage(kind);

        CREATE TABLE IF NOT EXISTS creator_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            caller TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            total_time REAL,
            cost_input REAL DEFAULT 0.0,
            cost_output REAL DEFAULT 0.0,
            cost_total REAL DEFAULT 0.0,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_creator_calls_caller ON creator_calls(caller);
        """
    )
