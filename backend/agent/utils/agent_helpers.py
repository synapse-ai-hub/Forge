"""Helpers for AgentInfo endpoints.

Reuses existing functions from permissions, skill_loader, tools, and mcp_helper.
Each helper returns structured data (list of dicts) for the frontend.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from backend.agent.utils.config_dir import get_skills_dir
from backend.agent.permissions import list_agents
from backend.agent.utils.skill_loader import _parse_frontmatter as parse_skill_frontmatter
from backend.agent.utils.mcp_helper import check_all_mcp_servers_health, is_mcp_tool
from backend.instances import agent

logger = logging.getLogger(__name__)

_HIDDEN_FROM_UI = frozenset({"query_model_capabilities", "skill"})
"""Native helpers never listed in the UI dropdowns (not for the user)."""


def get_skills_list() -> list[dict[str, str]]:
    """Scan skills directory and return structured list.

    For each subfolder containing a ``SKILL.md``, reads the frontmatter
    and returns ``{"name": <folder_name>, "description": <description>}``.

    Returns:
        List of skill dicts with ``name`` and ``description`` keys.
    """
    skills_dir = get_skills_dir()
    if not skills_dir.is_dir():
        return []

    result: list[dict[str, str]] = []
    for item in sorted(os.listdir(str(skills_dir))):
        skill_path = skills_dir / item
        if not skill_path.is_dir():
            continue

        skill_md = skill_path / "SKILL.md"
        if not skill_md.is_file():
            continue

        try:
            with open(str(skill_md), encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Error leyendo %s: %s", skill_md, e)
            continue

        fm = parse_skill_frontmatter(content)
        description = fm.get("description", "")
        if description:
            result.append({"name": item, "description": description})

    return result


def get_tools_list(include_mcp: bool = False) -> list[dict[str, Any]]:
    """Return all available tools from the agent's registry.

    Reads the already-built ``_tools_registry`` (native + external tools)
    **without** applying any permission filtering. MCP tools are excluded
    by default because they are managed separately via the MCP endpoint.
    Internal helpers (``_HIDDEN_FROM_UI``) are never listed: they are not
    for the user, the creator flows allow them via their own permissions.

    Args:
        include_mcp: When ``True``, MCP tools are listed too (the router
            panel needs them to pick which ones the router may use).

    Returns:
        List of tool dicts with ``name``, ``description`` and ``parameters`` (the JSON
        Schema of its arguments, as the router receives it) keys.
    """
    if agent is None or agent.tools is None:
        return []

    registry = getattr(agent.tools, "_tools_registry", [])
    result: list[dict[str, Any]] = []
    for entry in registry:
        func = entry.get("function", {})
        name = func.get("name", "")
        description = func.get("description", "")
        if name in _HIDDEN_FROM_UI:
            continue
        if name and (include_mcp or not is_mcp_tool(name)):
            result.append({
                "name": name,
                "description": description,
                "parameters": func.get("parameters") or {"type": "object", "properties": {}, "required": []},
            })
    return result


def get_agents_list() -> list[dict[str, Any]]:
    """Return list of sub-agents, excluding AGENT.md and ROUTER.md.

    Reuses ``list_agents()`` from permissions, which already reads the
    agents directory and parses frontmatter for name + description.

    Returns:
        List of agent dicts with ``name`` and ``description`` keys.
    """
    agents_result = list_agents()
    if agents_result.get("status") != "success":
        return []
    try:
        data = json.loads(agents_result.get("data", "[]"))
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Error parseando agentes: %s", e)
        return []
    return data


async def get_mcp_list() -> list[dict[str, str | int | None]]:
    """Check health of all configured MCP servers.

    Delegates to ``check_all_mcp_servers_health()`` which tests each
    server's connectivity and returns status (connected, failed, disabled).

    Returns:
        List of MCP server status dicts with ``label``, ``status``,
        and optionally ``error``.
    """
    return await check_all_mcp_servers_health(timeout=10.0)
