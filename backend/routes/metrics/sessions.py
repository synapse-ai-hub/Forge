"""Session metrics endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.agent.utils.contract import (
    make_error_response,
    make_success_response,
    validate_response,
    zero_usage,
)
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.db import get_connection
from backend.agent.utils.queries import load_query, time_clause, with_time
from backend.routes.metrics.common import (
    _fetch_one,
    _fill_cantidad_buckets,
    _normalize_range,
    _rows_to_csv_response,
)

router = APIRouter(tags=["metrics"])


@router.get("/metrics/sessions")
async def get_session_metrics(time_range: str = "1m") -> dict:
    """Return session metrics: totals plus the 12-bar creation chart.

    Args:
        time_range: Time filter ('1h', '6h', '1d', '1w', '1m', 'all').

    Returns:
        A contract response with ``data`` containing session totals and
        the binned ``cantidad`` series.
    """
    try:
        time_range = _normalize_range(time_range)
        clause, params = time_clause(time_range, "created_at")

        with get_connection() as conn:
            total_sessions = _fetch_one(
                conn, "metrics/sessions/total_sessions.sql", clause, params
            ) or 0

            created_sql = with_time(
                load_query("metrics/sessions/created_at_list.sql"), clause
            )
            created_rows = conn.execute(created_sql, params).fetchall()
            cantidad = _fill_cantidad_buckets(time_range, created_rows)

            return validate_response(
                make_success_response(
                    message="Session metrics obtenidas",
                    data={
                        "total_sessions": total_sessions,
                        "cantidad": cantidad,
                    },
                    usage=zero_usage(),
                )
            )
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics/sessions.py:get_session_metrics")
        return make_error_response(message="Error fetching session metrics")


@router.get("/metrics/sessions/export")
async def export_sessions_csv(time_range: str = "1m") -> Any:
    """Download the sessions table for the time range as a CSV file.

    Args:
        time_range: Time filter ('1h', '6h', '1d', '1w', '1m', 'all').

    Returns:
        A ``text/csv`` attachment with every session row in the range.
    """
    try:
        time_range = _normalize_range(time_range)
        clause, params = time_clause(time_range, "sessions.created_at")

        with get_connection() as conn:
            sql = with_time(load_query("metrics/sessions/export.sql"), clause)
            rows = conn.execute(sql, params).fetchall()
        return _rows_to_csv_response(rows, "sessions")
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics/sessions.py:export_sessions_csv")
        return make_error_response(message="Error exporting sessions CSV")
