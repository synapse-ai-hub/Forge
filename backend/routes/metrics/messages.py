"""Per-message metrics endpoints."""

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


@router.get("/metrics/messages")
async def get_message_metrics(time_range: str = "1m") -> dict:
    """Return the five per-message metrics with time range filter.

    One row per turn for each defined message metric: steps, input
    tokens, output tokens, time (assistant + tool) and latency (from the
    turn_latency table). Rows whose value was never loaded stay NULL and
    are excluded by the queries (NULL is never turned into 0).

    Args:
        time_range: Time filter ('1h', '6h', '1d', '1w', '1m', 'all').

    Returns:
        A contract response with ``data`` containing one row list per
        metric: steps, input_tokens, output_tokens, time and latency.
    """
    try:
        time_range = _normalize_range(time_range)
        clause, params = time_clause(time_range, "sessions.created_at")

        with get_connection() as conn:
            data: dict[str, list[dict]] = {}
            for key, path in (
                ("steps", "metrics/messages/steps_per_message.sql"),
                ("input_tokens", "metrics/messages/input_tokens_per_message.sql"),
                ("output_tokens", "metrics/messages/output_tokens_per_message.sql"),
                ("time", "metrics/messages/time_per_message.sql"),
                ("latency", "metrics/messages/latency_per_message.sql"),
            ):
                sql = with_time(load_query(path), clause)
                rows = conn.execute(sql, params).fetchall()
                data[key] = [dict(row) for row in rows]

        return validate_response(
            make_success_response(
                message="Message metrics obtenidas",
                data=data,
                usage=zero_usage(),
            )
        )
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics/messages.py:get_message_metrics")
        return make_error_response(message="Error fetching message metrics")


@router.get("/metrics/messages/export")
async def export_messages_csv(time_range: str = "1m") -> Any:
    """Download the messages table for the time range as a CSV file.

    Args:
        time_range: Time filter ('1h', '6h', '1d', '1w', '1m', 'all').

    Returns:
        A ``text/csv`` attachment with every message row in the range.
    """
    try:
        time_range = _normalize_range(time_range)
        clause, params = time_clause(time_range, "messages.created_at")

        with get_connection() as conn:
            sql = with_time(load_query("metrics/messages/export.sql"), clause)
            rows = conn.execute(sql, params).fetchall()
        return _rows_to_csv_response(rows, "messages")
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics/messages.py:export_messages_csv")
        return make_error_response(message="Error exporting messages CSV")
