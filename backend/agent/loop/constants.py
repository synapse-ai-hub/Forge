"""Limits and endpoints used by the agent loop."""

from __future__ import annotations

import os

_CONFIG_BASE_URL = os.getenv("CONFIG_BASE_URL", "http://127.0.0.1:8000/api/config")

MAX_ITERATIONS = 25

"""Maximum tool-calling iterations before forcing a response (safety net)."""

MAX_SUBAGENT_DEPTH = 3

"""Maximum nesting depth for sub-agent delegation (recursion guard)."""

MAX_EMPTY_RESPONSE_RETRIES = 2

"""Maximum retries when the final LLM response is empty (no content, no tool_calls)."""

MAX_LLM_RETRIES = 5

"""Maximum retries for the LLM streaming call on rate-limit/transient errors.

The first attempt plus up to ``MAX_LLM_RETRIES`` retries, with exponential
back-off waits of 2s, 4s, 8s, 16s and 32s (62s total).
"""

LLM_BACKOFF_BASE_SECONDS = 2.0

"""Base delay (seconds) for the exponential back-off between LLM retries."""

BLOCKED_USER_TEXT = "Mensaje bloqueado por el guardrail de seguridad."

"""Text stored (and shown) in place of a user message the guardrail blocked."""
