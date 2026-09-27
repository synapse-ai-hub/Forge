"""Render metric distributions with synapse_tools.eda without writing files.

Loads the .sql metric scripts with pandas read_sql (the temporal filter
stays in SQL so only the range rows travel) and converts the matplotlib
figure to base64 in memory. Nothing is ever written to disk.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from typing import Any

_current_dir = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_current_dir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import matplotlib

matplotlib.use("Agg")

import pandas as pd
from synapse_tools.eda import outliers as _outliers

from backend.utils.db import DB_PATH

_METRICS_SQL_DIR = os.path.join(
    _PROJECT_ROOT, "backend", "agent", "agent_db", "metrics"
)

_VALID_RANGES = {"1h", "6h", "1d", "1w", "1m", "all"}


def time_clause(time_range: str, column_name: str) -> tuple[str, tuple[Any, ...]]:
    """Return a parameterized SQL time filter clause and its parameters."""
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


def load_metric_sql(name: str) -> str:
    """Load a metric SQL script from backend/agent/agent_db/metrics/."""
    path = os.path.join(_METRICS_SQL_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def render_outliers_figure(
    query_file: str,
    value_column: str,
    time_range: str = "1m",
    placeholder: str = "{TIME_CLAUSE_SES}",
    filter_column: str = "sessions.created_at",
    color: str = "#8b5cf6",
    fig_size: tuple[int, int] = (18, 6),
) -> dict:
    """Run a metric query and render the outliers figure as base64.

    Args:
        query_file: Script path relative to the metrics dir.
        value_column: Result column with the numeric values to plot.
        time_range: One of 1h, 6h, 1d, 1w, 1m, all.
        placeholder: Time filter placeholder used inside the script.
        filter_column: Column the time filter applies to.
        color: Figure color.

    Returns:
        Dict with image_base64 (PNG data URI) and stats.

    Raises:
        ValueError: If the query returns no plottable values.
    """
    if time_range not in _VALID_RANGES:
        time_range = "1m"
    clause, params = time_clause(time_range, filter_column)
    sql = load_metric_sql(query_file).replace(placeholder, clause)
    code_lines = [
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    ]
    count = "\n".join(code_lines).count("?")
    full_params: tuple[Any, ...] = params * count if count else ()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    try:
        df = pd.read_sql(sql, conn, params=full_params if full_params else None)
    finally:
        conn.close()
    if value_column not in df.columns:
        raise ValueError(f"Column {value_column} not in query result")
    values = pd.to_numeric(df[value_column], errors="coerce").dropna()
    if values.empty:
        raise ValueError("No data for this range")
    result = _outliers(
        pd.DataFrame({value_column: values}),
        column=value_column,
        color=color,
        fig_size=fig_size,
        visualization=False,
        save=False,
        return_dict=True,
        return_base64=True,
    )
    image_b64 = (result or {}).pop("figure_base64", None)
    stats: dict[str, Any] = {}
    for key, value in (result or {}).items():
        try:
            import numpy as _np

            if isinstance(value, _np.generic):
                value = value.item()
        except Exception:
            pass
        stats[key] = value
    return {
        "image_base64": "data:image/png;base64," + (image_b64 or ""),
        "stats": stats,
    }
