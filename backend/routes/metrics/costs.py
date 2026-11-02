"""Cost metrics endpoints."""

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
from backend.routes.metrics.common import _normalize_range, _rows_to_csv_response

router = APIRouter(tags=["metrics"])


@router.get("/metrics/costs")
async def get_cost_metrics(time_range: str = "1m") -> dict:
    """Return cost metrics grouped by provider/model from agent.db with time range filter.

    Args:
        time_range: Time filter ('1h', '6h', '1d', '1w', '1m', 'all').

    Returns:
        A contract response with per-model cost totals and range totals.
    """
    try:
        time_range = _normalize_range(time_range)
        clause, params = time_clause(time_range, "created_at")

        with get_connection() as conn:
            by_model_sql = with_time(
                load_query("metrics/costs/cost_by_model.sql"), clause
            )
            cost_rows = conn.execute(by_model_sql, params).fetchall()
        cost_by_model = [
            {
                "provider": row["provider"],
                "model": row["model"],
                "total": round(float(row["total"] or 0.0), 6),
                "input": round(float(row["input"] or 0.0), 6),
                "output": round(float(row["output"] or 0.0), 6),
            }
            for row in cost_rows
        ]
        total_cost = round(sum(c["total"] for c in cost_by_model), 6)
        total_input = round(sum(c["input"] for c in cost_by_model), 6)
        total_output = round(sum(c["output"] for c in cost_by_model), 6)

        return validate_response(
            make_success_response(
                message="Cost metrics obtenidas",
                data={
                    "cost_by_model": cost_by_model,
                    "total_cost": total_cost,
                    "total_input": total_input,
                    "total_output": total_output,
                },
                usage=zero_usage(),
            )
        )
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics/costs.py:get_cost_metrics")
        return make_error_response(message="Error fetching cost metrics")


@router.get("/metrics/costs/export")
async def export_costs_csv(time_range: str = "1m") -> Any:
    """Download the assistant calls with cost for the time range as a CSV file.

    Args:
        time_range: Time filter ('1h', '6h', '1d', '1w', '1m', 'all').

    Returns:
        A ``text/csv`` attachment with every cost row in the range.
    """
    try:
        time_range = _normalize_range(time_range)
        clause, params = time_clause(time_range, "created_at")

        with get_connection() as conn:
            sql = with_time(load_query("metrics/costs/export.sql"), clause)
            rows = conn.execute(sql, params).fetchall()
        return _rows_to_csv_response(rows, "costs")
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics/costs.py:export_costs_csv")
        return make_error_response(message="Error exporting costs CSV")
