"""Agent loop package.

``AgentLoop`` lives in :mod:`backend.agent.loop.agent_loop`; the limits,
router tool schema and small helpers it uses live in their own modules.
The public names are re-exported here so ``from backend.agent.loop import
AgentLoop`` keeps working.
"""

from __future__ import annotations

from backend.agent.loop.agent_loop import AgentLoop
from backend.agent.loop.constants import (
    LLM_BACKOFF_BASE_SECONDS,
    MAX_EMPTY_RESPONSE_RETRIES,
    MAX_ITERATIONS,
    MAX_LLM_RETRIES,
    MAX_SUBAGENT_DEPTH,
)
from backend.agent.loop.helpers import (
    _load_router_permissions,
    _read_param_override,
    _resolve_tool_api_type,
    _router_tool_permissions,
)
from backend.agent.loop.router_tools import _ROUTER_TOOLS

__all__ = [
    "AgentLoop",
    "LLM_BACKOFF_BASE_SECONDS",
    "MAX_EMPTY_RESPONSE_RETRIES",
    "MAX_ITERATIONS",
    "MAX_LLM_RETRIES",
    "MAX_SUBAGENT_DEPTH",
    "_ROUTER_TOOLS",
    "_load_router_permissions",
    "_read_param_override",
    "_resolve_tool_api_type",
    "_router_tool_permissions",
]
