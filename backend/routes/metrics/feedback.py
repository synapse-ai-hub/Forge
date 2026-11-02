"""Response quality (feedback) metrics endpoints."""

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


@router.get("/metrics/feedback")
async def get_feedback_metrics(time_range: str = "1m") -> dict:
    """Return response quality metrics (up/down votes) with time range filter.

    Args:
        time_range: Time filter ('1h', '6h', '1d', '1w', '1m', 'all').

    Returns:
        A contract response with totals and quality series by type/model.
    """
    try:
        time_range = _normalize_range(time_range)
        clause, params = time_clause(time_range, "created_at")

        with get_connection() as conn:
            total = _fetch_one(conn, "metrics/feedback/total.sql", clause, params) or 0

            by_type_sql = with_time(load_query("metrics/feedback/by_type.sql"), clause)
            by_type_rows = conn.execute(by_type_sql, params).fetchall()
            by_type = [{"name": row["feedback_type"], "count": row["cnt"]} for row in by_type_rows]
            up = next((r["count"] for r in by_type if r["name"] == "up"), 0)
            down = next((r["count"] for r in by_type if r["name"] == "down"), 0)
            quality_rate = round(up / total * 100, 1) if total > 0 else 0.0

            by_model_sql = with_time(load_query("metrics/feedback/by_model.sql"), clause)
            by_model_rows = conn.execute(by_model_sql, params).fetchall()
            by_model = [
                {"provider": row["provider"], "model": row["model"], "type": row["feedback_type"], "count": row["cnt"]}
                for row in by_model_rows
            ]

        return validate_response(
            make_success_response(
                message="Feedback metrics obtenidas",
                data={
                    "total": total,
                    "up": up,
                    "down": down,
                    "quality_rate": quality_rate,
                    "by_type": by_type,
                    "by_model": by_model,
                },
                usage=zero_usage(),
            )
        )
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics/feedback.py:get_feedback_metrics")
        return make_error_response(message="Error fetching feedback metrics")


@router.get("/metrics/feedback/export")
async def export_feedback_csv(time_range: str = "1m") -> Any:
    """Download the quality votes for the time range as a CSV file.

    Args:
        time_range: Time filter ('1h', '6h', '1d', '1w', '1m', 'all').

    Returns:
        A ``text/csv`` attachment with every vote row in the range.
    """
    try:
        time_range = _normalize_range(time_range)
        clause, params = time_clause(time_range, "created_at")

        with get_connection() as conn:
            sql = with_time(load_query("metrics/feedback/export.sql"), clause)
            rows = conn.execute(sql, params).fetchall()
        return _rows_to_csv_response(rows, "feedback")
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics/feedback.py:export_feedback_csv")
        return make_error_response(message="Error exporting feedback CSV")
