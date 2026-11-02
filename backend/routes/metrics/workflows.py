"""Workflow run metrics endpoints."""

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


@router.get("/metrics/workflows")
async def get_workflow_metrics(time_range: str = "1m") -> dict:
    """Return workflow run metrics with time range filter.

    Args:
        time_range: Time filter ('1h', '6h', '1d', '1w', '1m', 'all').

    Returns:
        A contract response with totals and per-workflow/source/status series.
    """
    try:
        time_range = _normalize_range(time_range)
        clause, params = time_clause(time_range, "started_at")

        with get_connection() as conn:
            total_runs = _fetch_one(conn, "metrics/workflows/total_runs.sql", clause, params) or 0

            by_workflow_sql = with_time(load_query("metrics/workflows/by_workflow.sql"), clause)
            by_workflow = [{"name": row["workflow_name"], "count": row["cnt"]} for row in conn.execute(by_workflow_sql, params).fetchall()]

            by_source_sql = with_time(load_query("metrics/workflows/by_source.sql"), clause)
            by_source = [{"name": row["source"], "count": row["cnt"]} for row in conn.execute(by_source_sql, params).fetchall()]

            by_status_sql = with_time(load_query("metrics/workflows/by_status.sql"), clause)
            by_status = [{"name": row["status"], "count": row["cnt"]} for row in conn.execute(by_status_sql, params).fetchall()]

        return validate_response(
            make_success_response(
                message="Workflow metrics obtenidas",
                data={
                    "total_runs": total_runs,
                    "by_workflow": by_workflow,
                    "by_source": by_source,
                    "by_status": by_status,
                },
                usage=zero_usage(),
            )
        )
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics/workflows.py:get_workflow_metrics")
        return make_error_response(message="Error fetching workflow metrics")


@router.get("/metrics/workflows/export")
async def export_workflows_csv(time_range: str = "1m") -> Any:
    """Download the workflow runs for the time range as a CSV file.

    Args:
        time_range: Time filter ('1h', '6h', '1d', '1w', '1m', 'all').

    Returns:
        A ``text/csv`` attachment with every run row in the range.
    """
    try:
        time_range = _normalize_range(time_range)
        clause, params = time_clause(time_range, "started_at")

        with get_connection() as conn:
            sql = with_time(load_query("metrics/workflows/export.sql"), clause)
            rows = conn.execute(sql, params).fetchall()
        return _rows_to_csv_response(rows, "workflows")
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics/workflows.py:export_workflows_csv")
        return make_error_response(message="Error exporting workflows CSV")
