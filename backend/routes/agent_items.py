"""List and delete skills, tools, agents, MCP servers and RAG collections.

Endpoints:
- ``GET /api/knowledge`` — List vector collections.
- ``DELETE /api/skills/{name}`` — Delete a skill (whole directory).
- ``DELETE /api/tools/{name}`` — Delete an external tool (.py).
- ``DELETE /api/agents/{name}`` — Delete an agent (.md).
- ``DELETE /api/mcp/{label}`` — Delete an MCP server from the config.
- ``PUT /api/mcp/{label}/enabled`` — Switch an MCP server on or off in the config.
- ``DELETE /api/knowledge/{collection}`` — Delete a vector collection.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import inspect
import logging
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.utils.config_dir import (
    get_skills_dir,
    get_tools_dir,
    get_agents_dir,
    get_knowledge_dir,
    load_config,
    save_config,
    load_mcp_servers,
    save_mcp_servers,
)
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.mcp_helper import set_mcp_server_enabled
from backend.agent.utils.vector_db import VectorDB, get_vector_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(
    status: str,
    message: str,
    status_code: int = 200,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"status": status, "message": message},
    )


def _is_plain_name(name: str) -> bool:
    """Return True if name is a single path component.

    Rejects separators of both platforms, parent references and drive
    letters: on Windows Path(base) / absolute replaces the base, so a
    check for dot-dot and slash alone lets absolute paths through.
    """
    if not name or name in (".", ".."):
        return False
    if any(ch in name for ch in ("/", "\\", ":")):
        return False
    return ".." not in name and Path(name).name == name


def _rmtree(path: Path) -> bool:
    """Remove a directory tree."""
    try:
        shutil.rmtree(str(path))
        return True
    except OSError as e:
        log_error(str(e), source="agent_items.py:_rmtree")
        return False


def _unlink(path: Path) -> bool:
    """Remove a single file."""
    try:
        path.unlink()
        return True
    except OSError as e:
        log_error(str(e), source="agent_items.py:_unlink")
        return False


# ---------------------------------------------------------------------------
# GET /agent/knowledge  —  listar colecciones
# ---------------------------------------------------------------------------


@router.get("/knowledge")
async def list_knowledge_collections() -> JSONResponse:
    """List the available vector collections.

    Returns:
        A JSONResponse with ``{status, collections: string[]}``.
    """
    try:
        db = get_vector_db()
        from backend.agent.utils.rag_helpers import INTERNAL_COLLECTIONS

        cols = db.list_collections()
        names = [c["name"] for c in cols if c["name"] not in INTERNAL_COLLECTIONS]
        return JSONResponse(
            status_code=200,
            content={"status": "success", "collections": names},
        )
    except Exception as exc:
        log_error(str(exc), source="agent_items.py:list_knowledge_collections")
        logger.warning("Error listando colecciones: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Error listando colecciones", "collections": []},
        )


# ---------------------------------------------------------------------------
# DELETE /agent/skills/{name}
# ---------------------------------------------------------------------------


@router.delete("/skills/{name}")
async def delete_skill(name: str) -> JSONResponse:
    """Delete a skill by name.

    Looks up ``<skills_dir>/<name>/`` and removes it recursively.

    Returns:
        A JSONResponse with the operation result.
    """
    if not _is_plain_name(name):
        return _make_response("error", "Nombre de skill inválido.", 400)

    skill_dir = get_skills_dir() / name
    if not skill_dir.is_dir():
        return _make_response("error", f"Skill '{name}' no encontrada.", 404)

    logger.info("Eliminando skill: %s", skill_dir)
    ok = _rmtree(skill_dir)
    if not ok:
        return _make_response("error", f"No se pudo eliminar la skill '{name}'.", 500)

    return _make_response("success", f"Skill '{name}' eliminada.")


# ---------------------------------------------------------------------------
# DELETE /agent/tools/{name}
# ---------------------------------------------------------------------------


@router.delete("/tools/{name}")
async def delete_tool(name: str) -> JSONResponse:
    """Delete an external tool by name.

    Looks up ``<tools_dir>/<name>.py`` and removes it.

    Returns:
        A JSONResponse with the operation result.
    """
    if not _is_plain_name(name):
        return _make_response("error", "Nombre de tool inválido.", 400)

    # La tool puede estar como nombre sin extensión
    tool_path = get_tools_dir() / name
    if not tool_path.is_file():
        tool_path = get_tools_dir() / f"{name}.py"
    if not tool_path.is_file():
        return _make_response("error", f"Tool '{name}' no encontrada.", 404)

    logger.info("Eliminando tool externa: %s", tool_path)
    ok = _unlink(tool_path)
    if not ok:
        return _make_response("error", f"No se pudo eliminar la tool '{name}'.", 500)

    return _make_response("success", f"Tool externa '{name}' eliminada.")


# ---------------------------------------------------------------------------
# DELETE /agent/agents/{name}
# ---------------------------------------------------------------------------


@router.delete("/agents/{name}")
async def delete_agent(name: str) -> JSONResponse:
    """Delete an agent by name.

    Looks up ``<agents_dir>/<name>.md`` and removes it.

    Returns:
        A JSONResponse with the operation result.
    """
    if not _is_plain_name(name):
        return _make_response("error", "Nombre de agente inválido.", 400)

    agent_path = get_agents_dir() / f"{name}.md"
    if not agent_path.is_file():
        return _make_response("error", f"Agente '{name}' no encontrado.", 404)

    logger.info("Eliminando agente: %s", agent_path)
    ok = _unlink(agent_path)
    if not ok:
        return _make_response("error", f"No se pudo eliminar el agente '{name}'.", 500)

    return _make_response("success", f"Agente '{name}' eliminado.")


# ---------------------------------------------------------------------------
# DELETE /agent/mcp/{label}
# ---------------------------------------------------------------------------


@router.delete("/mcp/{label:path}")
async def delete_mcp_server(label: str) -> JSONResponse:
    """Delete an MCP server from mcp.json.

    Returns:
        A JSONResponse with the operation result.
    """
    if not label:
        return _make_response("error", "Label del servidor inválido.", 400)

    servers = load_mcp_servers()

    found = None
    for s in servers:
        if s.get("label") == label:
            found = s
            break

    if found is None:
        return _make_response("error", f"Servidor MCP '{label}' no encontrado.", 404)

    servers.remove(found)
    ok = save_mcp_servers(servers)
    if not ok:
        return _make_response("error", f"No se pudo guardar mcp.json al eliminar '{label}'.", 500)

    logger.info("Servidor MCP eliminado: %s", label)
    return _make_response("success", f"Servidor MCP '{label}' eliminado.")


# ---------------------------------------------------------------------------
# PUT /agent/mcp/{label}/enabled
# ---------------------------------------------------------------------------


@router.put("/mcp/{label:path}/enabled")
async def set_mcp_enabled(label: str, data: dict[str, Any] = Body(...)) -> JSONResponse:
    """Switch an MCP server on or off in mcp.json and rebuild the tools registry.

    The registry is rebuilt so a server turned off stops contributing tools
    (and one turned on starts) without waiting for the refresh button.

    Args:
        label: Server label.
        data: Body ``{"enabled": bool}``.

    Returns:
        A JSONResponse with the operation result.
    """
    enabled = data.get("enabled")
    if not label or not isinstance(enabled, bool):
        return _make_response("error", "Se requiere 'enabled' (true/false).", 400)

    saved = set_mcp_server_enabled(label, enabled)
    if saved is None:
        return _make_response("error", f"Servidor MCP '{label}' no encontrado.", 404)
    if not saved:
        return _make_response("error", f"No se pudo guardar mcp.json para '{label}'.", 500)

    try:
        from backend.instances import agent

        agent.tools._tools_registry = await asyncio.to_thread(
            agent.tools._build_tools_registry
        )
    except Exception as exc:
        log_error(str(exc), source="agent_items.py:set_mcp_enabled")
        return _make_response(
            "error", "mcp.json se actualizó pero falló la reconstrucción de tools.", 500
        )

    state = "activado" if enabled else "desactivado"
    logger.info("Servidor MCP %s: %s", state, label)
    return _make_response("success", f"Servidor MCP '{label}' {state}.")


# ---------------------------------------------------------------------------
# DELETE /agent/knowledge/{collection}
# ---------------------------------------------------------------------------


@router.delete("/knowledge/{collection}")
async def delete_knowledge_collection(collection: str) -> JSONResponse:
    """Delete a vector collection from the knowledge base.

    Looks up ``<knowledge_dir>/<collection>/`` and removes it recursively.

    Returns:
        A JSONResponse with the operation result.
    """
    if not _is_plain_name(collection):
        return _make_response("error", "Nombre de colección inválido.", 400)

    # Collections live inside Chroma (not as directories): delete them there.
    try:
        db = get_vector_db()
        if collection not in [c["name"] for c in db.list_collections()]:
            return _make_response("error", f"Colección '{collection}' no encontrada.", 404)
        logger.info("Eliminando colección vectorial: %s", collection)
        db.delete_collection(collection)
    except Exception as exc:
        log_error(str(exc), source="agent_items.py:delete_knowledge_collection")
        return _make_response(
            "error", f"No se pudo eliminar la colección '{collection}'.", 500
        )

    return _make_response("success", f"Colección '{collection}' eliminada.")


# ── Test endpoint ──────────────────────────────────────────────────────────


def _load_tool_module(tool_name: str) -> tuple[Any, str] | None:
    """Load a tool .py module from the tools directory.

    Args:
        tool_name: Name of the tool file (without .py).

    Returns:
        ``(module, handler_name)`` on success, ``None`` on failure.
    """
    tools_dir = get_tools_dir()
    tool_path = tools_dir / f"{tool_name}.py"
    try:
        if tool_path.resolve().parent != tools_dir.resolve():
            return None
    except OSError:
        return None
    if not tool_path.is_file():
        return None

    spec = importlib.util.spec_from_file_location(tool_name, str(tool_path))
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    _added = False
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
        _added = True
    try:
        spec.loader.exec_module(mod)
    finally:
        if _added:
            sys.path.remove(str(tools_dir))

    handler = getattr(mod, tool_name, None)
    if handler is None or not callable(handler):
        return None
    return mod, tool_name


@router.get("/tools/{tool_name}/schema")
async def get_tool_schema(tool_name: str) -> JSONResponse:
    """Return the function signature of a tool as a JSON schema.

    Extracts parameter names, types, descriptions and required flags from
    the handler function's signature and docstring.

    Args:
        tool_name: Tool file name (without .py extension).

    Returns:
        JSONResponse with ``{properties, required}`` or error.
    """
    if not _is_plain_name(tool_name):
        return _make_response("error", "Nombre de tool inválido.", 400)

    result = _load_tool_module(tool_name)
    if result is None:
        return _make_response("error", f"Tool '{tool_name}' no encontrada.", 404)

    mod, handler_name = result
    handler = getattr(mod, handler_name)
    sig = inspect.signature(handler)

    # Parse Google-style Args from docstring
    doc = (handler.__doc__ or "").strip()
    param_descs: dict[str, str] = {}
    lines = doc.split("\n")
    in_args = False
    for line in lines:
        stripped = line.strip()
        if stripped == "Args:":
            in_args = True
            continue
        if in_args:
            if stripped and not stripped.startswith(" ") and not stripped.startswith("\t"):
                if stripped.endswith(":"):
                    break
            m = re.match(r"^(\w+):\s*(.*)", stripped)
            if m:
                param_descs[m.group(1)] = m.group(2).strip()

    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }

    properties: dict[str, Any] = {}
    required: list[str] = []
    for pname, param in sig.parameters.items():
        if pname in ("self", "tools"):
            continue
        annotation = param.annotation
        type_str = "string"
        if annotation in type_map:
            type_str = type_map[annotation]
        elif hasattr(annotation, "__name__"):
            type_str = annotation.__name__

        prop: dict[str, Any] = {"type": type_str}
        if pname in param_descs:
            prop["description"] = param_descs[pname]
        if param.default is not inspect.Parameter.empty:
            prop["default"] = param.default
        else:
            required.append(pname)
        properties[pname] = prop

    return JSONResponse(content={
        "status": "success",
        "data": {
            "tool": tool_name,
            "description": doc.split("\n")[0] if doc else "",
            "properties": properties,
            "required": required,
        },
    })


@router.post("/tools/{tool_name}/test")
async def test_tool(
    tool_name: str,
    args: dict[str, Any] = Body(default={}),
) -> JSONResponse:
    """Execute a tool with the given arguments and return the result.

    This is a sandbox endpoint — it loads the tool module fresh each time
    and invokes the handler with the provided args. No permission checks
    beyond file existence (this is a developer testing endpoint).

    Args:
        tool_name: Tool file name (without .py extension).
        args: Arguments to pass to the tool function.

    Returns:
        JSONResponse with the tool's contract result.
    """
    if not _is_plain_name(tool_name):
        return _make_response("error", "Nombre de tool inválido.", 400)

    result = _load_tool_module(tool_name)
    if result is None:
        return _make_response("error", f"Tool '{tool_name}' no encontrada.", 404)

    mod, handler_name = result
    handler = getattr(mod, handler_name)

    try:
        if asyncio.iscoroutinefunction(handler):
            tool_result = await handler(**args)
        else:
            tool_result = handler(**args)
    except Exception as e:
        logger.exception("Tool test failed: %s", tool_name)
        log_error(str(e), source="agent_items.py:test_tool")
        return JSONResponse(content={
            "status": "error",
            "message": f"Error ejecutando '{tool_name}': {e}",
        }, status_code=500)

    return JSONResponse(content={
        "status": "success",
        "data": tool_result,
    })
