"""Tool usage metrics endpoints."""

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


@router.get("/metrics/tools/export")
async def export_tools_csv(time_range: str = "1m") -> Any:
    """Download the tool calls table for the time range as a CSV file.

    Args:
        time_range: Time filter ('1h', '6h', '1d', '1w', '1m', 'all').

    Returns:
        A ``text/csv`` attachment with every tool call row in the range.
    """
    try:
        time_range = _normalize_range(time_range)
        clause, params = time_clause(time_range, "created_at")

        with get_connection() as conn:
            sql = with_time(load_query("metrics/tools/export.sql"), clause)
            rows = conn.execute(sql, params).fetchall()
        return _rows_to_csv_response(rows, "tools")
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics/tools.py:export_tools_csv")
        return make_error_response(message="Error exporting tools CSV")


@router.get("/metrics/tools")
async def get_tool_metrics(time_range: str = "1m") -> dict:
    """Return tool usage metrics aggregated from agent.db with time range filter.

    Args:
        time_range: Time filter ('1h', '6h', '1d', '1w', '1m', 'all').

    Returns:
        A contract response with tool usage, totals and the calls to each sub-agent.
    """
    try:
        time_range = _normalize_range(time_range)
        clause, params = time_clause(time_range, "created_at")

        with get_connection() as conn:
            usage_sql = with_time(load_query("metrics/tools/tool_usage.sql"), clause)
            tool_rows = conn.execute(usage_sql, params).fetchall()
            tool_usage = [
                {
                    "name": row["tool_name"],
                    "count": row["cnt"],
                    "avg_time": round(float(row["avg_time"] or 0.0), 2),
                }
                for row in tool_rows
            ]
            total_tool_calls = sum(t["count"] for t in tool_usage)

            avg_time_per_tool_call = (
                _fetch_one(
                    conn, "metrics/tools/avg_time_per_tool_call.sql", clause, params
                )
                or 0.0
            )
            avg_time_per_tool_call = round(float(avg_time_per_tool_call), 2)

            subagent_sql = with_time(
                load_query("metrics/tools/subagent_calls.sql"), clause
            )
            subagent_rows = conn.execute(subagent_sql, params).fetchall()
        top_subagents = [
            {"name": row["agent_name"], "count": row["cnt"]} for row in subagent_rows
        ]

        return validate_response(
            make_success_response(
                message="Tool metrics obtenidas",
                data={
                    "tool_usage": tool_usage,
                    "total_tool_calls": total_tool_calls,
                    "avg_time_per_tool_call": avg_time_per_tool_call,
                    "top_subagents": top_subagents,
                },
                usage=zero_usage(),
            )
        )
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics/tools.py:get_tool_metrics")
        return make_error_response(message="Error fetching tool metrics")
