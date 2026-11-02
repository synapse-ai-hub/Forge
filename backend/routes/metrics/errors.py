"""Agent error metrics endpoints."""

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


@router.get("/metrics/errors")
async def get_error_metrics(time_range: str = "1m") -> dict:
    """Return agent error metrics with time range filter.

    Only agent errors are counted: messages with status 'error'
    (failed turns and failed tool calls). Backend/programming errors
    from error_log are never included.

    Args:
        time_range: Time filter ('1h', '6h', '1d', '1w', '1m', 'all').

    Returns:
        A contract response with total errors and per-model/per-tool series.
    """
    try:
        time_range = _normalize_range(time_range)
        clause, params = time_clause(time_range, "created_at")

        with get_connection() as conn:
            total_errors = (
                _fetch_one(conn, "metrics/agent_errors/total_errors.sql", clause, params)
                or 0
            )

            by_model_sql = with_time(
                load_query("metrics/agent_errors/by_model.sql"), clause
            )
            model_rows = conn.execute(by_model_sql, params).fetchall()
            errors_by_model = [
                {
                    "provider": row["provider"],
                    "model": row["model"],
                    "count": row["cnt"],
                }
                for row in model_rows
            ]

            by_tool_sql = with_time(
                load_query("metrics/agent_errors/by_tool.sql"), clause
            )
            tool_rows = conn.execute(by_tool_sql, params).fetchall()
            errors_by_tool = [
                {"tool": row["tool"], "count": row["cnt"]} for row in tool_rows
            ]

        return validate_response(
            make_success_response(
                message="Error metrics obtenidas",
                data={
                    "total_errors": total_errors,
                    "errors_by_model": errors_by_model,
                    "errors_by_tool": errors_by_tool,
                },
                usage=zero_usage(),
            )
        )
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics/errors.py:get_error_metrics")
        return make_error_response(message="Error fetching error metrics")


@router.get("/metrics/errors/export")
async def export_errors_csv(time_range: str = "1m") -> Any:
    """Download the agent error messages for the time range as a CSV file.

    Args:
        time_range: Time filter ('1h', '6h', '1d', '1w', '1m', 'all').

    Returns:
        A ``text/csv`` attachment with every error row in the range.
    """
    try:
        time_range = _normalize_range(time_range)
        clause, params = time_clause(time_range, "messages.created_at")

        with get_connection() as conn:
            sql = with_time(load_query("metrics/agent_errors/export.sql"), clause)
            rows = conn.execute(sql, params).fetchall()
        return _rows_to_csv_response(rows, "errors")
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics/errors.py:export_errors_csv")
        return make_error_response(message="Error exporting errors CSV")
