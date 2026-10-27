"""MCP (Model Context Protocol) helper.

Loads MCP server configurations from ``mcp.json`` (direct array)
and provides functions to discover tools and execute tool calls over
the MCP protocol using the official ``mcp`` SDK (same approach as opencode).

Usage::

    from backend.agent.utils.mcp_helper import get_mcp_tools, execute_mcp_tool

    # Get all MCP tools as function schemas
    mcp_tools = get_mcp_tools()
    # mcp_tools -> [{"name": ..., "description": ..., "input_schema": ...}, ...]

    # Execute a tool
    result = await execute_mcp_tool("mssql", "execute_query", {"sql": "SELECT 1"})
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import time
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, AsyncIterator

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.utils.config_dir import load_mcp_servers, save_mcp_servers
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

McpServerConfig = dict[str, Any]
"""Structure of a single MCP server entry from ``mcp.json`` (array).

Keys: ``label``, ``transport`` (``"stdio"``, ``"http"`` for streamable HTTP,
or ``"sse"``; inferred when absent: ``command`` means stdio, a URL means
streamable HTTP), ``command`` (string or list), ``args``, ``env``/``environment``,
``description``, ``server_url`` (or ``url``), ``headers``,
``oauth``, ``disabled``, ``timeout``.
"""


def load_mcp_config() -> list[McpServerConfig]:
    """Load MCP server configurations from ``mcp.json`` (direct array).

    Returns:
        List of MCP server config dicts, or empty list if not configured.
    """
    servers = load_mcp_servers()
    if not servers:
        logger.debug("No MCP servers found in mcp.json — skipping MCP config load.")
        return []

    return servers


# ---------------------------------------------------------------------------
# stdio transport helpers (official MCP SDK)
# ---------------------------------------------------------------------------


def _build_stdio_params(config: McpServerConfig) -> StdioServerParameters:
    """Build ``StdioServerParameters`` from an MCP server config.

    Args:
        config: MCP server config dict.

    Returns:
        ``StdioServerParameters`` ready for ``stdio_client``.

    Raises:
        ValueError: If the config has no ``command``.
    """
    cmd_raw = config.get("command", [])
    if isinstance(cmd_raw, list):
        cmd = cmd_raw
    else:
        cmd = [cmd_raw] + config.get("args", [])
    if not cmd or not cmd[0]:
        raise ValueError("stdio MCP server without 'command'")
    env = {**os.environ, **config.get("environment", config.get("env", {}))}
    return StdioServerParameters(command=cmd[0], args=cmd[1:], env=env)


def is_server_enabled(config: McpServerConfig) -> bool:
    """Return ``False`` when the server is switched off in ``mcp.json``.

    A server is off with ``"disabled": true`` (what the UI writes) or
    ``"enabled": false``; anything else leaves it on.

    Args:
        config: MCP server config dict.

    Returns:
        ``True`` when the server is enabled.
    """
    if config.get("disabled"):
        return False
    return config.get("enabled") is not False


_HTTP_TRANSPORTS = {"http", "streamable_http", "streamable-http", "streamablehttp"}


def _transport_kind(config: McpServerConfig) -> str:
    """Return how to talk to the server: ``"stdio"``, ``"http"`` or ``"sse"``.

    Uses ``transport`` when it is declared. Otherwise a ``command`` means
    stdio and an ``http(s)`` URL means streamable HTTP.

    Args:
        config: MCP server config dict.

    Returns:
        The transport kind.
    """
    declared = str(config.get("transport") or "").strip().lower()
    if declared == "sse":
        return "sse"
    if declared in _HTTP_TRANSPORTS:
        return "http"
    if declared == "stdio":
        return "stdio"
    if config.get("command"):
        return "stdio"
    if _server_has_http_url(config):
        return "http"
    return "stdio"


@asynccontextmanager
async def _open_session(
    config: McpServerConfig, timeout: float
) -> AsyncIterator[ClientSession]:
    """Open an initialized MCP session over the server's transport.

    The only place that knows the transports: stdio, streamable HTTP and
    SSE all yield the same ``ClientSession``, so discovery, calls and the
    health check work the same for every kind of server.

    Args:
        config: MCP server config dict.
        timeout: Seconds allowed for the ``initialize`` handshake.

    Yields:
        An initialized ``ClientSession``.

    Raises:
        ValueError: If a remote server has no URL (or a stdio one no command).
        asyncio.TimeoutError: If the handshake takes longer than *timeout*.
    """
    kind = _transport_kind(config)
    headers = config.get("headers") or None
    async with AsyncExitStack() as stack:
        if kind == "stdio":
            streams = await stack.enter_async_context(
                stdio_client(_build_stdio_params(config))
            )
        else:
            url = config.get("server_url") or config.get("url")
            if not url:
                raise ValueError(f"{kind} MCP server without 'server_url'")
            if kind == "sse":
                streams = await stack.enter_async_context(
                    sse_client(url, headers=headers, sse_read_timeout=timeout)
                )
            else:
                http_client = await stack.enter_async_context(
                    create_mcp_http_client(headers=headers)
                )
                streams = await stack.enter_async_context(
                    streamable_http_client(url, http_client=http_client)
                )
        session = await stack.enter_async_context(ClientSession(streams[0], streams[1]))
        await asyncio.wait_for(session.initialize(), timeout=timeout)
        yield session


def _server_timeout(config: McpServerConfig, default: float = 300.0) -> float:
    """Return the per-server connection timeout in seconds.

    Reads the ``timeout`` key from the server config (loaded from
    ``mcp.json``). Falls back to ``default`` (300s) when the server does
    not define one, so long-running tools (e.g. interactive auth or slow
    notebook queries) are not cut short.

    Args:
        config: MCP server config dict.
        default: Fallback timeout when the config has no ``timeout``.

    Returns:
        Timeout in seconds.
    """
    try:
        return float(config.get("timeout", default))
    except (TypeError, ValueError):
        return default


async def _discover_server_tools(
    config: McpServerConfig, retries: int = 3, backoff: float = 1.0
) -> list[Any]:
    """Discover tools from a single MCP server using the official SDK.

    Retries with exponential backoff so a transient failure (e.g. the
    server being momentarily busy, or a lingering instance holding a
    shared resource) does not permanently leave the tool registry empty,
    without hammering a deterministically broken server.

    Args:
        config: MCP server config dict.
        retries: Number of attempts before giving up.
        backoff: Base delay (seconds); doubled on every retry.

    Returns:
        List of ``mcp.types.Tool`` objects.

    Raises:
        Exception: The error of the last attempt (for example ``asyncio.TimeoutError`` when the
            server does not respond in time) once every attempt failed.
    """
    timeout = _server_timeout(config)
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            async with _open_session(config, timeout) as session:
                result = await asyncio.wait_for(
                    session.list_tools(), timeout=timeout
                )
                return result.tools
        except Exception as exc:  # noqa: BLE001 - retry any transient failure
            last_exc = exc
            if attempt < retries:
                logger.warning(
                    "MCP discovery attempt %d/%d failed: %s — retrying",
                    attempt,
                    retries,
                    exc,
                )
                await asyncio.sleep(backoff * (2 ** (attempt - 1)))
    if last_exc is not None:
        raise last_exc
    return []


async def _call_server_tool(
    config: McpServerConfig, name: str, arguments: dict[str, Any]
) -> Any:
    """Call a tool on a single MCP server using the official SDK.

    Args:
        config: The MCP server config dict.
        name: Tool name.
        arguments: Tool arguments dict.

    Returns:
        The ``CallToolResult`` from the server.

    Raises:
        asyncio.TimeoutError: If the server does not respond in time.
    """
    timeout = _server_timeout(config)
    async with _open_session(config, timeout) as session:
        return await asyncio.wait_for(
            session.call_tool(name, arguments), timeout=timeout
        )


# ---------------------------------------------------------------------------
# Tool-to-server mapping (populated by get_mcp_tools)
# ---------------------------------------------------------------------------

_mcp_tool_to_server: dict[str, str] = {}
"""Maps MCP tool name → server label for dispatch in ``_execute_tool``."""

# Cooldown (seconds) between one-shot self-heal re-discoveries, so a
# genuinely unreachable MCP server is not hammered on every tool call.
_SELFHEAL_COOLDOWN = 30.0
_last_selfheal_ts: float = 0.0


# ---------------------------------------------------------------------------
# Internal context7 server (tool creator only, not in mcp.json)
# ---------------------------------------------------------------------------

CONTEXT7_INTERNAL_LABEL = "context7docs"
"""Label of the internal context7 server.

It is deliberately different from any user label (a user may add their own
``context7`` entry in ``mcp.json`` without collision): tools are exposed as
``context7docs_*`` and are only granted to the tool-creator turn.
"""

CONTEXT7_INTERNAL_SERVER: McpServerConfig = {
    "label": CONTEXT7_INTERNAL_LABEL,
    "transport": "stdio",
    "command": ["npx", "-y", "@upstash/context7-mcp"],
    "description": "Documentación actualizada de librerías (interno del creador de tools).",
    "timeout": 60.0,
}
"""Code-defined context7 server: never read from nor written to ``mcp.json``.

``CONTEXT7_API_KEY`` is picked up from the backend environment automatically
(``_build_stdio_params`` inherits ``os.environ``); without a key the server
still starts and answers with lower rate limits.
"""

_internal_mcp_tool_to_server: dict[str, str] = {}
"""Maps internal tool name → internal server label (survives mcp.json re-discoveries)."""

_context7_schemas_cache: list[dict[str, Any]] | None = None
"""Discovered context7 schemas, cached so ``npx`` is spawned only once per process."""

_context7_failed_ts: float = 0.0
"""When the last context7 discovery failed (``0.0`` when it never failed)."""

_CONTEXT7_RETRY_COOLDOWN = 600.0
"""Seconds before a failed context7 discovery is retried.

A failure caches ``[]`` so a broken server (no ``npx``, no network) does
not spawn a process on every tool-creator turn; once the cooldown expires
the next turn tries again in case the problem was transient.
"""

_context7_lock = threading.Lock()
"""Guards the check-then-set of ``_context7_schemas_cache`` under concurrency."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _mcp_tool_to_function_schema(
    mcp_tool: Any, name_override: str | None = None
) -> dict[str, Any]:
    """Convert an MCP tool definition to a function-call schema.

    Accepts both ``mcp.types.Tool`` objects (from the SDK) and plain dicts.
    When *name_override* is provided (e.g. a server-label prefixed name),
    it is used as the tool name instead of the raw MCP tool name.

    Args:
        mcp_tool: MCP tool definition.
        name_override: Optional name to use for the tool (defaults to the
            MCP tool's own name).

    Returns:
        Function schema ready for the tools registry.
    """
    if isinstance(mcp_tool, dict):
        name = name_override or mcp_tool.get("name", "")
        description = mcp_tool.get("description", "")
        input_schema = mcp_tool.get("inputSchema", {})
    else:
        name = name_override or getattr(mcp_tool, "name", "")
        description = getattr(mcp_tool, "description", "") or ""
        # SDK >= 2.x uses snake_case; older versions and plain dicts use camelCase.
        input_schema = (
            getattr(mcp_tool, "input_schema", None)
            or getattr(mcp_tool, "inputSchema", None)
            or {}
        )
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": input_schema or {"type": "object", "properties": {}},
        },
    }


def _server_has_http_url(server: McpServerConfig) -> bool:
    """Check if server config has a valid HTTP/SSE URL.

    Args:
        server: The MCP server configuration.

    Returns:
        True when its URL is an http(s) address.
    """
    url = server.get("server_url") or server.get("url")
    if not url:
        return False
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        return parsed.scheme in ("http", "https")
    except Exception:
        return False


async def _discover_all(servers: list[McpServerConfig]) -> list[dict[str, Any]]:
    """Discover tools from every enabled server and populate the mapping.

    Servers switched off in ``mcp.json`` are skipped: no process is started
    and none of their tools reach the registry.

    Args:
        servers: MCP server configs loaded from mcp.json.

    Returns:
        Freshly discovered function schemas.
    """
    function_tools: list[dict[str, Any]] = []
    for server in servers:
        label = server.get("label", "unknown")
        if not is_server_enabled(server):
            logger.info("MCP '%s' — disabled, skipping discovery", label)
            continue
        try:
            tools = await _discover_server_tools(server)
            for tool in tools:
                # Prefix the tool name with the server label so that
                # permissions can group tools per server (e.g. a
                # "notebooklm" permission matches every "notebooklm_*"
                # tool). This is generic and works for any server.
                prefixed_name = f"{label}_{tool.name}"
                function_tools.append(
                    _mcp_tool_to_function_schema(tool, prefixed_name)
                )
                _mcp_tool_to_server[prefixed_name] = label
            logger.info("MCP '%s' — discovered %d tool(s)", label, len(tools))
        except Exception as exc:
            log_error(str(exc), source="mcp_helper.py:_discover_all")
            logger.warning("MCP '%s' — failed to discover tools: %s", label, exc)
    return function_tools


def _run_discovery(servers: list[McpServerConfig]) -> list[dict[str, Any]]:
    """Run discovery on a fresh event loop, safe from sync or async callers.

    When called from a running event loop (e.g. the agent loop re-discovering
    an empty registry), the discovery runs on a dedicated thread with its own
    loop so it never fails with ``RuntimeError``.

    Args:
        servers: MCP server configs loaded from mcp.json.

    Returns:
        Freshly discovered function schemas.

    Raises:
        Exception: The error the discovery failed with, when it ran on the dedicated thread.
    """

    def _worker() -> list[dict[str, Any]]:
        """Run the discovery coroutine in a fresh event loop.

        Returns:
            The discovered tools.
        """
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(_discover_all(servers))
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — run discovery directly on a fresh loop.
        return _worker()

    # Already inside an event loop: run discovery on a dedicated thread.
    result: list[dict[str, Any]] = []
    error: Exception | None = None

    def _thread_worker() -> None:
        """Run the discovery in a thread and keep its result."""
        nonlocal result, error
        try:
            result = _worker()
        except Exception as exc:  # noqa: BLE001
            error = exc

    thread = threading.Thread(target=_thread_worker, daemon=True)
    thread.start()
    thread.join(timeout=120.0)
    if thread.is_alive():
        # Discovery is still running in the background. Log it clearly so
        # the empty result is not mistaken for a successful discovery.
        logger.warning(
            "MCP discovery still running after 120s — returning partial/empty "
            "result; the background thread may populate the mapping later."
        )
    if error is not None:
        raise error
    return result


def get_mcp_tools_ollama() -> list[dict[str, Any]]:
    """Discover tools from all MCP servers and wrap as function schemas.

    Uses the official MCP SDK with a per-server timeout. A server that
    fails or times out is isolated — it is logged and skipped, and the
    rest of the startup continues normally. Discovery is safe to call
    from both synchronous and asynchronous contexts.

    Returns:
        List of function schemas ready for ``tools_registry``.
    """
    global _mcp_tool_to_server
    servers = load_mcp_config()
    # Clear any stale mapping so a re-discovery does not accumulate
    # entries for servers that are no longer reachable. Mutate in place
    # (instead of rebinding) so concurrent readers never see a fresh dict.
    _mcp_tool_to_server.clear()
    try:
        return _run_discovery(servers)
    except Exception as exc:
        log_error(str(exc), source="mcp_helper.py:get_mcp_tools")
        return []


def get_mcp_tools() -> list[dict[str, Any]]:
    """Get all MCP tools wrapped as function schemas (universal).

    Wraps stdio MCP tools as ``"type": "function"`` schemas. This is
    the recommended approach for local MCP servers like MSSQL.

    Returns:
        List of function schemas ready for ``tools_registry``.
    """
    return get_mcp_tools_ollama()


def mcp_servers_configured() -> bool:
    """Return ``True`` if at least one enabled MCP server is in mcp.json.

    Disabled servers do not count: they never produce tools, so counting
    them would make the registry look incomplete and trigger useless
    re-discoveries.

    Returns:
        ``True`` when there is at least one enabled MCP server entry.
    """
    return any(is_server_enabled(server) for server in load_mcp_config())


def set_mcp_server_enabled(label: str, enabled: bool) -> bool | None:
    """Switch a server on or off in ``mcp.json`` (the single source of truth).

    Writes the ``disabled`` key (removed when enabling) and drops a legacy
    ``enabled`` key so the file keeps one way of saying it.

    Args:
        label: Server label.
        enabled: ``True`` to enable, ``False`` to disable.

    Returns:
        ``None`` if no server has that label, otherwise whether the file was saved.
    """
    servers = load_mcp_servers()
    for server in servers:
        if server.get("label") != label:
            continue
        server.pop("enabled", None)
        if enabled:
            server.pop("disabled", None)
        else:
            server["disabled"] = True
        return save_mcp_servers(servers)
    return None


def mcp_tools_discovered() -> bool:
    """Return ``True`` if at least one MCP tool has been discovered.

    Returns:
        ``True`` if the tool-to-server mapping is non-empty.
    """
    return bool(_mcp_tool_to_server)


def rediscover_mcp_servers() -> list[dict[str, Any]]:
    """Re-run MCP discovery, clearing any stale tool-to-server mapping.

    Useful to recover from a transient failure at startup (e.g. the MCP
    server was momentarily busy), so the tool registry is not left empty
    for the whole session.

    Returns:
        Freshly discovered function schemas.
    """
    return get_mcp_tools_ollama()


def is_mcp_tool(tool_name: str) -> bool:
    """Check if *tool_name* belongs to an MCP server.

    Args:
        tool_name: Tool name to check.

    Returns:
        ``True`` if the tool is managed by an MCP server (including the
        internal context7 server).
    """
    return tool_name in _mcp_tool_to_server or tool_name in _internal_mcp_tool_to_server


def is_internal_mcp_tool(tool_name: str) -> bool:
    """Check if *tool_name* belongs to the internal context7 server.

    Args:
        tool_name: Tool name to check.

    Returns:
        ``True`` only for ``context7docs_*`` tools. Used to hide them from
        the UI listings and from every permission set except the explicit
        tool-creator grant.
    """
    return tool_name in _internal_mcp_tool_to_server


def get_internal_mcp_server(label: str) -> McpServerConfig | None:
    """Return the code-defined server config for an internal label.

    Args:
        label: Server label to look up.

    Returns:
        The internal server config when *label* is the context7 internal
        label, otherwise ``None``.
    """
    if label == CONTEXT7_INTERNAL_LABEL:
        server = dict(CONTEXT7_INTERNAL_SERVER)
        if os.name == "nt":
            # On Windows `npx` is a .cmd shim, not an executable: spawning
            # it directly fails with WinError 193.
            cmd = list(server.get("command", []))
            if cmd and cmd[0] == "npx":
                cmd[0] = "npx.cmd"
                server["command"] = cmd
        return server
    return None


def get_context7_tools() -> list[dict[str, Any]]:
    """Discover the internal context7 tools (cached, never raises).

    Spawns the code-defined server once per process and returns its tools
    as function schemas (``context7docs_*``). Failures (missing ``npx``,
    no network, bad package) are logged and yield ``[]`` so the caller
    turn continues without context7.

    Returns:
        List of function schemas (possibly empty).
    """
    global _context7_schemas_cache, _context7_failed_ts
    if _context7_schemas_cache:
        return list(_context7_schemas_cache)
    if _context7_schemas_cache is not None and (
        time.time() - _context7_failed_ts < _CONTEXT7_RETRY_COOLDOWN
    ):
        # A previous discovery failed and the cooldown has not expired:
        # do not spawn `npx` again on this turn.
        return []
    with _context7_lock:
        if _context7_schemas_cache:
            return list(_context7_schemas_cache)
        if _context7_schemas_cache is not None and (
            time.time() - _context7_failed_ts < _CONTEXT7_RETRY_COOLDOWN
        ):
            return []
        try:
            # Resolve through get_internal_mcp_server so platform fixes
            # (e.g. `npx.cmd` on Windows) apply to discovery as well.
            server = get_internal_mcp_server(CONTEXT7_INTERNAL_LABEL)
            assert server is not None
            schemas = _run_discovery([server])
        except Exception as exc:
            logger.warning("Internal context7 discovery failed: %s", exc)
            log_error(str(exc), source="mcp_helper.py:get_context7_tools")
            _context7_schemas_cache = []
            _context7_failed_ts = time.time()
            return []
        # Move the entries out of the mcp.json mapping into the internal one so
        # a later global re-discovery cannot wipe them.
        for schema in schemas:
            name = schema.get("function", {}).get("name", "")
            if name:
                _internal_mcp_tool_to_server[name] = CONTEXT7_INTERNAL_LABEL
                _mcp_tool_to_server.pop(name, None)
        _context7_schemas_cache = schemas
        logger.info("Internal context7 — discovered %d tool(s)", len(schemas))
        return list(schemas)


def ensure_context7_in_registry(registry: list[dict[str, Any]]) -> list[str]:
    """Append the internal context7 schemas missing from a tool registry.

    Idempotent: names already present are skipped, so registry rebuilds
    (refresh button, agent editor) are repaired on the next tool-creator
    turn without re-spawning ``npx`` (schemas are cached).

    Args:
        registry: Mutable tool registry (e.g. ``agent.tools._tools_registry``).

    Returns:
        Names of the schemas that were appended (empty when none).
    """
    try:
        schemas = get_context7_tools()
    except Exception as exc:  # noqa: BLE001 - never break the turn
        logger.warning("ensure_context7_in_registry failed: %s", exc)
        return []
    present = {e.get("function", {}).get("name", "") for e in registry}
    added = []
    for schema in schemas:
        name = schema.get("function", {}).get("name", "")
        if name and name not in present:
            registry.append(schema)
            added.append(name)
    return added


def _mcp_content_to_serializable(content: list[Any]) -> Any:
    """Convert MCP content items to a JSON-serializable representation.

    MCP servers return tool results as content items (``TextContent``,
    ``ImageContent``, ``EmbeddedResource``) which are not JSON-serializable
    and would break ``json.dumps`` downstream. When every item is text, the
    items are joined into a single string (the most useful form for the
    LLM). Otherwise each item is converted to a plain dict.

    Args:
        content: ``result.content`` from an MCP tool call.

    Returns:
        A JSON-serializable value (string or list of dicts).
    """
    if not content:
        return ""
    if all(getattr(item, "type", "text") == "text" for item in content):
        return "\n".join(getattr(item, "text", str(item)) for item in content)
    items: list[dict[str, Any]] = []
    for item in content:
        if isinstance(item, dict):
            items.append(item)
        elif hasattr(item, "model_dump"):
            items.append(item.model_dump())
        else:
            items.append(
                {
                    "type": getattr(item, "type", "text"),
                    "text": getattr(item, "text", str(item)),
                }
            )
    return items


async def execute_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    """Execute a tool on the MCP server that owns it.

    Resolves the server label from the tool-to-server mapping
    (populated by ``get_mcp_tools_ollama``), connects, calls the
    tool, and returns the result.

    Args:
        tool_name: MCP tool name (e.g. ``"execute_query"``).
        arguments: Tool arguments dict.

    Returns:
        JSON-serializable tool result (text string or list of dicts), or
        raises on error.

    Raises:
        ValueError: If the tool is not registered in any MCP server.
    """
    global _last_selfheal_ts
    label = _internal_mcp_tool_to_server.get(tool_name) or _mcp_tool_to_server.get(tool_name)
    if label is None and tool_name.startswith(f"{CONTEXT7_INTERNAL_LABEL}_"):
        # Prefix fallback: the internal server spawns per call, so it can
        # run even when its schemas were never discovered in this process.
        # Resolved before the self-heal below so an internal tool never
        # triggers a full (blocking) re-discovery of mcp.json servers.
        label = CONTEXT7_INTERNAL_LABEL
    if label is None:
        # One-shot self-heal: the mapping may be empty because discovery
        # failed at startup. Re-discover once (bounded by a cooldown) and
        # retry before giving up.
        now = time.time()
        if now - _last_selfheal_ts > _SELFHEAL_COOLDOWN:
            _last_selfheal_ts = now
            rediscover_mcp_servers()
            label = _mcp_tool_to_server.get(tool_name)
    if label is None:
        raise ValueError(f"Tool '{tool_name}' is not registered in any MCP server")

    # Strip the server-label prefix to recover the original MCP tool name
    original_name = (
        tool_name[len(label) + 1:] if tool_name.startswith(f"{label}_") else tool_name
    )

    servers = load_mcp_config()
    config = next((s for s in servers if s.get("label") == label), None)
    if is_internal_mcp_tool(tool_name) or tool_name.startswith(f"{CONTEXT7_INTERNAL_LABEL}_"):
        # The internal label is reserved: a user entry with the same tool
        # name in mcp.json must not hijack the internal server. Force the
        # code-defined server regardless of the resolved label.
        config = get_internal_mcp_server(CONTEXT7_INTERNAL_LABEL) or config
    if config is None:
        # Fall back to the code-defined internal servers (not in mcp.json).
        config = get_internal_mcp_server(label)
    if config is None:
        raise ValueError(
            f"Tool '{tool_name}' is not registered in any MCP server"
        )
    if not is_server_enabled(config):
        raise ValueError(f"MCP server '{label}' is disabled")

    result = await _call_server_tool(config, original_name, arguments)
    return _mcp_content_to_serializable(result.content)


# ---------------------------------------------------------------------------
# Health check / Status API
# ---------------------------------------------------------------------------


class McpServerStatus:
    """MCP server status constants (matching opencode's Status type)."""

    CONNECTED = "connected"
    DISABLED = "disabled"
    FAILED = "failed"
    NEEDS_AUTH = "needs_auth"
    NEEDS_CLIENT_REGISTRATION = "needs_client_registration"


async def check_mcp_server_health(label: str, timeout: float = 10.0) -> dict[str, Any]:
    """Check health of a single MCP server by label.

    Args:
        label: Server label from mcp.json.
        timeout: Connection timeout in seconds.

    Returns:
        Status dict with keys: label, status, tools_count, tools, error.
    """
    servers = load_mcp_servers()
    config = next((s for s in servers if s.get("label") == label), None)
    if not config:
        return {
            "label": label,
            "status": McpServerStatus.FAILED,
            "error": f"Server '{label}' not found in mcp.json",
        }

    config_with_label = dict(config)
    config_with_label["label"] = label

    if not is_server_enabled(config_with_label):
        return {
            "label": label,
            "status": McpServerStatus.DISABLED,
            "tools_count": 0,
        }

    return await _check_server_health(config_with_label, timeout)


async def _check_server_health(
    config: McpServerConfig, timeout: float
) -> dict[str, Any]:
    """Check a server with a real MCP handshake, whatever its transport.

    Args:
        config: The MCP server configuration.
        timeout: Seconds to wait for the handshake.

    Returns:
        A dict with the connection status of the server.
    """
    label = config.get("label", "unknown")
    try:
        async with _open_session(config, timeout):
            pass
        return {
            "label": label,
            "status": McpServerStatus.CONNECTED,
            "transport": _transport_kind(config),
        }
    except Exception as exc:
        return {
            "label": label,
            "status": McpServerStatus.FAILED,
            "transport": _transport_kind(config),
            "error": str(exc),
        }


async def check_all_mcp_servers_health(timeout: float = 10.0) -> list[dict[str, Any]]:
    """Check health of all configured MCP servers.

    Args:
        timeout: Connection timeout per server in seconds.

    Returns:
        List of status dicts for each server.
    """
    servers = load_mcp_servers()
    results = []

    for server in servers:
        label = server.get("label", "unknown")
        result = await check_mcp_server_health(label, timeout)
        results.append(result)

    return results