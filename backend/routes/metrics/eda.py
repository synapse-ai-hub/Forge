"""Lightweight distribution endpoints (no pandas/matplotlib)."""

from __future__ import annotations

from fastapi import APIRouter, Body

from backend.agent.utils.contract import (
    make_error_response,
    make_success_response,
    validate_response,
    zero_usage,
)
from backend.agent.utils.error_logger import log_error

router = APIRouter(tags=["metrics"])


@router.post("/metrics/eda/distribution")
async def eda_distribution(payload: dict = Body(...)) -> dict:
    """Return binned histogram + stats for a metric query (no image).

    Lightweight binned histogram: sqlite3 + stdlib only, frontend
    renders divs with the same style/colors.

    Args:
        payload: Request body with the query to run.

    Returns:
        JSON response with bins and stats.
    """
    try:
        from backend.agent.utils.eda_distribution import render_distribution

        raw_percentile = payload.get("percentile")
        percentile: float | None = None
        if raw_percentile is not None:
            try:
                candidate = float(raw_percentile)
                if 0 < candidate < 1:
                    percentile = candidate
            except (TypeError, ValueError):
                percentile = None

        model = payload.get("model")
        provider = payload.get("provider")
        model_clause = ""
        model_params: tuple = ()
        if model and provider:
            model_clause = " AND m.model = ? AND m.provider = ?"
            model_params = (str(model), str(provider))

        result = render_distribution(
            query_file=str(payload.get("query_file", "")),
            value_column=str(payload.get("value_column", "")),
            time_range=str(payload.get("time_range", "1m")),
            placeholder=str(payload.get("placeholder", "{TIME_CLAUSE}")),
            filter_column=str(
                payload.get("filter_column", "sessions.created_at")
            ),
            percentile=percentile,
            model_clause=model_clause,
            model_params=model_params,
        )
        return validate_response(
            make_success_response(
                message="Distribución generada",
                data={
                    "bins": result["bins"],
                    "stats": result["stats"],
                },
                usage=zero_usage(),
            )
        )
    except ValueError as e:
        return make_error_response(message=str(e))
    except Exception as e:
        log_error(str(e), source="backend/routes/metrics/eda.py:eda_distribution")
        return make_error_response(message="Error generando distribución")
