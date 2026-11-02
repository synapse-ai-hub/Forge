"""LLM model usage metrics endpoints."""

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


@router.get("/metrics/models/export")
async def export_models_csv(time_range: str = "1m") -> Any:
    """Download the assistant LLM calls table for the time range as a CSV file.

    Args:
        time_range: Time filter ('1h', '6h', '1d', '1w', '1m', 'all').

    Returns:
        A ``text/csv`` attachment with every assistant model call row in the range.
    """
    try:
        time_range = _normalize_range(time_range)
        clause, params = time_clause(time_range, "created_at")

        with get_connection() as conn:
            sql = with_time(load_query("metrics/models/export.sql"), clause)
            rows = conn.execute(sql, params).fetchall()
        return _rows_to_csv_response(rows, "models")
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics/models.py:export_models_csv")
        return make_error_response(message="Error exporting models CSV")


@router.get("/metrics/models")
async def get_model_metrics(time_range: str = "1m") -> dict:
    """Return LLM usage metrics grouped by model from agent.db with time range filter.

    Args:
        time_range: Time filter ('1h', '6h', '1d', '1w', '1m', 'all').

    Returns:
        A contract response with per-model call counts.
    """
    try:
        time_range = _normalize_range(time_range)
        clause, params = time_clause(time_range, "created_at")

        with get_connection() as conn:
            usage_sql = with_time(load_query("metrics/models/usage.sql"), clause)
            model_rows = conn.execute(usage_sql, params).fetchall()
            tokens_in_sql = with_time(
                load_query("metrics/models/tokens_input.sql"), clause
            )
            tokens_in_rows = conn.execute(tokens_in_sql, params).fetchall()
            tokens_out_sql = with_time(
                load_query("metrics/models/tokens_output.sql"), clause
            )
            tokens_out_rows = conn.execute(tokens_out_sql, params).fetchall()
            tool_sql = with_time(
                load_query("metrics/models/tool_calls.sql"), clause
            )
            tool_rows = conn.execute(tool_sql, params).fetchall()
            latency_sql = with_time(
                load_query("metrics/models/latency.sql"), clause
            )
            latency_rows = conn.execute(latency_sql, params).fetchall()
        models = [
            {
                "provider": row["provider"],
                "model": row["model"],
                "count": row["cnt"],
            }
            for row in model_rows
        ]
        tokens_input = [
            {
                "provider": row["provider"],
                "model": row["model"],
                "value": row["value"],
            }
            for row in tokens_in_rows
        ]
        tokens_output = [
            {
                "provider": row["provider"],
                "model": row["model"],
                "value": row["value"],
            }
            for row in tokens_out_rows
        ]
        tool_calls = [
            {
                "provider": row["provider"],
                "model": row["model"],
                "value": row["value"],
            }
            for row in tool_rows
        ]
        latency_models = [
            {
                "provider": row["provider"],
                "model": row["model"],
                "value": row["value"],
            }
            for row in latency_rows
        ]
        total_model_calls = sum(m["count"] for m in models)
        total_models = len(models)

        return validate_response(
            make_success_response(
                message="Model metrics obtenidas",
                data={
                    "models": models,
                    "tokens_input": tokens_input,
                    "tokens_output": tokens_output,
                    "tool_calls": tool_calls,
                    "latency_models": latency_models,
                    "total_model_calls": total_model_calls,
                    "total_models": total_models,
                },
                usage=zero_usage(),
            )
        )
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics/models.py:get_model_metrics")
        return make_error_response(message="Error fetching model metrics")
