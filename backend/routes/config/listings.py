"""Read-only listings for the settings panel: skills, tools, agents and MCP servers."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.instances import agent
from backend.agent.utils.config_dir import mcp_config_error
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.agent_helpers import (
    get_skills_list,
    get_tools_list,
    get_agents_list,
    get_mcp_list,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# AgentInfo endpoints
# ---------------------------------------------------------------------------


@router.get("/skills")
async def list_skills() -> JSONResponse:
    """List available skills (name + description)."""
    try:
        skills = get_skills_list()
        return JSONResponse(
            status_code=200,
            content={"status": "success", "skills": skills},
        )
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py:list_skills")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Error listing skills", "skills": []},
        )

@router.get("/tools")
async def list_tools() -> JSONResponse:
    """List all available tools (native + external) without permission filtering."""
    try:
        tools = get_tools_list()
        return JSONResponse(
            status_code=200,
            content={"status": "success", "tools": tools},
        )
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py:list_tools")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Error listing tools", "tools": []},
        )

@router.post("/tools/refresh")
async def refresh() -> JSONResponse:
    """Full refresh: re-scan external tools, rebuild registry (including MCP).

    Triggered by the ``Actualizar`` button in the agent panel.
    """
    try:
        agent.tools._external_tools = agent.tools._scan_external_tools()
        agent.tools._tools_registry = agent.tools._build_tools_registry()
        tools = get_tools_list()
        return JSONResponse(
            status_code=200,
            content={"status": "success", "tools": tools, "message": "Tools registry refreshed"},
        )
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py:refresh")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Error refreshing tools", "tools": []},
        )

@router.get("/agents")
async def list_agents() -> JSONResponse:
    """List available sub-agents (excluding AGENT.md and ROUTER.md)."""
    try:
        agents = get_agents_list()
        return JSONResponse(
            status_code=200,
            content={"status": "success", "agents": agents},
        )
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py:list_agents")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Error listing agents", "agents": []},
        )

@router.get("/mcp")
async def list_mcp_servers() -> JSONResponse:
    """List MCP servers with connection status.

    ``error`` is set when ``mcp.json`` is not a valid array (the list is then
    empty because of the file, not because nothing is configured).
    """
    try:
        servers = await get_mcp_list()
        return JSONResponse(
            status_code=200,
            content={"status": "success", "servers": servers, "error": mcp_config_error()},
        )
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config.py:list_mcp_servers")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Error checking MCP servers", "servers": []},
        )
