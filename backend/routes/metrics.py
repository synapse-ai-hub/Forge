"""Metrics endpoints for the agent.

Provides REST endpoints that aggregate usage data from the SQLite
``agent.db`` database to power the frontend metrics panel.
"""

from __future__ import annotations

import json
import logging
import math
import os
import sys
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

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
from backend.utils.db import get_connection
from backend.instances import session_manager
from fastapi import Body

logger = logging.getLogger(__name__)

router = APIRouter(tags=["metrics"])


def _time_filter_params(time_range: str, column_name: str = "created_at") -> tuple[str, tuple[Any, ...]]:
    """Return a parameterized SQL WHERE clause and tuple parameters for time filtering.

    Prevents SQL injection by using ? placeholders for parameters.
    """
    if time_range == "1h":
        return f" AND {column_name} >= datetime('now', ?)", ('-1 hour',)
    elif time_range == "6h":
        return f" AND {column_name} >= datetime('now', ?)", ('-6 hours',)
    elif time_range == "1d":
        return f" AND {column_name} >= datetime('now', ?)", ('-1 day',)
    elif time_range == "1w":
        return f" AND {column_name} >= datetime('now', ?)", ('-7 days',)
    elif time_range == "1m":
        return f" AND {column_name} >= datetime('now', ?)", ('-30 days',)
    return "", ()
def _sessions_bucket_expr(time_range: str) -> tuple[str, str]:
    """Return (select_expr, group_expr) for automatic time bucketing of sessions.

    Buckets adapt to the global range so the bar chart stays readable:
    1h -> 5-minute buckets, 6h -> 30-minute buckets, 1d -> hourly (24),
    1w -> daily last 7 days, 1m -> weekly, all -> monthly.
    """
    try:
        if time_range == "1h":
            expr = (
                "strftime('%Y-%m-%d %H:', created_at) || "
                "printf('%02d', CAST(CAST(strftime('%M', created_at) AS INTEGER) / 5 AS INTEGER) * 5)"
            )
            return expr, expr
        elif time_range == "6h":
            expr = (
                "strftime('%Y-%m-%d %H:', created_at) || "
                "printf('%02d', CAST(CAST(strftime('%M', created_at) AS INTEGER) / 30 AS INTEGER) * 30)"
            )
            return expr, expr
        elif time_range == "1d":
            expr = "strftime('%Y-%m-%d %H:00', created_at)"
            return expr, expr
        elif time_range == "1m":
            expr = "strftime('%Y-W%W', created_at)"
            return expr, expr
        elif time_range == "all":
            expr = "strftime('%Y-%m', created_at)"
            return expr, expr
        return "date(created_at)", "date(created_at)"
    except Exception:
        return "date(created_at)", "date(created_at)"


def _cantidad_bins(time_range: str) -> tuple[Any, Any, int]:
    """Return (start, end, bins) in UTC for the fixed 12-bar chart."""
    try:
        from datetime import datetime, timedelta, timezone as _tz

        now = datetime.now(_tz.utc)
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
        from datetime import datetime, timedelta, timezone as _tz

        now = datetime.now(_tz.utc)
        return now - timedelta(days=6), now + timedelta(days=1), 12


def _parse_ts(value: Any) -> Any | None:
    """Parse SQLite/ISO timestamps (with or without timezone) to aware datetime."""
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


def _bin_label(dt: Any, time_range: str) -> str:
    """Short label shown below the axis line."""
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
    """Bin raw session timestamps into exactly 12 equal bars (fixed width)."""
    try:
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
        return [{"date": r["bucket"], "count": r["cnt"]} for r in rows]


_METRICS_SQL_DIR = os.path.join(_project_root, "backend", "agent", "agent_db", "metrics")


def _load_metric_sql(name: str) -> str:
    """Load a metric SQL script from backend/agent/agent_db/metrics/.

    Raises FileNotFoundError if the script does not exist.
    """
    path = os.path.join(_METRICS_SQL_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _avg_agent_latency(conn, t_clause: str = "", t_params: tuple[Any, ...] = ()) -> float:
    """Return the average per-turn agent latency in seconds (2 decimals).

    Per-turn latency (tf - t0) is reconstructed as: the summed
    ``total_time`` of the turn's non-final assistant steps (sequential LLM
    calls) + per step the MAX ``total_time`` of its tool rows (tools in the
    same step run concurrently, so the slowest one sets the step wall time)
    + the final assistant row's ``time_to_first_token`` (the clock stops at
    the final answer's first chunk, so the final step's full total is NOT
    added). The average is taken over all (session, turn) groups.
    """
    try:
        rows = conn.execute(
            """
            SELECT AVG(lat) AS avg FROM (
                SELECT
                    COALESCE((
                        SELECT SUM(a.total_time) FROM messages a
                        WHERE a.role = 'assistant'
                            AND a.session_id = b.sid
                            AND a.turn_number = b.t
                            AND a.step < b.max_step
                    ), 0)
                    + COALESCE((
                        SELECT SUM(mx) FROM (
                            SELECT MAX(t2.total_time) AS mx FROM messages t2
                            WHERE t2.role = 'tool'
                                AND t2.session_id = b.sid
                                AND t2.turn_number = b.t
                            GROUP BY t2.step
                        )
                    ), 0)
                    + COALESCE((
                        SELECT m2.time_to_first_token FROM messages m2
                        WHERE m2.role = 'assistant'
                            AND m2.session_id = b.sid
                            AND m2.turn_number = b.t
                        ORDER BY m2.step DESC LIMIT 1
                    ), 0) AS lat
                FROM (
                    SELECT session_id AS sid, turn_number AS t, MAX(step) AS max_step
                    FROM messages
                    WHERE role = 'assistant'
                    """ + t_clause + """
                    GROUP BY session_id, turn_number
                ) AS b
            )
            """, t_params
        ).fetchall()
        return round(float(rows[0]["avg"] or 0.0), 2)
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics.py:_avg_agent_latency")
        return 0.0


def _latency_percentiles(conn, t_clause: str = "", t_params: tuple[Any, ...] = ()) -> tuple[float, float]:
    """Return (p95, p99) of agent per-turn latencies in seconds (2 decimals)."""
    try:
        rows = conn.execute(
            """
            SELECT
                COALESCE((
                    SELECT SUM(a.total_time) FROM messages a
                    WHERE a.role = 'assistant'
                        AND a.session_id = b.sid
                        AND a.turn_number = b.t
                        AND a.step < b.max_step
                ), 0)
                + COALESCE((
                    SELECT SUM(mx) FROM (
                        SELECT MAX(t2.total_time) AS mx FROM messages t2
                        WHERE t2.role = 'tool'
                            AND t2.session_id = b.sid
                            AND t2.turn_number = b.t
                        GROUP BY t2.step
                    )
                ), 0)
                + COALESCE((
                    SELECT m2.time_to_first_token FROM messages m2
                    WHERE m2.role = 'assistant'
                        AND m2.session_id = b.sid
                        AND m2.turn_number = b.t
                    ORDER BY m2.step DESC LIMIT 1
                ), 0) AS lat
            FROM (
                SELECT session_id AS sid, turn_number AS t, MAX(step) AS max_step
                FROM messages
                WHERE role = 'assistant'
                """ + t_clause + """
                GROUP BY session_id, turn_number
            ) AS b
            """, t_params
        ).fetchall()

        latencies = [float(r["lat"] or 0.0) for r in rows if r["lat"] is not None]
        if not latencies:
            return 0.0, 0.0

        latencies.sort()
        n = len(latencies)

        def percentile(p: float) -> float:
            k = (n - 1) * p
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return latencies[int(k)]
            d0 = latencies[int(f)] * (c - k)
            d1 = latencies[int(c)] * (k - f)
            return d0 + d1

        p95 = round(percentile(0.95), 2)
        p99 = round(percentile(0.99), 2)
        return p95, p99
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics.py:_latency_percentiles")
        return 0.0, 0.0


@router.get("/metrics/sessions")
async def get_session_metrics(time_range: str = "1m"):
    """Return session-level metrics aggregated from agent.db with time range filter."""
    try:
        valid_ranges = {"1h", "6h", "1d", "1w", "1m", "all"}
        if time_range not in valid_ranges:
            time_range = "1m"

        t_clause, t_params = _time_filter_params(time_range, "created_at")
        
        with get_connection() as conn:
            # Total sessions (excluding sub-agents, which have parent_id)
            total_rows = conn.execute(
                "SELECT COUNT(*) AS cnt FROM sessions WHERE parent_id IS NULL" + t_clause, t_params
            ).fetchall()
            total_sessions = total_rows[0]["cnt"] if total_rows else 0

            # Total messages
            msg_rows = conn.execute("SELECT COUNT(*) AS cnt FROM messages WHERE 1=1" + t_clause, t_params).fetchall()
            total_messages = msg_rows[0]["cnt"] if msg_rows else 0

            # Average messages per session
            avg_messages = 0.0
            if total_sessions > 0:
                avg_messages = round(total_messages / total_sessions, 1)

            # Token consumption metrics
            token_rows = conn.execute(
                "SELECT SUM(total_tokens) AS total, SUM(prompt_tokens) AS prompt, "
                "SUM(completion_tokens) AS completion FROM messages "
                "WHERE total_tokens IS NOT NULL" + t_clause, t_params
            ).fetchall()
            total_tokens = token_rows[0]["total"] or 0
            total_prompt_tokens = token_rows[0]["prompt"] or 0
            total_completion_tokens = token_rows[0]["completion"] or 0

            avg_tokens_per_session = 0.0
            avg_input_tokens_per_session = 0.0
            avg_output_tokens_per_session = 0.0
            if total_sessions > 0:
                avg_tokens_per_session = round(total_tokens / total_sessions, 1)
                avg_input_tokens_per_session = round(total_prompt_tokens / total_sessions, 1)
                avg_output_tokens_per_session = round(total_completion_tokens / total_sessions, 1)

            avg_tokens_per_message = 0.0
            if total_messages > 0:
                avg_tokens_per_message = round(total_tokens / total_messages, 1)

            # Average tokens per tool call
            tool_token_rows = conn.execute(
                "SELECT SUM(total_tokens) AS total FROM messages WHERE tool_name IS NOT NULL AND tool_name != '' AND total_tokens IS NOT NULL" + t_clause, t_params
            ).fetchall()
            total_tool_tokens = tool_token_rows[0]["total"] or 0
            tool_call_rows = conn.execute(
                "SELECT COUNT(*) AS cnt FROM messages WHERE tool_name IS NOT NULL AND tool_name != ''" + t_clause, t_params
            ).fetchall()
            total_tool_calls_for_avg = tool_call_rows[0]["cnt"] if tool_call_rows else 0
            avg_tokens_per_tool = 0.0
            if total_tool_calls_for_avg > 0:
                avg_tokens_per_tool = round(total_tool_tokens / total_tool_calls_for_avg, 1)

            # Cost metrics (from messages table — per call cost).
            # All money values use 2 decimals (USD).
            cost_rows = conn.execute(
                "SELECT SUM(cost_total) AS total, SUM(cost_input) AS cin, "
                "SUM(cost_output) AS cout FROM messages WHERE cost_total IS NOT NULL" + t_clause, t_params
            ).fetchall()
            total_cost = round(float(cost_rows[0]["total"] or 0.0), 2)
            total_cost_input = round(float(cost_rows[0]["cin"] or 0.0), 2)
            total_cost_output = round(float(cost_rows[0]["cout"] or 0.0), 2)

            avg_cost_per_session = 0.0
            avg_cost_input_per_session = 0.0
            avg_cost_output_per_session = 0.0
            if total_sessions > 0:
                avg_cost_per_session = round(total_cost / total_sessions, 2)
                avg_cost_input_per_session = round(total_cost_input / total_sessions, 2)
                avg_cost_output_per_session = round(total_cost_output / total_sessions, 2)

            avg_cost_per_message = 0.0
            if total_messages > 0:
                avg_cost_per_message = round(total_cost / total_messages, 2)

            # Average cost per tool call
            tool_cost_rows = conn.execute(
                "SELECT SUM(cost_total) AS total FROM messages WHERE tool_name IS NOT NULL AND tool_name != '' AND cost_total IS NOT NULL" + t_clause, t_params
            ).fetchall()
            total_tool_cost = tool_cost_rows[0]["total"] or 0.0
            avg_cost_per_tool = 0.0
            if total_tool_calls_for_avg > 0:
                avg_cost_per_tool = round(total_tool_cost / total_tool_calls_for_avg, 2)

            # Average cost per provider-model (from spend table — aggregated)
            spend_clause, spend_params = _time_filter_params(time_range, "updated_at")
            spend_avg_rows = conn.execute(
                "SELECT AVG(cost_total) AS avg FROM spend WHERE cost_total > 0" + spend_clause, spend_params
            ).fetchall()
            avg_cost_per_provider_model = spend_avg_rows[0]["avg"] or 0.0
            if avg_cost_per_provider_model is not None:
                avg_cost_per_provider_model = round(float(avg_cost_per_provider_model), 2)

            # Time metrics (seconds, 2 decimals). total_time is recorded on
            # assistant rows (LLM latency) and tool rows (execution time).
            time_rows = conn.execute(
                "SELECT SUM(total_time) AS total FROM messages WHERE total_time IS NOT NULL" + t_clause, t_params
            ).fetchall()
            total_time = round(float(time_rows[0]["total"] or 0.0), 2)

            # Average time per turn: mean of per-(session, turn) sums.
            turn_time_rows = conn.execute(
                """
                SELECT AVG(turn_total) AS avg FROM (
                    SELECT SUM(total_time) AS turn_total
                    FROM messages
                    WHERE total_time IS NOT NULL AND turn_number IS NOT NULL
                """ + t_clause + """
                    GROUP BY session_id, turn_number
                )
                """, t_params
            ).fetchall()
            avg_time_per_turn = turn_time_rows[0]["avg"] or 0.0
            avg_time_per_turn = round(float(avg_time_per_turn), 2)

            # Average time per session: total time over root sessions
            # (same methodology as avg_tokens_per_session).
            avg_time_per_session = 0.0
            if total_sessions > 0:
                avg_time_per_session = round(total_time / total_sessions, 2)

            # Average agent latency per turn (tf - t0 reconstruction).
            avg_agent_latency = _avg_agent_latency(conn, t_clause, t_params)

            # Sessions by day (legacy, daily buckets) + automatic buckets.
            day_rows = conn.execute(
                """
                SELECT
                    date(created_at) AS day,
                    COUNT(*) AS cnt
                FROM sessions
                WHERE parent_id IS NULL
                """ + t_clause + """
                GROUP BY date(created_at)
                ORDER BY day ASC
                """, t_params
            ).fetchall()
            sessions_by_day = [
                {"date": row["day"], "count": row["cnt"]} for row in day_rows
            ]

            bucket_select, bucket_group = _sessions_bucket_expr(time_range)
            bucket_rows = conn.execute(
                "SELECT " + bucket_select + " AS bucket, COUNT(*) AS cnt "
                "FROM sessions WHERE parent_id IS NULL" + t_clause + " "
                "GROUP BY " + bucket_group + " ORDER BY bucket ASC",
                t_params,
            ).fetchall()
            sessions_over_time = [
                {"date": row["bucket"], "count": row["cnt"]} for row in bucket_rows
            ]

            return validate_response(
                make_success_response(
                    message="Session metrics obtenidas",
                    data={
                        "total_sessions": total_sessions,
                        "total_messages": total_messages,
                        "avg_messages_per_session": avg_messages,
                        "total_tokens": total_tokens,
                        "avg_tokens_per_session": avg_tokens_per_session,
                        "avg_input_tokens_per_session": avg_input_tokens_per_session,
                        "avg_output_tokens_per_session": avg_output_tokens_per_session,
                        "avg_tokens_per_message": avg_tokens_per_message,
                        "avg_tokens_per_tool": avg_tokens_per_tool,
                        "total_cost": total_cost,
                        "avg_cost_per_session": avg_cost_per_session,
                        "avg_cost_input_per_session": avg_cost_input_per_session,
                        "avg_cost_output_per_session": avg_cost_output_per_session,
                        "avg_cost_per_message": avg_cost_per_message,
                        "avg_cost_per_tool": avg_cost_per_tool,
                        "avg_cost_per_provider_model": avg_cost_per_provider_model,
                        "total_time": total_time,
                        "avg_time_per_turn": avg_time_per_turn,
                        "avg_time_per_session": avg_time_per_session,
                        "avg_agent_latency": avg_agent_latency,
                        "sessions_by_day": sessions_by_day,
                        "sessions_over_time": sessions_over_time,
                    },
                    usage=zero_usage(),
                )
            )
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics.py:get_session_metrics")
        return make_error_response(message="Error fetching session metrics")


@router.get("/metrics/sessions/detail")
async def get_session_detail(time_range: str = "1m"):
    """Return per-session distributions for the Sesiones card from .sql scripts."""
    try:
        valid_ranges = {"1h", "6h", "1d", "1w", "1m", "all"}
        if time_range not in valid_ranges:
            time_range = "1m"

        ses_clause, ses_params = _time_filter_params(time_range, "sessions.created_at")
        ses_clause_plain = ses_clause.replace("sessions.created_at", "created_at")

        with get_connection() as conn:
            cantidad_sql = _load_metric_sql("sesiones/cantidad.sql")
            cantidad_sql = cantidad_sql.replace("{TIME_CLAUSE}", ses_clause_plain)
            cantidad_rows = conn.execute(cantidad_sql, ses_params).fetchall()
            cantidad = _fill_cantidad_buckets(time_range, cantidad_rows)

            mensajes_sql = _load_metric_sql("sesiones/total_mensajes.sql")
            mensajes_sql = mensajes_sql.replace("{TIME_CLAUSE_SES}", ses_clause)
            mensajes_rows = conn.execute(mensajes_sql, ses_params).fetchall()
            mensajes_per_session = [int(r["msg_count"]) for r in mensajes_rows if r["msg_count"] is not None]

            entrada_sql = _load_metric_sql("sesiones/tokens_entrada.sql")
            entrada_sql = entrada_sql.replace("{TIME_CLAUSE_SES}", ses_clause)
            entrada_rows = conn.execute(entrada_sql, ses_params).fetchall()
            tokens_entrada = [float(r["input_tokens"]) for r in entrada_rows if r["input_tokens"] is not None]

            salida_sql = _load_metric_sql("sesiones/tokens_salida.sql")
            salida_sql = salida_sql.replace("{TIME_CLAUSE_SES}", ses_clause)
            salida_rows = conn.execute(salida_sql, ses_params).fetchall()
            tokens_salida = [float(r["output_tokens"]) for r in salida_rows if r["output_tokens"] is not None]

            latencia_sesion_sql = _load_metric_sql("sesiones/latencia_promedio_sesion.sql")
            latencia_sesion_sql = latencia_sesion_sql.replace("{TIME_CLAUSE_SES}", ses_clause)
            latencia_sesion_rows = conn.execute(latencia_sesion_sql, ses_params).fetchall()
            latencia_per_session = [float(r["avg_lat"]) for r in latencia_sesion_rows if r["avg_lat"] is not None]

            return validate_response(
                make_success_response(
                    message="Detalle de sesiones obtenido",
                    data={
                        "cantidad": cantidad,
                        "mensajes_per_session": mensajes_per_session,
                        "tokens_entrada": tokens_entrada,
                        "tokens_salida": tokens_salida,
                        "latencia_per_session": latencia_per_session,
                    },
                    usage=zero_usage(),
                )
            )
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics.py:get_session_detail")
        return make_error_response(message="Error fetching session detail")


@router.post("/metrics/eda/outliers-image")
async def eda_outliers_image(payload: dict = Body(...)):
    """Render a metric query with synapse_tools.eda.outliers (base64, no files)."""
    try:
        from backend.utils.eda_figure import render_outliers_figure

        result = render_outliers_figure(
            query_file=str(payload.get("query_file", "")),
            value_column=str(payload.get("value_column", "")),
            time_range=str(payload.get("time_range", "1m")),
            placeholder=str(payload.get("placeholder", "{TIME_CLAUSE_SES}")),
            filter_column=str(
                payload.get("filter_column", "sessions.created_at")
            ),
            color=str(payload.get("color", "#8b5cf6")),
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
    """Return tool usage metrics aggregated from agent.db with time range filter."""
    try:
        valid_ranges = {"1h", "6h", "1d", "1w", "1m", "all"}
        if time_range not in valid_ranges:
            time_range = "1m"

        t_clause, t_params = _time_filter_params(time_range, "created_at")

        with get_connection() as conn:
            # Tool usage (from tool_calls JSON in messages)
            tool_rows = conn.execute(
                f"""
                SELECT tool_name, COUNT(*) AS cnt, AVG(total_time) AS avg_time
                FROM messages
                WHERE tool_name IS NOT NULL AND tool_name != '' {t_clause}
                GROUP BY tool_name
                ORDER BY cnt DESC
                """, t_params
            ).fetchall()
            tool_usage = [
                {
                    "name": row["tool_name"],
                    "count": row["cnt"],
                    "avg_time": round(float(row["avg_time"] or 0.0), 2),
                }
                for row in tool_rows
            ]

            total_tool_calls = sum(t["count"] for t in tool_usage)

            # Average execution time per tool call (seconds, 2 decimals).
            tool_time_rows = conn.execute(
                f"""
                SELECT AVG(total_time) AS avg FROM messages
                WHERE tool_name IS NOT NULL AND tool_name != ''
                    AND total_time IS NOT NULL {t_clause}
                """, t_params
            ).fetchall()
            avg_time_per_tool_call = tool_time_rows[0]["avg"] or 0.0
            avg_time_per_tool_call = round(float(avg_time_per_tool_call), 2)

            # Sub-agent delegations (tool_calls where name = "task")
            subagent_rows = conn.execute(
                f"""
                SELECT tool_name, COUNT(*) AS cnt
                FROM messages
                WHERE tool_name = 'task' {t_clause}
                GROUP BY tool_name
                """, t_params
            ).fetchall()
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
    """Return error metrics from the error_log table with time range filter."""
    try:
        valid_ranges = {"1h", "6h", "1d", "1w", "1m", "all"}
        if time_range not in valid_ranges:
            time_range = "1m"

        t_clause, t_params = _time_filter_params(time_range, "created_at")

        with get_connection() as conn:
            # Total errors (excluding provider key errors)
            total_rows = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM error_log WHERE exception NOT LIKE '%key%' AND exception NOT LIKE '%api_key%' {t_clause}", t_params
            ).fetchall()
            total_errors = total_rows[0]["cnt"] if total_rows else 0

            # Errors by day (last 30 days, excluding provider key errors)
            day_rows = conn.execute(
                f"""
                SELECT 
                    date(created_at) AS day,
                    COUNT(*) AS cnt
                FROM error_log
                WHERE 1=1 {t_clause}
                    AND exception NOT LIKE '%key%'
                    AND exception NOT LIKE '%api_key%'
                GROUP BY date(created_at)
                ORDER BY day ASC
                """, t_params
            ).fetchall()
            errors_by_day = [
                {"date": row["day"], "count": row["cnt"]} for row in day_rows
            ]

            # Errors by source (excluding provider key errors — missing API keys are not agent errors)
            source_rows = conn.execute(
                f"""
                SELECT source, COUNT(*) AS cnt
                FROM error_log
                WHERE source IS NOT NULL AND source != ''
                    AND source NOT LIKE '%provider_keys%'
                    AND exception NOT LIKE '%key%'
                    AND exception NOT LIKE '%api_key%' {t_clause}
                GROUP BY source
                ORDER BY cnt DESC
                LIMIT 10
                """, t_params
            ).fetchall()
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
    """Return LLM usage metrics grouped by model from agent.db with time range filter."""
    try:
        valid_ranges = {"1h", "6h", "1d", "1w", "1m", "all"}
        if time_range not in valid_ranges:
            time_range = "1m"

        t_clause, t_params = _time_filter_params(time_range, "created_at")

        with get_connection() as conn:
            model_rows = conn.execute(
                """
                SELECT model, COUNT(*) AS cnt
                FROM messages
                WHERE role = 'assistant'
                    AND model IS NOT NULL AND model != ''
                """ + t_clause + """
                GROUP BY model
                ORDER BY cnt DESC
                """, t_params
            ).fetchall()
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
        # Validate time_range parameter strictly against whitelist to ensure zero injection risk
        valid_ranges = {"1h", "6h", "1d", "1w", "1m", "all"}
        if time_range not in valid_ranges:
            time_range = "1m"

        t_clause, t_params = _time_filter_params(time_range, "created_at")

        with get_connection() as conn:
            # Session metrics with time range
            total_rows = conn.execute(
                "SELECT COUNT(*) AS cnt FROM sessions WHERE parent_id IS NULL" + t_clause, t_params
            ).fetchall()
            total_sessions = total_rows[0]["cnt"] if total_rows else 0

            msg_rows = conn.execute(
                "SELECT COUNT(*) AS cnt FROM messages WHERE 1=1" + t_clause, t_params
            ).fetchall()
            total_messages = msg_rows[0]["cnt"] if msg_rows else 0

            avg_messages = 0.0
            if total_sessions > 0:
                avg_messages = round(total_messages / total_sessions, 1)

            # Tool usage with time range
            tool_rows = conn.execute(
                """
                SELECT tool_name, COUNT(*) AS cnt
                FROM messages
                WHERE tool_name IS NOT NULL AND tool_name != ''
                """ + t_clause + """
                GROUP BY tool_name
                ORDER BY cnt DESC
                LIMIT 5
                """, t_params
            ).fetchall()
            top_tools = [
                {"name": row["tool_name"], "count": row["cnt"]} for row in tool_rows
            ]

            # Token consumption metrics with time range
            token_rows = conn.execute(
                "SELECT SUM(total_tokens) AS total, SUM(prompt_tokens) AS prompt, "
                "SUM(completion_tokens) AS completion FROM messages "
                "WHERE total_tokens IS NOT NULL" + t_clause, t_params
            ).fetchall()
            total_tokens = token_rows[0]["total"] or 0
            total_prompt_tokens = token_rows[0]["prompt"] or 0
            total_completion_tokens = token_rows[0]["completion"] or 0
            avg_tokens_per_session = round(total_tokens / total_sessions, 1) if total_sessions > 0 else 0.0
            avg_input_tokens_per_session = round(total_prompt_tokens / total_sessions, 1) if total_sessions > 0 else 0.0
            avg_output_tokens_per_session = round(total_completion_tokens / total_sessions, 1) if total_sessions > 0 else 0.0
            avg_tokens_per_message = round(total_tokens / total_messages, 1) if total_messages > 0 else 0.0

            # Cost metrics (2 decimals, USD).
            cost_rows = conn.execute(
                "SELECT SUM(cost_total) AS total, SUM(cost_input) AS cin, "
                "SUM(cost_output) AS cout FROM messages WHERE cost_total IS NOT NULL" + t_clause, t_params
            ).fetchall()
            total_cost = round(float(cost_rows[0]["total"] or 0.0), 2)
            total_cost_input = round(float(cost_rows[0]["cin"] or 0.0), 2)
            total_cost_output = round(float(cost_rows[0]["cout"] or 0.0), 2)
            avg_cost_per_session = round(total_cost / total_sessions, 2) if total_sessions > 0 else 0.0
            avg_cost_input_per_session = round(total_cost_input / total_sessions, 2) if total_sessions > 0 else 0.0
            avg_cost_output_per_session = round(total_cost_output / total_sessions, 2) if total_sessions > 0 else 0.0
            avg_cost_per_message = round(total_cost / total_messages, 2) if total_messages > 0 else 0.0

            # Average cost per provider-model (from spend table)
            spend_clause, spend_params = _time_filter_params(time_range, "updated_at")
            spend_avg_rows = conn.execute(
                "SELECT AVG(cost_total) AS avg FROM spend WHERE cost_total > 0" + spend_clause, spend_params
            ).fetchall()
            avg_cost_per_provider_model = spend_avg_rows[0]["avg"] or 0.0
            if avg_cost_per_provider_model is not None:
                avg_cost_per_provider_model = round(float(avg_cost_per_provider_model), 2)

            # Time metrics (seconds, 2 decimals).
            time_rows = conn.execute(
                "SELECT SUM(total_time) AS total FROM messages WHERE total_time IS NOT NULL" + t_clause, t_params
            ).fetchall()
            total_time = round(float(time_rows[0]["total"] or 0.0), 2)
            turn_time_rows = conn.execute(
                """
                SELECT AVG(turn_total) AS avg FROM (
                    SELECT SUM(total_time) AS turn_total
                    FROM messages
                    WHERE total_time IS NOT NULL AND turn_number IS NOT NULL
                """ + t_clause + """
                    GROUP BY session_id, turn_number
                )
                """, t_params
            ).fetchall()
            avg_time_per_turn = round(float(turn_time_rows[0]["avg"] or 0.0), 2)
            avg_time_per_session = round(total_time / total_sessions, 2) if total_sessions > 0 else 0.0

            # Average agent latency per turn (tf - t0 reconstruction).
            avg_agent_latency = _avg_agent_latency(conn, t_clause, t_params)

            # Failure rates (based on messages with status='error')
            err_msg_rows = conn.execute(
                "SELECT COUNT(*) AS cnt FROM messages WHERE status = 'error'" + t_clause, t_params
            ).fetchall()
            failed_turns_count = err_msg_rows[0]["cnt"] if err_msg_rows else 0

            total_turns_rows = conn.execute(
                "SELECT COUNT(DISTINCT session_id || '-' || turn_number) AS cnt FROM messages WHERE turn_number IS NOT NULL" + t_clause, t_params
            ).fetchall()
            total_turns_count = total_turns_rows[0]["cnt"] if total_turns_rows else 0

            failed_sessions_rows = conn.execute(
                "SELECT COUNT(DISTINCT session_id) AS cnt FROM messages WHERE status = 'error'" + t_clause, t_params
            ).fetchall()
            failed_sessions_count = failed_sessions_rows[0]["cnt"] if failed_sessions_rows else 0

            failure_rate_general = round((failed_turns_count / total_messages * 100), 2) if total_messages > 0 else 0.0
            failure_rate_turns = round((failed_turns_count / total_turns_count * 100), 2) if total_turns_count > 0 else 0.0
            failure_rate_sessions = round((failed_sessions_count / total_sessions * 100), 2) if total_sessions > 0 else 0.0

            # Sessions by day (filtered by time range)
            day_rows = conn.execute(
                """
                SELECT 
                    date(created_at) AS day,
                    COUNT(*) AS cnt
                FROM sessions 
                WHERE parent_id IS NULL
                """ + t_clause + """
                GROUP BY date(created_at)
                ORDER BY day ASC
                """, t_params
            ).fetchall()
            sessions_by_day = [
                {"date": row["day"], "count": row["cnt"]} for row in day_rows
            ]
            bucket_select, bucket_group = _sessions_bucket_expr(time_range)
            bucket_rows = conn.execute(
                "SELECT " + bucket_select + " AS bucket, COUNT(*) AS cnt "
                "FROM sessions WHERE parent_id IS NULL" + t_clause + " "
                "GROUP BY " + bucket_group + " ORDER BY bucket ASC",
                t_params,
            ).fetchall()
            sessions_over_time = [
                {"date": row["bucket"], "count": row["cnt"]} for row in bucket_rows
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
                    "sessions_over_time": sessions_over_time,
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
        print(f"DEBUG ERROR: {e}")
        log_error(str(e), source="backend/routes/metrics.py:get_metrics_overview")
        return make_error_response(message="Error fetching metrics overview")
