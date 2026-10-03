"""Spend tracking and budget limit enforcement.

This module provides comprehensive functionality for tracking API spending and
enforcing configurable budget limits at both provider and model levels.

The module supports:
- Verifying spend limits before allowing API requests
- Recording detailed cost transactions with input/output cost breakdowns
- Calculating costs based on token usage and model catalog pricing
- Managing spend limit configurations per provider or model
- Retrieving spend statistics and billing reports

All database operations use the centralized db module to avoid code duplication.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

from backend.agent.utils.contract import (
    make_error_response,
    make_success_response,
    validate_response,
    zero_usage,
)
from backend.agent.utils.db import db_transaction, get_connection
from backend.agent.utils.queries import load_query
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)


def current_month() -> str:
    """Return the current month key (``YYYY-MM``).

    Spend is accumulated in one row per provider, model and month, so
    history is never reset and the tabs show the current month.

    Returns:
        The current month as ``"YYYY-MM"`` (Local time).
    """
    return datetime.now().strftime("%Y-%m")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_spend_limit(provider: str, model: str | None) -> tuple[bool, dict | None]:
    """Check if the current spend exceeds configured limits.

    Verifies spend against two possible limits:
    1. Model-specific limit (provider + model)
    2. Provider-level limit (provider only)

    Both limits are checked when applicable. If either is exceeded,
    the operation is blocked.

    Args:
        provider: The provider name (e.g., "openrouter", "google").
        model: Optional model identifier. If provided, both model and
            provider limits are checked.

    Returns:
        A tuple of (can_proceed, spend_info):
        - can_proceed: False if any limit is exceeded, True otherwise.
        - spend_info: Dict with current_spend, model_limit, provider_limit,
            or None if no limits are configured.
    """
    try:
        provider_value = provider.strip()
        model_value = model.strip() if model else None
        month_value = current_month()

        with get_connection() as conn:
            spend_info: dict[str, Any] = {
                "current_spend": 0.0,
                "model_limit": None,
                "provider_limit": None,
                "current_model_spend": 0.0,
                "current_provider_spend": 0.0,
            }

            # Check model-specific limit if model is provided
            if model_value:
                model_limit_row = conn.execute(
                    load_query("spend/get_model_limit.sql"),
                    (provider_value, model_value),
                ).fetchone()

                if model_limit_row:
                    spend_info["model_limit"] = float(model_limit_row["limit_amount"])
                    model_spend_row = conn.execute(
                        load_query("spend/get_model_spend.sql"),
                        (provider_value, model_value, month_value),
                    ).fetchone()
                    spend_info["current_model_spend"] = (
                        float(model_spend_row["cost_total"])
                        if model_spend_row and model_spend_row["cost_total"]
                        else 0.0
                    )

                    if spend_info["current_model_spend"] >= spend_info["model_limit"]:
                        spend_info["current_spend"] = spend_info["current_model_spend"]
                        return False, spend_info

            # Check provider-level limit
            provider_limit_row = conn.execute(
                load_query("spend/get_provider_limit.sql"),
                (provider_value,),
            ).fetchone()

            if provider_limit_row:
                spend_info["provider_limit"] = float(provider_limit_row["limit_amount"])
                provider_spend_row = conn.execute(
                    load_query("spend/get_provider_spend.sql"),
                    (provider_value, month_value),
                ).fetchone()
                spend_info["current_provider_spend"] = (
                    float(provider_spend_row["total_cost"])
                    if provider_spend_row and provider_spend_row["total_cost"]
                    else 0.0
                )

                if spend_info["current_provider_spend"] >= spend_info["provider_limit"]:
                    spend_info["current_spend"] = spend_info["current_provider_spend"]
                    return False, spend_info

            # Set current_spend based on model or provider
            if model_value:
                spend_info["current_spend"] = spend_info["current_model_spend"]
            else:
                spend_info["current_spend"] = spend_info["current_provider_spend"]

            # Return None if no limits configured
            if spend_info["model_limit"] is None and spend_info["provider_limit"] is None:
                return True, None

            return True, spend_info

    except sqlite3.Error as e:
        log_error(str(e), source="spend_handler.py:check_spend_limit")
        logger.warning("Spend limit check failed, allowing request: %s", e)
        return True, None


def record_spend(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_input: float,
    cost_output: float,
    requests: int = 1,
) -> bool:
    """Record a spend transaction to the spend table.

    Uses UPSERT logic to update the current month's row or insert it.
    One row per provider, model and month (``YYYY-MM``): history is never
    reset. Calculates total_tokens and cost_total automatically. Every
    call counts as ``requests`` (one LLM request per call), even when
    tokens are zero (failures, embeddings, transcription): zero-token
    calls add no tokens or cost but still count the request, creating
    the row with ``requests=1`` when it does not exist yet.

    Args:
        provider: The provider name (e.g., "openrouter", "google").
        model: The model identifier (e.g., "llama-3.1-8b-instant").
        prompt_tokens: Number of prompt tokens consumed in this transaction.
        completion_tokens: Number of completion tokens generated.
        cost_input: The cost for input tokens.
        cost_output: The cost for output tokens.
        requests: Number of LLM requests this transaction counts (default 1).

    Returns:
        True if the spend was recorded successfully, False otherwise.
    """
    try:
        provider_value = provider.strip()
        model_value = model.strip()
        month_value = current_month()
        cost_total = cost_input + cost_output
        total_tokens = prompt_tokens + completion_tokens
        now = datetime.now().isoformat()

        with db_transaction() as conn:
            cursor = conn.execute(
                load_query("spend/record_update.sql"),
                (
                    requests,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    cost_input,
                    cost_output,
                    cost_total,
                    now,
                    provider_value,
                    model_value,
                    month_value,
                ),
            )

            if cursor.rowcount == 0:
                conn.execute(
                    load_query("spend/record_insert.sql"),
                    (
                        provider_value,
                        model_value,
                        month_value,
                        requests,
                        prompt_tokens,
                        completion_tokens,
                        total_tokens,
                        cost_input,
                        cost_output,
                        cost_total,
                        now,
                    ),
                )

        logger.debug(
            "Recorded spend: provider=%s, model=%s, cost_input=%.6f, cost_output=%.6f, cost_total=%.6f",
            provider_value,
            model_value,
            cost_input,
            cost_output,
            cost_total,
        )
        return True

    except sqlite3.Error as e:
        log_error(str(e), source="spend_handler.py:record_spend")
        logger.error("Failed to record spend: %s", e)
        return False


def calculate_cost(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> tuple[float, float, float]:
    """Calculate the cost breakdown for a token usage based on model catalog pricing.

    Queries the model_catalog table to retrieve cost per token rates and computes
    the input cost, output cost, and total cost for the given token counts.
    Catalog rates come from models.dev and are USD per million tokens.

    Cost components:
        - cost_input: prompt_tokens * cost_input_rate / 1_000_000
        - cost_output: completion_tokens * cost_output_rate / 1_000_000
        - cost_total: cost_input + cost_output

    Args:
        provider: The provider name (e.g., "openrouter", "google").
        model: The model identifier (e.g., "llama-3.1-8b-instant").
        prompt_tokens: Number of prompt tokens consumed.
        completion_tokens: Number of completion tokens generated.

    Returns:
        A tuple of (cost_input, cost_output, cost_total):
        - cost_input: The calculated cost for input tokens.
        - cost_output: The calculated cost for output tokens.
        - cost_total: The sum of cost_input and cost_output.
        Returns (0.0, 0.0, 0.0) if the model is not found or on error.
    """
    try:
        provider_value = provider.strip()

        with get_connection() as conn:
            row = conn.execute(
                load_query("model_catalog/get_rates.sql"),
                (provider_value, model),
            ).fetchone()

            if row is None:
                logger.warning(
                    "Model not found for cost calculation: %s/%s",
                    provider_value,
                    model,
                )
                return 0.0, 0.0, 0.0

            cost_input_rate = float(row["cost_input"] or 0.0)
            cost_output_rate = float(row["cost_output"] or 0.0)

            calculated_cost_input = prompt_tokens * cost_input_rate / 1_000_000
            calculated_cost_output = completion_tokens * cost_output_rate / 1_000_000
            calculated_cost_total = calculated_cost_input + calculated_cost_output

            return (
                calculated_cost_input,
                calculated_cost_output,
                calculated_cost_total,
            )

    except (sqlite3.Error, ValueError, TypeError) as e:
        log_error(str(e), source="spend_handler.py:calculate_cost")
        logger.error("Failed to calculate cost: %s", e)
        return 0.0, 0.0, 0.0


def get_spend_config(provider: str, model: str | None) -> dict | None:
    """Retrieve the spend limit configuration for a provider/model combination.

    Queries the spend_limits table to retrieve the configured spending limit.
    When a model is specified, checks for a model-specific configuration first,
    then falls back to a provider-level configuration.

    Args:
        provider: The provider name (e.g., "openrouter", "google").
        model: Optional model identifier. If provided, looks for a model-specific
            configuration first.

    Returns:
        A dictionary containing the spend limit configuration with keys:
        - provider: The provider name.
        - model: The model identifier (or None for provider-level).
        - limit_amount: The configured spending limit in USD.
        - created_at: Timestamp when the limit was created.
        - updated_at: Timestamp when the limit was last updated.
        Returns None if no configuration is found.
    """
    try:
        provider_value = provider.strip()
        model_value = model.strip() if model else None

        with get_connection() as conn:
            if model_value:
                row = conn.execute(
                    load_query("spend/get_config_model.sql"),
                    (provider_value, model_value),
                ).fetchone()
                if row:
                    return dict(row)

            row = conn.execute(
                load_query("spend/get_config_provider.sql"),
                (provider_value,),
            ).fetchone()
            if row:
                return dict(row)

            return None

    except sqlite3.Error as e:
        log_error(str(e), source="spend_handler.py:get_spend_config")
        logger.error("Failed to get spend config: %s", e)
        return None


def set_spend_limit(
    provider: str,
    model: str | None,
    limit_amount: float,
) -> bool:
    """Set or update the spend limit for a provider/model combination.

    Creates a new spend limit configuration or updates an existing one.
    For model-specific limits, uses ON CONFLICT for upsert behavior.
    For provider-level limits (model is None), uses UPDATE + INSERT pattern.

    Args:
        provider: The provider name (e.g., "openrouter", "google").
        model: Optional model identifier. If None, sets a provider-level limit.
        limit_amount: The spending limit in USD. Setting to 0 effectively
            removes the limit (requests will always be allowed).

    Returns:
        True if the spend limit was set or updated successfully, False otherwise.
    """
    try:
        provider_value = provider.strip()
        model_value = model.strip() if model else None
        now = datetime.now().isoformat()

        with db_transaction() as conn:
            if model_value:
                conn.execute(
                    load_query("spend/upsert_limit_model.sql"),
                    (provider_value, model_value, limit_amount, now, now),
                )
            else:
                cursor = conn.execute(
                    load_query("spend/update_limit_provider.sql"),
                    (limit_amount, now, provider_value),
                )
                if cursor.rowcount == 0:
                    conn.execute(
                        load_query("spend/insert_limit_provider.sql"),
                        (provider_value, limit_amount, now, now),
                    )

        logger.info(
            "Set spend limit: provider=%s, model=%s, limit=%.2f",
            provider_value,
            model_value,
            limit_amount,
        )
        return True

    except sqlite3.Error as e:
        log_error(str(e), source="spend_handler.py:set_spend_limit")
        logger.error("Failed to set spend limit: %s", e)
        return False


def get_spend_by_provider(provider: str) -> list[dict]:
    """Retrieve all spend records for a provider.

    Queries the spend table to retrieve all model spend entries under
    the specified provider.

    Args:
        provider: The provider name (e.g., "openrouter", "google").

    Returns:
        A list of dictionaries containing spend data for each model:
        - provider: The provider name.
        - model: The model identifier.
        - requests: Total LLM requests counted.
        - prompt_tokens: Total prompt tokens consumed.
        - completion_tokens: Total completion tokens generated.
        - total_tokens: Total tokens (prompt + completion).
        - cost_input: Accumulated cost for input tokens.
        - cost_output: Accumulated cost for output tokens.
        - cost_total: Total accumulated cost.
        - cost_input_rate: Catalog input rate (USD per million tokens).
        - cost_output_rate: Catalog output rate (USD per million tokens).
        - updated_at: Timestamp of the last update.
        Returns an empty list if no records are found or on error.
    """
    try:
        provider_value = provider.strip()

        with get_connection() as conn:
            rows = conn.execute(
                load_query("spend/by_provider.sql"),
                (provider_value, current_month()),
            ).fetchall()

            return [
                {
                    "provider": row["provider"],
                    "model": row["model"],
                    "requests": row["requests"] or 0,
                    "prompt_tokens": row["prompt_tokens"] or 0,
                    "completion_tokens": row["completion_tokens"] or 0,
                    "total_tokens": row["total_tokens"] or 0,
                    "cost_input": float(row["cost_input"] or 0.0),
                    "cost_output": float(row["cost_output"] or 0.0),
                    "cost_total": float(row["cost_total"] or 0.0),
                    "cost_input_rate": (
                        float(row["cost_input_rate"])
                        if row["cost_input_rate"] is not None else None
                    ),
                    "cost_output_rate": (
                        float(row["cost_output_rate"])
                        if row["cost_output_rate"] is not None else None
                    ),
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ]

    except sqlite3.Error as e:
        log_error(str(e), source="spend_handler.py:get_spend_by_provider")
        logger.error("Failed to get spend by provider: %s", e)
        return []


def get_all_spend() -> list[dict]:
    """Retrieve all spend records across all providers.

    Queries the spend table to retrieve all accumulated spend data
    for every provider and model combination.

    Returns:
        A list of dictionaries containing spend data for each provider-model:
        - provider: The provider name.
        - model: The model identifier.
        - requests: Total LLM requests counted.
        - prompt_tokens: Total prompt tokens consumed.
        - completion_tokens: Total completion tokens generated.
        - total_tokens: Total tokens (prompt + completion).
        - cost_input: Accumulated cost for input tokens.
        - cost_output: Accumulated cost for output tokens.
        - cost_total: Total accumulated cost.
        - cost_input_rate: Catalog input rate (USD per million tokens).
        - cost_output_rate: Catalog output rate (USD per million tokens).
        - updated_at: Timestamp of the last update.
        Returns an empty list if no records are found or on error.
    """
    try:
        with get_connection() as conn:
            rows = conn.execute(
                load_query("spend/all_current_month.sql"),
                (current_month(),),
            ).fetchall()

            return [
                {
                    "provider": row["provider"],
                    "model": row["model"],
                    "requests": row["requests"] or 0,
                    "prompt_tokens": row["prompt_tokens"] or 0,
                    "completion_tokens": row["completion_tokens"] or 0,
                    "total_tokens": row["total_tokens"] or 0,
                    "cost_input": float(row["cost_input"] or 0.0),
                    "cost_output": float(row["cost_output"] or 0.0),
                    "cost_total": float(row["cost_total"] or 0.0),
                    "cost_input_rate": (
                        float(row["cost_input_rate"])
                        if row["cost_input_rate"] is not None else None
                    ),
                    "cost_output_rate": (
                        float(row["cost_output_rate"])
                        if row["cost_output_rate"] is not None else None
                    ),
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ]

    except sqlite3.Error as e:
        log_error(str(e), source="spend_handler.py:get_all_spend")
        logger.error("Failed to get all spend: %s", e)
        return []


def get_billing_stats(provider: str) -> dict | None:
    """Retrieve aggregated billing statistics for a provider.

    Aggregates the spend table to compute the request count and the token
    and cost totals for the given provider.

    Args:
        provider: The provider name (e.g., "openrouter", "google").

    Returns:
        A dict with ``provider``, ``requests``, ``prompt_tokens``,
        ``completion_tokens``, ``total_tokens`` and ``cost``, or None if the
        provider has no recorded spend.
    """
    try:
        provider_value = provider.strip()

        with get_connection() as conn:
            row = conn.execute(
                load_query("spend/billing_stats.sql"),
                (provider_value, current_month()),
            ).fetchone()

            if row is None or (row["requests"] or 0) == 0:
                return None

            return {
                "provider": provider_value,
                "requests": row["requests"] or 0,
                "prompt_tokens": row["prompt_tokens"] or 0,
                "completion_tokens": row["completion_tokens"] or 0,
                "total_tokens": row["total_tokens"] or 0,
                "cost": float(row["cost"] or 0.0),
            }

    except sqlite3.Error as e:
        log_error(str(e), source="spend_handler.py:get_billing_stats")
        logger.error("Failed to get billing stats: %s", e)
        return None


def get_current_spend(provider: str) -> float:
    """Retrieve the current accumulated spend for a provider.

    Args:
        provider: The provider name (e.g., "openrouter", "google").

    Returns:
        The total accumulated cost for the provider, or 0.0 if none.
    """
    try:
        provider_value = provider.strip()

        with get_connection() as conn:
            row = conn.execute(
                load_query("spend/current_total.sql"),
                (provider_value, current_month()),
            ).fetchone()
            return float(row["total"] or 0.0) if row else 0.0

    except sqlite3.Error as e:
        log_error(str(e), source="spend_handler.py:get_current_spend")
        logger.error("Failed to get current spend: %s", e)
        return 0.0


def record_external_usage(
    kind: str,
    provider: str,
    model: str,
    units: int = 1,
    duration: float | None = None,
    prompt_tokens: int = 0,
    session_id: str | None = None,
    turn_number: int | None = None,
    step: int | None = None,
) -> bool:
    """Record a non-LLM usage call (embeddings, transcription).

    The transcription API reports no token counts, so token columns stay
    at zero for it. The embedding API also returns no usage, but the
    caller counts tokens up front with the server-side ``count_tokens``
    and passes them as ``prompt_tokens``. The measured wall-clock
    ``duration`` (seconds) is always stored.

    Every call is contemplated twice: one detail row in ``external_usage``
    and one aggregated counter in ``spend`` (requests, tokens and cost),
    so the billing tabs include absolutely all model traffic.

    Args:
        kind: Usage kind (``"embedding"`` or ``"transcription"``).
        provider: The provider name (e.g., "google", "groq").
        model: The model identifier (e.g., "gemini-embedding-001").
        units: Processed units this call counts (default 1).
        duration: Measured wall-clock seconds for the call, if known.
        prompt_tokens: Input tokens counted up front (embeddings only).
        session_id: Optional session identifier if called within a chat turn.
        turn_number: Optional turn number if called within a chat turn.
        step: Optional step number if called within a chat turn.

    Returns:
        True if the usage was recorded successfully, False otherwise.
    """
    try:
        kind_value = (kind or "").strip().lower()
        provider_value = (provider or "").strip()
        model_value = (model or "").strip()
        units_value = units or 0
        prompt_value = int(prompt_tokens or 0)
        now = datetime.now().isoformat()

        if session_id is None or turn_number is None:
            try:
                from backend.agent.utils.error_logger import get_error_context
                ctx = get_error_context()
                if ctx:
                    if session_id is None:
                        session_id = ctx.get("session_id")
                    if turn_number is None:
                        turn_number = ctx.get("turn_number")
            except Exception:
                pass

        with db_transaction() as conn:
            conn.execute(
                load_query("spend/insert_external_usage.sql"),
                (kind_value, provider_value, model_value, units_value, prompt_value, duration, session_id, turn_number, step, now),
            )
        # Contemplate the call in spend too (one request plus the counted
        # input tokens and their cost; transcription reports no tokens so
        # it only adds the request). The processed units stay in the
        # external_usage detail row only. LOCAL providers are never
        # contemplated in spend (no cost).
        try:
            if provider_value != "LOCAL":
                cost_input, cost_output, _ = calculate_cost(
                    provider_value, model_value, prompt_value, 0
                )
                record_spend(provider_value, model_value, prompt_value, 0, cost_input, cost_output, requests=1)
        except Exception:
            pass
        return True

    except sqlite3.Error as e:
        log_error(str(e), source="spend_handler.py:record_external_usage")
        logger.error("Failed to record external usage: %s", e)
        return False


def record_creator_call(
    caller: str,
    provider: str | None,
    model: str | None,
    usage: dict | None,
) -> bool:
    """Record a direct LLM call made outside the chat loop.

    Creator flows (skill/tool/agent creators), the skills and tools
    evaluators and the agenda prompt crafter call ``llm_process`` /
    ``llm_streaming`` directly, so they never produce ``messages`` rows.
    Their usage is contemplated here instead, one row per call in the
    ``creator_calls`` table with the same token and cost breakdown as
    ``messages``. Failures are recorded with zero tokens so every call
    counts. Never raises.

    Args:
        caller: Caller identifier (e.g., ``"creator:skill:generate"``).
        provider: The provider name (e.g., ``"openai"``, ``"google"``).
        model: The model identifier.
        usage: The usage report dict (``prompt_tokens``,
            ``completion_tokens``, ``total_tokens``, ``total_time``).

    Returns:
        True if the call was recorded successfully, False otherwise.
    """
    try:
        caller_value = (caller or "unknown").strip()
        provider_value = (provider or "unknown").strip()
        model_value = (model or "unknown").strip()
        usage = usage or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or 0) or (prompt_tokens + completion_tokens)
        total_time = usage.get("total_time")
        cost_input, cost_output, cost_total = calculate_cost(
            provider_value, model_value, prompt_tokens, completion_tokens
        )
        now = datetime.now().isoformat()

        with db_transaction() as conn:
            conn.execute(
                load_query("spend/insert_creator_call.sql"),
                (
                    caller_value, provider_value, model_value, prompt_tokens,
                    completion_tokens, total_tokens, total_time, cost_input,
                    cost_output, cost_total, now,
                ),
            )
        # NOTE: spend is NOT touched here. Every creator/agenda call goes
        # through llm_process/llm_streaming, which already contemplate it
        # in spend via _record_spend (success and failure). Recording it
        # here too would double-count every request.
        return True

    except Exception as e:
        log_error(str(e), source="spend_handler.py:record_creator_call")
        logger.error("Failed to record creator call: %s", e)
        return False
