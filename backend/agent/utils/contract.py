"""Unified response contract for all tools, endpoints and the Agent.

Defines the unified JSON structure that every framework component must return
to guarantee consistency across the whole API.
"""

import json
from typing import Any, NotRequired, Optional, TypedDict


class UsageReport(TypedDict):
    """Token usage and execution time report.

    Attributes:
        prompt_tokens: Number of input (prompt) tokens.
        completion_tokens: Number of output (completion) tokens.
        total_tokens: Sum of prompt_tokens + completion_tokens.
        total_time: Total execution time in seconds.
    """

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    total_time: float


class ContractResponse(TypedDict):
    """Unified response structure for the whole API.

    Attributes:
        status: Whether the operation succeeded. ``"success"`` or ``"error"``.
        message: Human-readable description of the result.
        data: Any data associated with the response. ``None`` on error.
        tool_calls: List of tool calls requested by the LLM (optional).
        usage: Token usage and execution time report.
    """

    status: str  # "success" | "error"
    message: str
    data: Any
    tool_calls: NotRequired[Any]
    usage: UsageReport


def validate_response(response: dict) -> dict:
    """Validate that a dict conforms to the unified response contract.

    Checks the presence and correct types of the required keys
    (``status``, ``message``, ``data``). If the ``usage`` key is present,
    its internal structure is also validated.

    Args:
        response: The dict to validate.

    Returns:
        The same dict if validation succeeds.

    Raises:
        ValueError: If required keys are missing or have incorrect types.
        TypeError: If ``response`` is not a dict.
    """
    
    if not isinstance(response, dict):
        raise TypeError(f"Expected dict, got {type(response).__name__}")

    required_keys = ["status", "message", "data"]
    for key in required_keys:
        if key not in response:
            raise ValueError(f"Missing required key: '{key}'")

    if response["status"] not in ("success", "error"):
        raise ValueError(
            f"Invalid status '{response['status']}'. Must be 'success' or 'error'"
        )

    if not isinstance(response["message"], str):
        raise ValueError(
            f"Field 'message' must be a string, got {type(response['message']).__name__}"
        )

    if "usage" in response and response["usage"] is not None:
        usage = response["usage"]
        if not isinstance(usage, dict):
            raise ValueError(
                f"Field 'usage' must be a dict, got {type(usage).__name__}"
            )

        usage_required_keys = [
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "total_time",
        ]
        missing_usage = [k for k in usage_required_keys if k not in usage]
        if missing_usage:
            raise ValueError(
                f"Missing required keys in 'usage': {', '.join(missing_usage)}"
            )

        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if key in usage:
                value = usage[key]
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ValueError(
                        f"Field 'usage.{key}' must be an int, "
                        f"got {type(value).__name__}"
                    )

        if "total_time" in usage:
            value = usage["total_time"]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(
                    f"Field 'usage.total_time' must be a number, "
                    f"got {type(value).__name__}"
                )

    return response


def make_success_response(
    message: str, data: Any = None, usage: Optional[UsageReport] = None,
    tool_calls: Any = None,
) -> dict:
    """Create a success response with the unified contract.

    Args:
        message: Human-readable description of the successful result.
        data: Data associated with the response (optional, ``None`` by default).
        usage: Token usage and time report (optional).
        tool_calls: List of tool calls requested by the LLM (optional).

    Returns:
        A dict with the ``ContractResponse`` structure in ``"success"`` state.
    """
    response: dict = {
        "status": "success",
        "message": message,
        "data": data,
        "tool_calls": tool_calls,
        "usage": usage if usage is not None else zero_usage(),
    }
    return response


def make_error_response(message: str, usage: Optional[UsageReport] = None) -> dict:
    """Create an error response with the unified contract.

    Args:
        message: Human-readable description of the error.
        usage: Token usage and time report (optional).

    Returns:
        A dict with the ``ContractResponse`` structure in ``"error"`` state.
    """
    response: dict = {
        "status": "error",
       
        "tool_calls": None,
        "usage": usage if usage is not None else zero_usage(),
    }
    return response


def zero_usage() -> dict:
    """Return a usage report with all values set to zero.

    Returns:
        A dict with the ``UsageReport`` structure initialized to zero.
    """
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "total_time": 0.0,
    }


def parse_output_safe(output: Any) -> Any:
    """Parse LLM output, returning the parsed JSON value when it holds JSON,
    else the raw value.

    When the model is asked for structured output it may return a JSON
    document as a string; this helper converts it to a ``dict``/``list`` so
    callers can store structured data in the contract ``data`` field. Any
    non-JSON value (plain text, ``None``, already-structured objects) is
    returned unchanged, so text responses never break.

    Args:
        output: Raw LLM output (usually ``str``, but any type is accepted).

    Returns:
        The parsed JSON value when ``output`` is a JSON ``str``; otherwise
        ``output`` unchanged.
    """
    if not isinstance(output, str):
        return output
    try:
        return json.loads(output)
    except (json.JSONDecodeError, TypeError, ValueError):
        return output


if __name__ == '__main__':
    print('Contract module — define make_success_response, make_error_response, zero_usage.')
    u = zero_usage()
    print(f'  zero_usage(): {u}')
    s = make_success_response(message='OK', data={'test': 1}, usage=u)
    print(f'  make_success_response: status={s["status"]}')
    e = make_error_response(message='Error', usage=u)
    print(f'  make_error_response: status={e["status"]}')
