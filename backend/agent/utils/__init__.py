"""Utility modules for the backend.

This package contains utility handlers for:
- spend_handler: Budget limit checking and spend tracking
- rate_limit_handler: Rate limit parsing and provider-specific adapters
"""

from backend.agent.utils.spend_handler import (
    check_spend_limit,
    record_spend,
    calculate_cost,
    get_spend_config,
    set_spend_limit,
)

from backend.agent.utils.rate_limit_handler import (
    RateLimitError,
    parse_rate_limit_error,
    get_rate_limit_message,
    RATE_LIMIT_MESSAGES,
)

__all__ = [
    # spend_handler
    "check_spend_limit",
    "record_spend",
    "calculate_cost",
    "get_spend_config",
    "set_spend_limit",
    # rate_limit_handler
    "RateLimitError",
    "parse_rate_limit_error",
    "get_rate_limit_message",
    "RATE_LIMIT_MESSAGES",
]
