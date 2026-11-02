"""Creator request metrics endpoints."""

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
    _normalize_range,
    _rows_to_csv_response,
)

router = APIRouter(tags=["metrics"])


@router.get("/metrics/creators")
async def get_creator_metrics(time_range: str = "1m") -> dict:
    """Return creator request metrics with time range filter.

    Args:
        time_range: Time filter ('1h', '6h', '1d', '1w', '1m', 'all').

    Returns:
        A contract response with totals and per-kind/status series.
    """
    try:
        time_range = _normalize_range(time_range)
        clause, params = time_clause(time_range, "created_at")

        with get_connection() as conn:
            total_requests = _fetch_one(conn, "metrics/creators/total_requests.sql", clause, params) or 0

            by_kind_sql = with_time(load_query("metrics/creators/by_kind.sql"), clause)
            by_kind = [{"name": row["kind"], "count": row["cnt"]} for row in conn.execute(by_kind_sql, params).fetchall()]

            by_status_sql = with_time(load_query("metrics/creators/by_status.sql"), clause)
            by_status = [{"name": row["status"], "count": row["cnt"]} for row in conn.execute(by_status_sql, params).fetchall()]

        return validate_response(
            make_success_response(
                message="Creator metrics obtenidas",
                data={
                    "total_requests": total_requests,
                    "by_kind": by_kind,
                    "by_status": by_status,
                },
                usage=zero_usage(),
            )
        )
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics/creators.py:get_creator_metrics")
        return make_error_response(message="Error fetching creator metrics")


@router.get("/metrics/creators/export")
async def export_creators_csv(time_range: str = "1m") -> Any:
    """Download the creator requests for the time range as a CSV file.

    Args:
        time_range: Time filter ('1h', '6h', '1d', '1w', '1m', 'all').

    Returns:
        A ``text/csv`` attachment with every request row in the range.
    """
    try:
        time_range = _normalize_range(time_range)
        clause, params = time_clause(time_range, "created_at")

        with get_connection() as conn:
            sql = with_time(load_query("metrics/creators/export.sql"), clause)
            rows = conn.execute(sql, params).fetchall()
        return _rows_to_csv_response(rows, "creators")
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics/creators.py:export_creators_csv")
        return make_error_response(message="Error exporting creators CSV")
