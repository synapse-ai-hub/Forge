"""Rate limit handling and provider-specific error parsing.

This module provides:
- Exception classes for rate limit errors
- Provider-specific adapters to parse rate limit responses
- User-friendly error messages for different rate limit scenarios
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Ensure the project root is in sys.path for absolute imports
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.utils.contract import make_error_response, zero_usage
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# User-friendly rate limit messages (Spanish)
RATE_LIMIT_MESSAGES = {
    # General rate limit exceeded
    "default": "Se alcanzó el límite de peticiones del proveedor. Probá de nuevo en un minuto o cambiá a otro modelo desde la configuración.",
    "429": "Se alcanzó el límite de peticiones del proveedor. Probá de nuevo en un minuto o cambiá a otro modelo desde la configuración.",
    # Request too large (context window exceeded)
    "413": "La solicitud es demasiado grande para el modelo seleccionado. Reducí el contexto o usá un modelo con mayor ventana de contexto.",
    # Tokens per minute exceeded
    "tpm": "Se alcanzó el límite de tokens por minuto del proveedor. Probá de nuevo en un momento.",
    # Provider-specific messages
    "openrouter": "Límite de uso de OpenRouter alcanzado. Revisá tu plan en openrouter.ai o cambiá de proveedor.",
    "google": "Límite de uso de Google AI alcanzado. Probá de nuevo más tarde o cambiá a otro modelo.",
    "openai": "Límite de uso de OpenAI alcanzado. Revisá tu quota en platform.openai.com.",
    # Budget exceeded (from spend handler)
    "budget": "Se alcanzó el límite de presupuesto configurado. No se pueden hacer más solicitudes a este proveedor hasta que se incremente el límite.",
    # Retry suggested
    "retry": "El proveedor está temporalmente sobrecargado. Reintentando automáticamente...",
}

# Rate limit error patterns for parsing error messages
_RATE_LIMIT_PATTERNS = [
    r"rate\s*limit",
    r"too\s*many\s*requests",
    r"request\s*too\s*large",
    r"tokens\s*per\s*min",
    r"\btpm\b",
    r"429\b",
    r"413\b",
    r"quota\s*exceeded",
    r"limit\s*exceeded",
    r"over\s*quota",
]

# HTTP status codes that indicate rate limiting
RATE_LIMIT_CODES = frozenset(["429", "413", "402"])  # 402 = Payment Required


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RateLimitInfo:
    """Structured information about a rate limit error.

    Attributes:
        error_type: The type of rate limit error (429, 413, budget, etc.).
        provider: The provider that returned the error.
        retry_after: Seconds to wait before retrying (if available).
        details: Additional error details from the response.
        user_message: A user-friendly message for display.
    """

    error_type: str
    provider: str | None
    retry_after: int | None
    details: str | None
    user_message: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "error_type": self.error_type,
            "provider": self.provider,
            "retry_after": self.retry_after,
            "details": self.details,
            "user_message": self.user_message,
        }


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class RateLimitError(Exception):
    """Exception raised when a rate limit is encountered.

    Attributes:
        error_type: The type of rate limit (429, 413, budget, etc.).
        provider: The provider that returned the error.
        retry_after: Seconds to wait before retrying.
        user_message: A user-friendly message.
    """

    def __init__(
        self,
        message: str,
        error_type: str = "429",
        provider: str | None = None,
        retry_after: int | None = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.provider = provider
        self.retry_after = retry_after
        self.user_message = get_rate_limit_message(error_type, provider)


# ---------------------------------------------------------------------------
# Provider-specific adapters
# ---------------------------------------------------------------------------

class RateLimitAdapter:
    """Base class for provider-specific rate limit parsing."""

    provider_name: str = ""

    @classmethod
    def parse(cls, response_body: str | dict | None, status_code: int = 429) -> RateLimitInfo | None:
        """Parse a rate limit response from the provider.

        Args:
            response_body: The response body (string or dict).
            status_code: The HTTP status code.

        Returns:
            A RateLimitInfo object if rate limit detected, None otherwise.
        """
        raise NotImplementedError

    @classmethod
    def get_error_type(cls, status_code: int, response_body: str | dict | None) -> str:
        """Determine the error type based on status code and response.

        Args:
            status_code: The HTTP status code.
            response_body: The response body.

        Returns:
            The error type string.
        """
        if status_code == 413:
            return "413"
        return "429"


class OpenRouterAdapter(RateLimitAdapter):
    """Rate limit adapter for OpenRouter API responses."""

    provider_name = "openrouter"

    @classmethod
    def parse(cls, response_body: str | dict | None, status_code: int = 429) -> RateLimitInfo | None:
        """Parse an OpenRouter rate limit response.

        OpenRouter error format:
        {"error": {"message": "...", "code": "rate_limit_exceeded", "type": "rate_limit_error"}}
        """
        try:
            if isinstance(response_body, str):
                data = json.loads(response_body)
            else:
                data = response_body or {}

            error = data.get("error", {})
            message = error.get("message", "") or str(data)
            code = error.get("code", "")
            error_type = error.get("type", "")

            # Check for rate limit indicators
            if any(p in message.lower() or p in code.lower() or p in error_type.lower()
                   for p in _RATE_LIMIT_PATTERNS):
                retry_after = error.get("retry_after") or cls._extract_retry_after(message)

                return RateLimitInfo(
                    error_type=cls.get_error_type(status_code, response_body),
                    provider=cls.provider_name,
                    retry_after=retry_after,
                    details=message,
                    user_message=get_rate_limit_message(status_code, cls.provider_name),
                )
        except (json.JSONDecodeError, TypeError):
            pass
        return None

    @staticmethod
    def _extract_retry_after(message: str) -> int | None:
        """Extract retry_after value from error message."""
        match = re.search(r"retry\s*after[:\s]*(\d+)", message, re.IGNORECASE)
        if match:
            return int(match.group(1))
        # OpenRouter sometimes uses seconds format
        match = re.search(r"(\d+)\s*second", message, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None


class GoogleAdapter(RateLimitAdapter):
    """Rate limit adapter for Google AI (Gemini) API responses."""

    provider_name = "google"

    @classmethod
    def parse(cls, response_body: str | dict | None, status_code: int = 429) -> RateLimitInfo | None:
        """Parse a Google AI rate limit response.

        Google error format:
        {"error": {"code": 429, "message": "...", "status": "RESOURCE_EXHAUSTED"}}
        """
        try:
            if isinstance(response_body, str):
                data = json.loads(response_body)
            else:
                data = response_body or {}

            error = data.get("error", {})
            message = error.get("message", "") or str(data)
            code = error.get("code", 0)
            status = error.get("status", "")

            # Check for rate limit indicators
            if (code == 429 or
                "RESOURCE_EXHAUSTED" in status or
                any(p in message.lower() for p in _RATE_LIMIT_PATTERNS)):
                retry_after = error.get("retryAfter") or cls._extract_retry_after(message)

                return RateLimitInfo(
                    error_type=cls.get_error_type(status_code, response_body),
                    provider=cls.provider_name,
                    retry_after=retry_after,
                    details=message,
                    user_message=get_rate_limit_message(status_code, cls.provider_name),
                )
        except (json.JSONDecodeError, TypeError):
            pass
        return None

    @staticmethod
    def _extract_retry_after(message: str) -> int | None:
        """Extract retry_after value from error message."""
        match = re.search(r"retry\s*after[:\s]*(\d+)", message, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None


class OpenAIAdapter(RateLimitAdapter):
    """Rate limit adapter for OpenAI API responses."""

    provider_name = "openai"

    @classmethod
    def parse(cls, response_body: str | dict | None, status_code: int = 429) -> RateLimitInfo | None:
        """Parse an OpenAI rate limit response.

        OpenAI error format:
        {"error": {"message": "...", "type": "rate_limit_error", "code": "rate_limit_exceeded"}}
        """
        try:
            if isinstance(response_body, str):
                data = json.loads(response_body)
            else:
                data = response_body or {}

            error = data.get("error", {})
            message = error.get("message", "") or str(data)
            code = error.get("code", "")
            error_type = error.get("type", "")

            # Check for rate limit indicators
            if any(p in message.lower() or p in code.lower() or p in error_type.lower()
                   for p in _RATE_LIMIT_PATTERNS):
                retry_after = error.get("retry_after") or cls._extract_retry_after(message)

                return RateLimitInfo(
                    error_type=cls.get_error_type(status_code, response_body),
                    provider=cls.provider_name,
                    retry_after=retry_after,
                    details=message,
                    user_message=get_rate_limit_message(status_code, cls.provider_name),
                )
        except (json.JSONDecodeError, TypeError):
            pass
        return None

    @staticmethod
    def _extract_retry_after(message: str) -> int | None:
        """Extract retry_after value from error message."""
        match = re.search(r"retry\s*after[:\s]*(\d+)", message, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------

# Map provider names to their adapter classes.
# Providers without a dedicated adapter use OpenAIAdapter when their
# api_type is "openai-compatible" (see get_adapter), else the base adapter.
_ADAPTERS: dict[str, type[RateLimitAdapter]] = {
    "openrouter": OpenRouterAdapter,
    "google": GoogleAdapter,
    "openai": OpenAIAdapter,
}


def get_adapter(provider: str) -> type[RateLimitAdapter]:
    """Get the rate limit adapter for a provider.

    Args:
        provider: Provider name (case-insensitive).

    Returns:
        The adapter class for the provider; OpenAI-compatible providers
        without a dedicated adapter use ``OpenAIAdapter``; anything else
        falls back to the base adapter.
    """
    adapter = _ADAPTERS.get(provider)
    if adapter is not None:
        return adapter
    try:
        from backend.agent.utils.model_catalog import get_provider_api_type

        if get_provider_api_type(provider) == "openai-compatible":
            return OpenAIAdapter
    except Exception:
        pass
    return RateLimitAdapter


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_rate_limit_error(
    response_body: str | dict | None,
    status_code: int,
    provider: str | None = None,
) -> RateLimitInfo | None:
    """Parse a rate limit error from an HTTP response.

    Tries the provider-specific adapter first if provider is known,
    then falls back to general pattern matching.

    Args:
        response_body: The response body (string or dict).
        status_code: The HTTP status code.
        provider: Optional provider name for targeted parsing.

    Returns:
        A RateLimitInfo object if rate limit detected, None otherwise.
    """
    # Try provider-specific adapter first
    if provider:
        adapter = get_adapter(provider)
        result = adapter.parse(response_body, status_code)
        if result:
            return result

    # Fall back to general pattern matching
    return _parse_generic(response_body, status_code)


def _parse_generic(response_body: str | dict | None, status_code: int) -> RateLimitInfo | None:
    """Parse rate limit error using generic patterns.

    Args:
        response_body: The response body.
        status_code: The HTTP status code.

    Returns:
        RateLimitInfo if detected, None otherwise.
    """
    try:
        if isinstance(response_body, str):
            data = json.loads(response_body)
        else:
            data = response_body or {}

        # Extract error message from various formats
        message = ""
        if isinstance(data, dict):
            error = data.get("error", {})
            if isinstance(error, dict):
                message = error.get("message", "") or str(error)
            else:
                message = str(error) if error else str(data)

        message_lower = message.lower()

        # Check for rate limit patterns
        if any(re.search(p, message_lower) for p in _RATE_LIMIT_PATTERNS):
            error_type = "413" if status_code == 413 else "429"
            retry_after = _extract_retry_after(message)

            return RateLimitInfo(
                error_type=error_type,
                provider=None,
                retry_after=retry_after,
                details=message,
                user_message=get_rate_limit_message(error_type, None),
            )

        # Also check status code
        if str(status_code) in RATE_LIMIT_CODES:
            return RateLimitInfo(
                error_type=str(status_code),
                provider=None,
                retry_after=None,
                details=message,
                user_message=get_rate_limit_message(str(status_code), None),
            )

    except (json.JSONDecodeError, TypeError, AttributeError) as e:
        logger.debug("Failed to parse generic rate limit: %s", e)

    return None


def _extract_retry_after(message: str) -> int | None:
    """Extract retry_after value from an error message."""
    patterns = [
        r"retry\s*after[:\s]*(\d+)",
        r"wait\s*(\d+)\s*second",
        r"in\s*(\d+)\s*second",
    ]
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def get_rate_limit_message(error_type: str, provider: str | None) -> str:
    """Get a user-friendly error message for a rate limit type.

    Args:
        error_type: The type of rate limit (429, 413, budget, etc.).
        provider: Optional provider name for provider-specific messages.

    Returns:
        A user-friendly error message in Spanish.
    """
    # Check for provider-specific message first
    if provider:
        provider_msg = RATE_LIMIT_MESSAGES.get(provider)
        if provider_msg:
            return provider_msg

    # Then check for error type specific message
    return RATE_LIMIT_MESSAGES.get(error_type, RATE_LIMIT_MESSAGES["default"])


def make_rate_limit_response(
    error_type: str,
    provider: str | None = None,
    retry_after: int | None = None,
) -> dict:
    """Create a standardized rate limit error response.

    Args:
        error_type: The type of rate limit (429, 413, budget, etc.).
        provider: Optional provider name.
        retry_after: Optional seconds to wait before retrying.

    Returns:
        A contract-compliant error response dictionary.
    """
    message = get_rate_limit_message(error_type, provider)

    # Log the rate limit error
    log_error(
        f"Rate limit: type={error_type}, provider={provider}, retry_after={retry_after}",
        source="rate_limit_handler.py:make_rate_limit_response",
    )

    return make_error_response(
        message=message,
        usage=zero_usage(),
    )


def is_rate_limit_error(exception: Exception) -> bool:
    """Check if an exception represents a rate limit error.

    Args:
        exception: The exception to check.

    Returns:
        True if the exception is a rate limit error, False otherwise.
    """
    if isinstance(exception, RateLimitError):
        return True

    # Check exception message for rate limit patterns
    message = str(exception).lower()
    if any(re.search(p, message) for p in _RATE_LIMIT_PATTERNS):
        return True

    # Check for rate limit status codes
    if any(re.search(rf"\b{code}\b", message) for code in RATE_LIMIT_CODES):
        return True

    return False


def classify_error_category(exception: Exception) -> str:
    """Classify an exception into a retry category.

    Categories:
        - "rate_limit": Rate limit errors (429, 413) - should retry
        - "budget": Budget/spend limit exceeded - should NOT retry
        - "transient": Temporary errors (timeouts, connection) - should retry
        - "fatal": Other errors - should NOT retry

    Args:
        exception: The exception to classify.

    Returns:
        The error category string.
    """
    if isinstance(exception, RateLimitError):
        if exception.error_type == "budget":
            return "budget"
        return "rate_limit"

    message = str(exception).lower()

    # Check for budget/spend limit patterns
    budget_patterns = ["budget", "spend limit", "presupuesto", "límite de gasto"]
    if any(p in message for p in budget_patterns):
        return "budget"

    # Check for rate limit patterns
    if any(re.search(p, message) for p in _RATE_LIMIT_PATTERNS):
        return "rate_limit"

    # Check for transient patterns
    transient_patterns = [
        "connection", "timeout", "overloaded",
        "temporarily unavailable", "service unavailable",
    ]
    if any(p in message for p in transient_patterns):
        return "transient"

    # Check for transient status codes
    transient_codes = ["500", "502", "503", "504"]
    if any(re.search(rf"\b{code}\b", message) for code in transient_codes):
        return "transient"

    return "fatal"


def get_retry_delay(
    error: RateLimitError | Exception,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
) -> float:
    """Calculate the retry delay for a rate limit error.

    Args:
        error: The rate limit error or exception.
        base_delay: Base delay in seconds.
        max_delay: Maximum delay in seconds.

    Returns:
        The calculated delay in seconds.
    """
    if isinstance(error, RateLimitError) and error.retry_after:
        return min(error.retry_after, max_delay)

    # Try to extract retry_after from exception message
    if isinstance(error, Exception):
        retry_after = _extract_retry_after(str(error))
        if retry_after:
            return min(retry_after, max_delay)

    return base_delay
