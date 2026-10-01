"""SQLite database utilities for the agent backend.

Provides centralized database connection management to avoid code duplication.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from contextlib import contextmanager
from typing import Generator

# ---------------------------------------------------------------------------
# Project root for absolute imports
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_current_dir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Database path
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(
    _PROJECT_ROOT, "backend", "agent", "agent_db", "agent.db"
)


def get_connection() -> sqlite3.Connection:
    """Create a new SQLite connection to agent.db.

    Configures the connection with optimized PRAGMAs for performance and safety.

    Returns:
        A new sqlite3.Connection configured with row_factory and WAL mode.
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def db_transaction() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database transactions with automatic cleanup.

    Handles connection, commit on success, rollback on error, and cleanup.

    Usage:
        with db_transaction() as conn:
            conn.execute("INSERT INTO ...", (data,))
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
