"""Combined overview metrics endpoint."""

from __future__ import annotations

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
from backend.routes.metrics.common import _fetch_one, _normalize_range

router = APIRouter(tags=["metrics"])


@router.get("/metrics/overview")
async def get_metrics_overview(time_range: str = "1m") -> dict:
    """Return an overview combining all metrics in a single response with time range filter.

    Args:
        time_range: Time filter ('1h', '6h', '1d', '1w', '1m', 'all').

    Returns:
        A contract response with ``data`` containing combined metrics.
    """
    try:
        time_range = _normalize_range(time_range)
        clause, params = time_clause(time_range, "created_at")
        spend_clause, spend_params = time_clause(time_range, "updated_at")

        with get_connection() as conn:
            # Session totals live in metrics/sessions/; the message total
            # (turns) lives in metrics/messages/.
            total_sessions = (
                _fetch_one(
                    conn, "metrics/sessions/total_sessions.sql", clause, params
                )
                or 0
            )
            total_messages = (
                _fetch_one(
                    conn, "metrics/messages/total_messages.sql", clause, params
                )
                or 0
            )
            avg_messages = 0.0
            if total_sessions > 0:
                avg_messages = round(total_messages / total_sessions, 1)

            # Tool usage (top 5).
            top_tools_sql = with_time(
                load_query("metrics/overview/top_tools.sql"), clause
            )
            top_tools_rows = conn.execute(top_tools_sql, params).fetchall()
            top_tools = [
                {"name": row["tool_name"], "count": row["cnt"]}
                for row in top_tools_rows
            ]

            # Token consumption.
            token_row = conn.execute(
                with_time(load_query("metrics/overview/token_totals.sql"), clause),
                params,
            ).fetchone()
            total_tokens = token_row["total"] or 0
            total_prompt_tokens = token_row["prompt"] or 0
            total_completion_tokens = token_row["completion"] or 0
            avg_tokens_per_session = (
                round(total_tokens / total_sessions, 1) if total_sessions > 0 else 0.0
            )
            avg_input_tokens_per_session = (
                round(total_prompt_tokens / total_sessions, 1)
                if total_sessions > 0
                else 0.0
            )
            avg_output_tokens_per_session = (
                round(total_completion_tokens / total_sessions, 1)
                if total_sessions > 0
                else 0.0
            )
            avg_tokens_per_message = (
                round(total_tokens / total_messages, 1) if total_messages > 0 else 0.0
            )

            # Cost metrics (2 decimals, USD).
            cost_row = conn.execute(
                with_time(load_query("metrics/overview/cost_totals.sql"), clause),
                params,
            ).fetchone()
            total_cost = round(float(cost_row["total"] or 0.0), 2)
            total_cost_input = round(float(cost_row["cin"] or 0.0), 2)
            total_cost_output = round(float(cost_row["cout"] or 0.0), 2)
            avg_cost_per_session = (
                round(total_cost / total_sessions, 2) if total_sessions > 0 else 0.0
            )
            avg_cost_input_per_session = (
                round(total_cost_input / total_sessions, 2)
                if total_sessions > 0
                else 0.0
            )
            avg_cost_output_per_session = (
                round(total_cost_output / total_sessions, 2)
                if total_sessions > 0
                else 0.0
            )
            avg_cost_per_message = (
                round(total_cost / total_messages, 2) if total_messages > 0 else 0.0
            )

            avg_cost_per_provider_model = _fetch_one(
                conn,
                "metrics/overview/spend_avg_cost.sql",
                spend_clause,
                spend_params,
            )
            if avg_cost_per_provider_model is not None:
                avg_cost_per_provider_model = round(
                    float(avg_cost_per_provider_model), 2
                )

            # Time metrics (seconds, 2 decimals).
            total_time = round(
                float(
                    _fetch_one(conn, "metrics/overview/time_total.sql", clause, params)
                    or 0.0
                ),
                2,
            )
            avg_time_per_turn = round(
                float(
                    _fetch_one(
                        conn, "metrics/overview/time_per_turn.sql", clause, params
                    )
                    or 0.0
                ),
                2,
            )
            avg_time_per_session = (
                round(total_time / total_sessions, 2) if total_sessions > 0 else 0.0
            )

            # Average turn latency, read directly from the turn_latency table.
            avg_agent_latency = round(
                float(
                    _fetch_one(
                        conn, "metrics/overview/avg_latency.sql", clause, params
                    )
                    or 0.0
                ),
                2,
            )

            # Failure rates (based on messages with status='error').
            failed_turns_count = (
                _fetch_one(conn, "metrics/overview/failed_turns.sql", clause, params)
                or 0
            )
            total_turns_count = (
                _fetch_one(conn, "metrics/overview/total_turns.sql", clause, params)
                or 0
            )
            failed_sessions_count = (
                _fetch_one(
                    conn, "metrics/overview/failed_sessions.sql", clause, params
                )
                or 0
            )

            failure_rate_general = (
                round((failed_turns_count / total_messages * 100), 2)
                if total_messages > 0
                else 0.0
            )
            failure_rate_turns = (
                round((failed_turns_count / total_turns_count * 100), 2)
                if total_turns_count > 0
                else 0.0
            )
            failure_rate_sessions = (
                round((failed_sessions_count / total_sessions * 100), 2)
                if total_sessions > 0
                else 0.0
            )

            # Sessions by day.
            by_day_sql = with_time(
                load_query("metrics/overview/sessions_by_day.sql"), clause
            )
            day_rows = conn.execute(by_day_sql, params).fetchall()
            sessions_by_day = [
                {"date": row["day"], "count": row["cnt"]} for row in day_rows
            ]

            return validate_response(
                make_success_response(
                    message="Overview obtenida",
                    data={
                        "total_sessions": total_sessions,
                        "total_messages": total_messages,
                        "avg_messages_per_session": avg_messages,
                        "total_errors": failed_turns_count,
                        "failed_turns_count": failed_turns_count,
                        "total_turns_count": total_turns_count,
                        "failed_sessions_count": failed_sessions_count,
                        "failure_rate_general": failure_rate_general,
                        "failure_rate_turns": failure_rate_turns,
                        "failure_rate_sessions": failure_rate_sessions,
                        "top_tools": top_tools,
                        "sessions_by_day": sessions_by_day,
                        "total_tokens": total_tokens,
                        "avg_tokens_per_session": avg_tokens_per_session,
                        "avg_input_tokens_per_session": avg_input_tokens_per_session,
                        "avg_output_tokens_per_session": avg_output_tokens_per_session,
                        "avg_tokens_per_message": avg_tokens_per_message,
                        "total_cost": total_cost,
                        "avg_cost_per_session": avg_cost_per_session,
                        "avg_cost_input_per_session": avg_cost_input_per_session,
                        "avg_cost_output_per_session": avg_cost_output_per_session,
                        "avg_cost_per_message": avg_cost_per_message,
                        "avg_cost_per_provider_model": avg_cost_per_provider_model,
                        "total_time": total_time,
                        "avg_time_per_turn": avg_time_per_turn,
                        "avg_time_per_session": avg_time_per_session,
                        "avg_agent_latency": avg_agent_latency,
                    },
                    usage=zero_usage(),
                )
            )
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics/overview.py:get_metrics_overview")
        return make_error_response(message="Error fetching metrics overview")
