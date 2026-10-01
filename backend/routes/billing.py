"""Billing endpoints for usage metrics and spend configuration.

Provides REST endpoints to query usage metrics aggregated by provider-model,
manage billing configuration (spend limits), and retrieve billing statistics.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from fastapi import APIRouter, Query

# ---------------------------------------------------------------------------
# Ensure the project root is in sys.path so absolute imports (backend.*)
# resolve correctly regardless of how the file is invoked.
# ---------------------------------------------------------------------------
import os
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
from backend.agent.utils.db import db_transaction
from backend.agent.utils.spend_handler import (
    get_all_spend,
    get_billing_stats,
    get_current_spend,
    get_spend_by_provider,
    get_spend_config,
    set_spend_limit,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["billing"])


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert a value to float.

    Args:
        value: The value to convert.
        default: Default value if conversion fails.

    Returns:
        The float value or the default.
    """
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def _get_all_spend_configs() -> list[dict[str, Any]]:
    """Get all spend limit configurations from the spend_limits table.

    Returns:
        List of spend config dicts with provider, model, limit_amount, etc.
    """
    try:
        with db_transaction() as conn:
            rows = conn.execute(
                """SELECT provider, model, limit_amount, created_at, updated_at
                   FROM spend_limits
                   ORDER BY provider, model"""
            ).fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        log_error(str(e), source="billing.py:_get_all_spend_configs")
        return []


def _get_all_provider_stats() -> list[dict[str, Any]]:
    """Get billing statistics for all providers aggregated from spend table.

    Current month only (spend keeps one row per provider, model and
    month; history is never reset).

    Returns:
        List of billing stats dicts per provider.
    """
    try:
        from backend.agent.utils.spend_handler import current_month

        with db_transaction() as conn:
            rows = conn.execute(
                """SELECT provider,
                          SUM(requests) as requests,
                          SUM(prompt_tokens) as prompt_tokens,
                          SUM(completion_tokens) as completion_tokens,
                          SUM(total_tokens) as total_tokens,
                          SUM(cost_total) as cost
                   FROM spend
                   WHERE month = ?
                   GROUP BY provider
                   ORDER BY provider""",
                (current_month(),),
            ).fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        log_error(str(e), source="billing.py:_get_all_provider_stats")
        return []


@router.get("/usage-metrics")
async def get_usage_metrics(
    provider: str | None = Query(default=None, description="Filter by provider name"),
):
    """Return usage metrics aggregated by provider-model.

    Args:
        provider: Optional provider filter (e.g., 'openrouter', 'google').

    Returns:
        A contract response with ``data`` containing aggregated usage metrics.
    """
    try:
        # Get all billing stats or filter by provider
        if provider:
            stat = get_billing_stats(provider)
            stats = [stat] if stat and stat.get('provider') else []
        else:
            stats = _get_all_provider_stats()

        # Calculate totals
        total_requests = sum(s.get("requests", 0) for s in stats)
        total_prompt_tokens = sum(s.get("prompt_tokens", 0) for s in stats)
        total_completion_tokens = sum(s.get("completion_tokens", 0) for s in stats)
        total_tokens = sum(s.get("total_tokens", 0) for s in stats)
        total_cost = sum(_safe_float(s.get("cost")) for s in stats)

        # Format per-provider metrics
        by_provider = [
            {
                "provider": s.get("provider", ""),
                "requests": s.get("requests", 0),
                "prompt_tokens": s.get("prompt_tokens", 0),
                "completion_tokens": s.get("completion_tokens", 0),
                "total_tokens": s.get("total_tokens", 0),
                "cost": _safe_float(s.get("cost")),
            }
            for s in stats
        ]

        return validate_response(
            make_success_response(
                message="Usage metrics obtenidas",
                data={
                    "by_provider": by_provider,
                    "totals": {
                        "requests": total_requests,
                        "prompt_tokens": total_prompt_tokens,
                        "completion_tokens": total_completion_tokens,
                        "total_tokens": total_tokens,
                        "cost": total_cost,
                    },
                },
                usage=zero_usage(),
            )
        )
    except Exception as e:
        log_error(str(e), source="billing.py:get_usage_metrics")
        return validate_response(make_error_response(message="Error fetching usage metrics"))


@router.get("/billing-config")
async def get_billing_config(
    provider: str | None = Query(default=None, description="Filter by provider name"),
    model: str | None = Query(default=None, description="Filter by model name"),
):
    """Return the configured spend limits.

    Args:
        provider: Optional provider filter.
        model: Optional model filter.

    Returns:
        A contract response with ``data`` containing configured spend limits.
    """
    try:
        if provider:
            # Get specific config for provider/model
            config = get_spend_config(provider, model)
            configs = [config] if config else []
        else:
            # Get all configs
            configs = _get_all_spend_configs()

        return validate_response(
            make_success_response(
                message="Billing config obtenido",
                data={
                    "limits": configs,
                    "count": len(configs),
                },
                usage=zero_usage(),
            )
        )
    except Exception as e:
        log_error(str(e), source="billing.py:get_billing_config")
        return validate_response(make_error_response(message="Error fetching billing config"))


@router.post("/billing-config")
async def create_billing_config(
    provider: str = Query(..., description="Provider name (e.g., 'openrouter', 'google')"),
    model: str | None = Query(default=None, description="Model name (optional for provider-level limit)"),
    limit_amount: float = Query(..., ge=0, description="Spend limit amount in USD"),
):
    """Configure a spend limit for a provider or provider-model.

    Args:
        provider: Provider name (required).
        model: Optional model identifier for model-specific limit.
        limit_amount: Spend limit in USD. Use 0 to remove/disable the limit.

    Returns:
        A contract response confirming the spend limit configuration.
    """
    try:
        success = set_spend_limit(provider, model, limit_amount)

        if success:
            return validate_response(
                make_success_response(
                    message=f"Spend limit configurado: {provider}" +
                            (f"/{model}" if model else "") +
                            f" = ${limit_amount}",
                    data={
                        "provider": provider,
                        "model": model,
                        "limit_amount": limit_amount,
                    },
                    usage=zero_usage(),
                )
            )
        else:
            return validate_response(make_error_response(message="Error configuring spend limit"))

    except Exception as e:
        log_error(str(e), source="billing.py:create_billing_config")
        return validate_response(make_error_response(message="Error configuring spend limit"))


@router.get("/billing-stats")
async def get_billing_statistics(
    provider: str | None = Query(default=None, description="Filter by provider name"),
):
    """Return general billing statistics with totals by provider.

    Args:
        provider: Optional provider filter.

    Returns:
        A contract response with ``data`` containing billing statistics.
    """
    try:
        if provider:
            # Get stats for specific provider
            stat = get_billing_stats(provider)
            stats = [stat] if stat and stat.get('provider') else []
        else:
            # Get stats for all providers
            stats = _get_all_provider_stats()

        # Calculate grand totals
        total_requests = sum(s.get("requests", 0) for s in stats)
        total_prompt_tokens = sum(s.get("prompt_tokens", 0) for s in stats)
        total_completion_tokens = sum(s.get("completion_tokens", 0) for s in stats)
        total_tokens = sum(s.get("total_tokens", 0) for s in stats)
        total_cost = sum(_safe_float(s.get("cost")) for s in stats)

        # Format provider stats with current spend info
        by_provider = []
        for s in stats:
            prov = s.get("provider", "")
            spend = get_current_spend(prov) if prov else 0.0
            by_provider.append({
                "provider": prov,
                "requests": s.get("requests", 0),
                "prompt_tokens": s.get("prompt_tokens", 0),
                "completion_tokens": s.get("completion_tokens", 0),
                "total_tokens": s.get("total_tokens", 0),
                "cost": _safe_float(s.get("cost")),
                "current_spend": spend,
            })

        return validate_response(
            make_success_response(
                message="Billing stats obtenidas",
                data={
                    "by_provider": by_provider,
                    "totals": {
                        "requests": total_requests,
                        "prompt_tokens": total_prompt_tokens,
                        "completion_tokens": total_completion_tokens,
                        "total_tokens": total_tokens,
                        "cost": total_cost,
                    },
                },
                usage=zero_usage(),
            )
        )
    except Exception as e:
        log_error(str(e), source="billing.py:get_billing_statistics")
        return validate_response(make_error_response(message="Error fetching billing statistics"))


@router.get("/spend")
async def get_spend(
    provider: str | None = Query(default=None, description="Filter by provider name"),
):
    """Return per-model spend records.

    Args:
        provider: Optional provider filter.

    Returns:
        A contract response with ``data`` containing per-model spend records
        (tokens and cost breakdowns) for every provider-model combination.
    """
    try:
        if provider:
            spend = get_spend_by_provider(provider)
        else:
            spend = get_all_spend()

        return validate_response(
            make_success_response(
                message="Spend obtenido",
                data={
                    "spend": spend,
                    "count": len(spend),
                },
                usage=zero_usage(),
            )
        )
    except Exception as e:
        log_error(str(e), source="billing.py:get_spend")
        return validate_response(make_error_response(message="Error fetching spend"))
