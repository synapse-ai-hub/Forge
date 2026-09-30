"""Loader for external .sql query files.

Every SQL statement in the backend lives as a .sql file under
``backend/agent/agent_db/queries/``. Files are loaded relative to that
root and cached in memory (the query set is static at runtime).

The ``{TIME_CLAUSE}`` placeholder inside a script is replaced by the
parameterized time filter produced by :func:`time_clause`.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

_QUERIES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "agent",
    "agent_db",
    "queries",
)

TIME_PLACEHOLDER = "{TIME_CLAUSE}"
MODEL_PLACEHOLDER = "{MODEL_CLAUSE}"


@lru_cache(maxsize=None)
def load_query(relative_path: str) -> str:
    """Load a .sql file relative to the queries root.

    Args:
        relative_path: Path relative to ``agent_db/queries`` (e.g.
            ``"metrics/sessions/total_sessions.sql"``).

    Returns:
        The raw SQL text of the file.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    path = os.path.join(_QUERIES_DIR, relative_path)
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def time_clause(
    time_range: str, column_name: str = "created_at"
) -> tuple[str, tuple[Any, ...]]:
    """Return a parameterized SQL time filter and its tuple parameters.

    Args:
        time_range: One of ``1h``, ``6h``, ``1d``, ``1w``, ``1m``, ``all``.
        column_name: Fully qualified column the filter applies to.

    Returns:
        Tuple ``(clause, params)`` where clause starts with `` AND ``
        (empty string for ``all``). Parameters use ``?`` placeholders to
        prevent SQL injection.
    """
    if time_range == "1h":
        return f" AND {column_name} >= datetime('now', ?)", ("-1 hour",)
    if time_range == "6h":
        return f" AND {column_name} >= datetime('now', ?)", ("-6 hours",)
    if time_range == "1d":
        return f" AND {column_name} >= datetime('now', ?)", ("-1 day",)
    if time_range == "1w":
        return f" AND {column_name} >= datetime('now', ?)", ("-7 days",)
    if time_range == "1m":
        return f" AND {column_name} >= datetime('now', ?)", ("-30 days",)
    return "", ()


def with_time(sql: str, clause: str) -> str:
    """Replace the ``{TIME_CLAUSE}`` placeholder with the given clause.

    Args:
        sql: Raw SQL text possibly containing the placeholder.
        clause: Time filter clause returned by :func:`time_clause`.

    Returns:
        SQL text with the placeholder substituted.
    """
    return sql.replace(TIME_PLACEHOLDER, clause)
