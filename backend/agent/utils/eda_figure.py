"""Render metric distributions with synapse_tools.eda without writing files.

Loads the .sql query scripts with pandas read_sql (the temporal filter
stays in SQL so only the range rows travel) and converts the matplotlib
figure to base64 in memory. Nothing is ever written to disk.
"""

from __future__ import annotations

import sqlite3
from typing import Any

import matplotlib

matplotlib.use("Agg")

import pandas as pd
from synapse_tools.eda import outliers as _outliers

from backend.agent.utils.db import DB_PATH
from backend.agent.utils.queries import TIME_PLACEHOLDER, load_query, time_clause

_VALID_RANGES = {"1h", "6h", "1d", "1w", "1m", "all"}


def render_outliers_figure(
    query_file: str,
    value_column: str,
    time_range: str = "1m",
    placeholder: str = TIME_PLACEHOLDER,
    filter_column: str = "sessions.created_at",
    color: str = "#8b5cf6",
    fig_size: tuple[int, int] = (18, 6),
) -> dict:
    """Run a metric query and render the outliers figure as base64.

    Args:
        query_file: Script path relative to the queries root
            (e.g. ``"metrics/sessions/messages_per_session.sql"``).
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
    sql = load_query(query_file).replace(placeholder, clause)
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
