"""Error logging helper for the agent backend.

Provides a ``log_error`` function that persists exception details into the
``error_log`` SQLite table.  The helper manages its own connection to the
same database used by ``SessionManager`` so it can be called from anywhere
without circular imports.

Uses ``contextvars.ContextVar`` to automatically capture session/turn context
from the agent loop, so callers don't need to pass session_id, turn_number,
parent_id, etc. explicitly on every call.
"""

from __future__ import annotations

import contextvars
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Ensure the project root is in sys.path so absolute imports (backend.*)
# resolve correctly regardless of how the file is invoked.
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(_current_dir)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

_logger = logging.getLogger(__name__)

# Same database as SessionManager
_DB_PATH = os.path.join(
    _project_root, "backend", "agent", "agent_db", "agent.db"
)

_conn: sqlite3.Connection | None = None
_initialized: bool = False

# Context variable to hold error logging context (session_id, turn_number, parent_id, depth, agent_name)
# This is set by AgentLoop.run() at the start of each turn and read by log_error()
_error_context: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "error_context", default=None
)


def set_error_context(
    session_id: str | None = None,
    turn_number: int | None = None,
    parent_id: str | None = None,
    depth: int | None = None,
    agent_name: str | None = None,
) -> contextvars.Token:
    """Set the error logging context for the current async context.

    Returns a token that can be used to reset the context (via ``reset_error_context``).
    Typically called at the start of each agent loop iteration/turn.

    Args:
        session_id: Current session identifier.
        turn_number: Current turn number.
        parent_id: Parent session/agent identifier (for sub-agents).
        depth: Current sub-agent nesting depth.
        agent_name: Name of the current agent (None for router).

    Returns:
        A contextvars.Token to restore the previous context.
    """
    ctx = {
        "session_id": session_id,
        "turn_number": turn_number,
        "parent_id": parent_id,
        "depth": depth,
        "agent_name": agent_name,
    }
    return _error_context.set(ctx)


def reset_error_context(token: contextvars.Token) -> None:
    """Reset the error logging context to a previous state.

    Args:
        token: Token returned by ``set_error_context``.
    """
    _error_context.reset(token)


def get_error_context() -> dict | None:
    """Get the current error logging context.

    Returns:
        The context dict or ``None`` if not set.
    """
    return _error_context.get()


def _get_connection() -> sqlite3.Connection:
    """Get or create the shared SQLite connection with WAL mode.

    Returns:
        An open ``sqlite3.Connection``.
    """
    global _conn, _initialized
    if _conn is None:
        db_dir = os.path.dirname(_DB_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _ensure_error_table(conn)
        _conn = conn
        _initialized = True
    return _conn


def _ensure_error_table(conn: sqlite3.Connection) -> None:
    """Create the ``error_log`` table if it does not exist.

    DDL lives in ``queries/ddl/error_log.sql`` (shared with ddl_setup).

    Args:
        conn: An open SQLite connection.
    """
    from backend.agent.utils.queries import load_query

    conn.executescript(load_query("ddl/error_log.sql"))


def log_error(
    exception: str,
    session_id: str | None = None,
    parent_id: str | None = None,
    turn_number: int | None = None,
    source: str | None = None,
) -> None:
    """Persist an exception record in the ``error_log`` table.

    This function is designed to be called from ``except`` blocks across
    the entire backend.  It manages its own database connection so it does
    not depend on ``SessionManager`` or ``instances``, avoiding circular
    imports.

    Context (session_id, turn_number, parent_id) is automatically read from
    the context variable set by ``AgentLoop.run()`` if not explicitly provided.

    Args:
        exception: The string representation of the exception
            (``str(e)`` or ``repr(e)``).
        session_id: Optional session identifier where the error occurred.
            If omitted, read from context.
        parent_id: Optional parent session/agent identifier.
            If omitted, read from context.
        turn_number: Optional turn number within the session.
            If omitted, read from context.
        source: Optional source label (e.g. ``"tools.py:read_file"``).
    """
    # Resolve context from contextvar if not explicitly provided
    ctx = _error_context.get()
    if ctx:
        session_id = session_id or ctx.get("session_id")
        turn_number = turn_number or ctx.get("turn_number")
        parent_id = parent_id or ctx.get("parent_id")
        # Optionally enrich source with agent_name/depth from context
        if source is None:
            agent_name = ctx.get("agent_name")
            depth = ctx.get("depth")
            if agent_name or depth is not None:
                parts = []
                if agent_name:
                    parts.append(f"agent={agent_name}")
                if depth is not None:
                    parts.append(f"depth={depth}")
                source = f"context:{','.join(parts)}"

    try:
        # Lazy import: error_logger is imported very early in the app
        # bootstrap and a module-level import of backend.agent.utils would close
        # an import cycle (backend.agent.utils -> spend_handler -> error_logger).
        from backend.agent.utils.queries import load_query

        conn = _get_connection()
        now = datetime.now().isoformat()
        conn.execute(
            load_query("errors/insert_error.sql"),
            (session_id, parent_id, turn_number, exception, source, now),
        )
        conn.commit()
    except Exception as e:
        _logger.exception("Failed to log error to database: %s", e)