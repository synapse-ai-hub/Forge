"""Metrics endpoints for the agent.

Provides REST endpoints that aggregate usage data from the SQLite
``agent.db`` database to power the frontend metrics panel.

Every SQL statement lives as a .sql file under
``backend/agent/agent_db/queries/metrics/<section>/`` — nothing is
hardcoded here. Each endpoint maps 1:1 to its query folder.
"""

from __future__ import annotations

import csv
import io
import os
import sys
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Response

# ---------------------------------------------------------------------------
# Ensure the project root is in sys.path so absolute imports (backend.*)
# resolve correctly regardless of how the file is invoked.
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.utils.contract import (
    make_error_response,
    make_success_response,
    validate_response,
    zero_usage,
)
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.db import get_connection
from backend.agent.utils.queries import load_query, time_clause, with_time

router = APIRouter(tags=["metrics"])

_VALID_RANGES = {"1h", "6h", "1d", "1w", "1m", "all"}


def _normalize_range(time_range: str) -> str:
    """Return a whitelisted time range (default ``1m``).

    Args:
        time_range: Requested range ('1h', '6h', '1d', '1w', '1m', 'all').

    Returns:
        The range if valid, otherwise ``'1m'``.
    """
    return time_range if time_range in _VALID_RANGES else "1m"


def _parse_ts(value: Any) -> Any | None:
    """Parse SQLite/ISO timestamps (with or without timezone) to aware datetime.

    Args:
        value: Raw timestamp string coming from SQLite.

    Returns:
        Timezone-aware datetime, or None when unparseable.
    """
    try:
        if value is None:
            return None
        text = str(value).strip().replace("Z", "+00:00")
        if "T" not in text and " " in text and "+" not in text and text.count(":") >= 2:
            text = text.replace(" ", "T", 1) + "+00:00"
        from datetime import datetime as _dt

        dt = _dt.fromisoformat(text)
        if dt.tzinfo is None:
            from datetime import timezone as _tz

            dt = dt.replace(tzinfo=_tz.utc)
        return dt
    except Exception:
        return None


def _cantidad_bins(time_range: str) -> tuple[Any, Any, int]:
    """Return (start, end, bins) in UTC for the fixed 12-bar chart.

    Args:
        time_range: Whitelisted range string.

    Returns:
        Tuple of (range start, range end, number of bins).
    """
    try:
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        if time_range == "1h":
            base = now.replace(second=0, microsecond=0)
            base = base.replace(minute=(base.minute // 5) * 5)
            return base - timedelta(hours=1), base + timedelta(minutes=5), 12
        elif time_range == "6h":
            base = now.replace(second=0, microsecond=0)
            base = base.replace(minute=(base.minute // 30) * 30)
            return base - timedelta(hours=6), base + timedelta(minutes=30), 12
        elif time_range == "1d":
            base = now.replace(minute=0, second=0, microsecond=0)
            return base - timedelta(hours=22), base + timedelta(hours=2), 12
        elif time_range == "1w":
            base = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return base - timedelta(days=6), base + timedelta(days=1), 12
        elif time_range == "1m":
            base = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return base - timedelta(days=29), base + timedelta(days=1), 12
        base = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return base - timedelta(days=364), base + timedelta(days=1), 12
    except Exception:
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        return now - timedelta(days=6), now + timedelta(days=1), 12


def _bin_label(dt: Any, time_range: str) -> str:
    """Short label shown below the axis line.

    Args:
        dt: Datetime of the bin midpoint.
        time_range: Whitelisted range string.

    Returns:
        Formatted label for the range granularity.
    """
    try:
        if time_range in ("1h", "6h"):
            return dt.strftime("%H:%M")
        if time_range == "1d":
            return dt.strftime("%Hh")
        if time_range == "1w":
            return dt.strftime("%m-%d %Hh")
        if time_range == "1m":
            return dt.strftime("%m-%d")
        return dt.strftime("%Y-%m")
    except Exception:
        return ""


def _fill_cantidad_buckets(time_range: str, rows: list) -> list:
    """Bin raw session timestamps into exactly 12 equal bars (fixed width).

    Args:
        time_range: Whitelisted range string.
        rows: Rows from ``metrics/sessions/created_at_list.sql``.

    Returns:
        List of ``{"date": label, "count": n}`` dicts, one per bin.
    """
    try:
        from datetime import timedelta

        start, end, bins = _cantidad_bins(time_range)
        span = (end - start).total_seconds() or 1
        counts = [0] * bins
        labels = [""] * bins
        for i in range(bins):
            b_start = start + (end - start) * i / bins
            b_end = start + (end - start) * (i + 1) / bins
            mid = b_start + (b_end - b_start) / 2
            labels[i] = _bin_label(mid, time_range)
        for r in rows:
            ts = r["ts"] if isinstance(r, dict) else r[0]
            dt = _parse_ts(ts)
            if dt is None:
                continue
            if dt < start or dt >= end:
                continue
            idx = int((dt - start).total_seconds() / span * bins)
            idx = max(0, min(bins - 1, idx))
            counts[idx] += 1
        return [{"date": labels[i], "count": counts[i]} for i in range(bins)]
    except Exception:
        return [{"date": "", "count": 0} for _ in range(12)]


def _fetch_one(conn, path: str, clause: str, params: tuple) -> Any:
    """Execute a query file with the time clause and return its first cell.

    Args:
        conn: Open SQLite connection.
        path: Query path relative to ``agent_db/queries``.
        clause: Time filter clause (`` AND col >= datetime('now', ?)``).
        params: Parameters for the clause.

    Returns:
        The first column of the first row (None when no rows).
    """
    sql = with_time(load_query(path), clause)
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def _rows_to_csv_response(rows: list, name: str) -> Response:
    """Serialize fetched SQLite rows into a single-line-per-record CSV.

    Newline characters inside string cells (``\\r\\n``, ``\\r``, ``\\n``)
    are replaced by the literal two-character sequence ``\\n`` so every
    record occupies exactly one physical line in the file; the original
    breaks remain visible as text.

    Args:
        rows: Fetched rows (``sqlite3.Row``); the first row provides the
            header names.
        name: Base filename (without extension) for the attachment.

    Returns:
        A ``text/csv`` response with an attachment disposition header.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    if rows:
        header = list(rows[0].keys())
        writer.writerow(header)
        for row in rows:
            cells = []
            for key in header:
                cell = row[key]
                if isinstance(cell, str):
                    cell = (
                        cell.replace("\r\n", "\n")
                        .replace("\r", "\n")
                        .replace("\n", "\\n")
                    )
                cells.append(cell)
            writer.writerow(cells)
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
    )


@router.get("/metrics/sessions")
async def get_session_metrics(time_range: str = "1m"):
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
        log_error(str(e), source="backend/routes/metrics.py:get_session_metrics")
        return make_error_response(message="Error fetching session metrics")


@router.get("/metrics/sessions/export")
async def export_sessions_csv(time_range: str = "1m"):
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
        log_error(str(e), source="backend/routes/metrics.py:export_sessions_csv")
        return make_error_response(message="Error exporting sessions CSV")


@router.get("/metrics/messages")
async def get_message_metrics(time_range: str = "1m"):
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
        log_error(str(e), source="backend/routes/metrics.py:get_message_metrics")
        return make_error_response(message="Error fetching message metrics")


@router.get("/metrics/messages/export")
async def export_messages_csv(time_range: str = "1m"):
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
        log_error(str(e), source="backend/routes/metrics.py:export_messages_csv")
        return make_error_response(message="Error exporting messages CSV")


@router.post("/metrics/eda/outliers-image")
async def eda_outliers_image(payload: dict = Body(...)):
    """Render a metric query with synapse_tools.eda.outliers (base64, no files)."""
    try:
        from backend.agent.utils.eda_figure import render_outliers_figure

        raw_percentile = payload.get("percentile")
        percentile: float | None = None
        if raw_percentile is not None:
            try:
                candidate = float(raw_percentile)
                if 0 < candidate < 1:
                    percentile = candidate
            except (TypeError, ValueError):
                percentile = None

        result = render_outliers_figure(
            query_file=str(payload.get("query_file", "")),
            value_column=str(payload.get("value_column", "")),
            time_range=str(payload.get("time_range", "1m")),
            placeholder=str(payload.get("placeholder", "{TIME_CLAUSE}")),
            filter_column=str(
                payload.get("filter_column", "sessions.created_at")
            ),
            color=str(payload.get("color", "#8b5cf6")),
            percentile=percentile,
        )
        return validate_response(
            make_success_response(
                message="Figura generada",
                data={
                    "image": result["image_base64"],
                    "stats": result["stats"],
                },
                usage=zero_usage(),
            )
        )
    except ValueError as e:
        return make_error_response(message=str(e))
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics.py:eda_outliers_image")
        return make_error_response(message="Error generando figura")


@router.get("/metrics/tools")
async def get_tool_metrics(time_range: str = "1m"):
    """Return tool usage metrics aggregated from agent.db with time range filter.

    Args:
        time_range: Time filter ('1h', '6h', '1d', '1w', '1m', 'all').

    Returns:
        A contract response with tool usage, totals and sub-agent calls.
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
            {"name": row["tool_name"], "count": row["cnt"]} for row in subagent_rows
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
        log_error(str(e), source="backend/routes/metrics.py:get_tool_metrics")
        return make_error_response(message="Error fetching tool metrics")


@router.get("/metrics/errors")
async def get_error_metrics(time_range: str = "1m"):
    """Return error metrics from the error_log table with time range filter.

    Args:
        time_range: Time filter ('1h', '6h', '1d', '1w', '1m', 'all').

    Returns:
        A contract response with total errors and per-day/per-source series.
    """
    try:
        time_range = _normalize_range(time_range)
        clause, params = time_clause(time_range, "created_at")

        with get_connection() as conn:
            total_errors = (
                _fetch_one(conn, "metrics/errors/total_errors.sql", clause, params)
                or 0
            )

            by_day_sql = with_time(load_query("metrics/errors/by_day.sql"), clause)
            day_rows = conn.execute(by_day_sql, params).fetchall()
            errors_by_day = [
                {"date": row["day"], "count": row["cnt"]} for row in day_rows
            ]

            by_source_sql = with_time(
                load_query("metrics/errors/by_source.sql"), clause
            )
            source_rows = conn.execute(by_source_sql, params).fetchall()
        errors_by_source = [
            {"source": row["source"], "count": row["cnt"]} for row in source_rows
        ]

        return validate_response(
            make_success_response(
                message="Error metrics obtenidas",
                data={
                    "total_errors": total_errors,
                    "errors_by_day": errors_by_day,
                    "errors_by_source": errors_by_source,
                },
                usage=zero_usage(),
            )
        )
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics.py:get_error_metrics")
        return make_error_response(message="Error fetching error metrics")


@router.get("/metrics/models")
async def get_model_metrics(time_range: str = "1m"):
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
        models = [
            {"model": row["model"], "count": row["cnt"]} for row in model_rows
        ]
        total_model_calls = sum(m["count"] for m in models)

        return validate_response(
            make_success_response(
                message="Model metrics obtenidas",
                data={
                    "models": models,
                    "total_model_calls": total_model_calls,
                },
                usage=zero_usage(),
            )
        )
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics.py:get_model_metrics")
        return make_error_response(message="Error fetching model metrics")


@router.get("/metrics/overview")
async def get_metrics_overview(time_range: str = "1m"):
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
        log_error(str(e), source="backend/routes/metrics.py:get_metrics_overview")
        return make_error_response(message="Error fetching metrics overview")
