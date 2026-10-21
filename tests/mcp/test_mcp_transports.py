"""MCP servers over stdio, streamable HTTP and SSE, and the on/off switch in mcp.json.

Everything runs against real MCP servers (``echo_server.py``, started as a
subprocess per transport) and the real ``mcp_helper`` / ``config_dir``
functions. ``XDG_CONFIG_HOME`` points to a temp folder so the user's own
``mcp.json`` is never read or written.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from backend.agent.utils import config_dir, mcp_helper
from collections.abc import Iterator

SERVER = str(Path(__file__).resolve().parent / "echo_server.py")


def _free_port() -> int:
    """Find a free TCP port on the loopback interface.

    Returns:
        The port number.
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def _config_dir() -> Iterator[Path]:
    """Point the app's config dir to an empty temp folder.

    Yields:
        The ``synapseForge`` folder inside the temporary config dir.
    """
    with tempfile.TemporaryDirectory() as tmp:
        previous = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = tmp
        try:
            yield Path(tmp) / "synapseForge"
        finally:
            if previous is None:
                os.environ.pop("XDG_CONFIG_HOME", None)
            else:
                os.environ["XDG_CONFIG_HOME"] = previous


@contextlib.contextmanager
def _remote_server(mode: str) -> Iterator[int]:
    """Start ``echo_server.py`` as an HTTP or SSE server and wait until it accepts connections.

    Args:
        mode: Transport to serve (``http`` or ``sse``).

    Yields:
        The port the server listens on.

    Raises:
        RuntimeError: If the server does not start in 30 seconds.
    """
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, SERVER, mode, str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            with contextlib.suppress(OSError):
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            time.sleep(0.2)
        else:
            raise RuntimeError(f"{mode} server did not start")
        yield port
    finally:
        proc.terminate()
        with contextlib.suppress(Exception):
            proc.wait(timeout=10)


def _stdio_config(label: str = "echo-stdio") -> dict:
    """Build the config of the stdio echo server.

    Args:
        label: Label of the server.

    Returns:
        The MCP server config.
    """
    return {"label": label, "transport": "stdio", "command": sys.executable, "args": [SERVER, "stdio"]}


def _discover_and_call(config: dict) -> tuple[list[str], str]:
    """Discover the tools of a server and call its ``echo`` tool.

    Args:
        config: MCP server config.

    Returns:
        ``(tool_names, echo_result)``.
    """
    async def run() -> tuple[list[str], str]:
        """Discover and call in the same event loop.

        Returns:
            ``(tool_names, echo_result)``.
        """
        tools = await mcp_helper._discover_server_tools(config, retries=1)
        result = await mcp_helper._call_server_tool(config, "echo", {"text": "hola"})
        return [t.name for t in tools], mcp_helper._mcp_content_to_serializable(result.content)

    return asyncio.run(run())


def test_stdio_server_discovery_and_call() -> None:
    """Stdio server discovery and call."""
    names, output = _discover_and_call(_stdio_config())
    assert names == ["echo"] and output == "echo: hola"


def test_streamable_http_server_discovery_and_call() -> None:
    """Streamable http server discovery and call."""
    with _remote_server("http") as port:
        config = {"label": "echo-http", "transport": "http", "server_url": f"http://127.0.0.1:{port}/mcp"}
        names, output = _discover_and_call(config)
    assert names == ["echo"] and output == "echo: hola"


def test_sse_server_discovery_and_call() -> None:
    """Sse server discovery and call."""
    with _remote_server("sse") as port:
        config = {"label": "echo-sse", "transport": "sse", "url": f"http://127.0.0.1:{port}/sse"}
        names, output = _discover_and_call(config)
    assert names == ["echo"] and output == "echo: hola"


def test_transport_is_inferred_when_not_declared() -> None:
    """Transport is inferred when not declared."""
    assert mcp_helper._transport_kind({"command": "node"}) == "stdio"
    assert mcp_helper._transport_kind({"server_url": "https://x.test/mcp"}) == "http"
    assert mcp_helper._transport_kind({"transport": "sse", "url": "https://x.test/sse"}) == "sse"


def test_health_is_a_real_handshake_for_every_transport() -> None:
    """Health is a real handshake for every transport."""
    with _config_dir() as cfg, _remote_server("http") as port:
        cfg.mkdir(parents=True)
        servers = [
            _stdio_config("a-stdio"),
            {"label": "b-http", "server_url": f"http://127.0.0.1:{port}/mcp"},
            # answers HTTP but is not an MCP server: the old GET-only check said "connected"
            {"label": "c-not-mcp", "server_url": f"http://127.0.0.1:{_free_port()}/mcp"},
        ]
        config_dir.save_mcp_servers(servers)
        result = {r["label"]: r["status"] for r in asyncio.run(mcp_helper.check_all_mcp_servers_health(timeout=20.0))}
    assert result == {"a-stdio": "connected", "b-http": "connected", "c-not-mcp": "failed"}


def test_disabled_server_is_not_discovered_nor_executed_nor_counted() -> None:
    """Disabled server is not discovered nor executed nor counted."""
    with _config_dir() as cfg:
        cfg.mkdir(parents=True)
        config_dir.save_mcp_servers([_stdio_config("echo-stdio")])
        assert mcp_helper.mcp_servers_configured() is True

        assert mcp_helper.set_mcp_server_enabled("echo-stdio", False) is True
        saved = json.loads((cfg / "mcp.json").read_text(encoding="utf-8"))
        assert saved[0]["disabled"] is True
        assert mcp_helper.mcp_servers_configured() is False
        assert asyncio.run(mcp_helper._discover_all(mcp_helper.load_mcp_config())) == []
        health = asyncio.run(mcp_helper.check_mcp_server_health("echo-stdio"))
        assert health["status"] == "disabled"

        # a tool left over in the mapping must not run while the server is off
        mcp_helper._mcp_tool_to_server["echo-stdio_echo"] = "echo-stdio"
        try:
            try:
                asyncio.run(mcp_helper.execute_mcp_tool("echo-stdio_echo", {"text": "x"}))
                raised = False
            except ValueError as exc:
                raised = "disabled" in str(exc)
        finally:
            mcp_helper._mcp_tool_to_server.pop("echo-stdio_echo", None)
        assert raised

        assert mcp_helper.set_mcp_server_enabled("echo-stdio", True) is True
        saved = json.loads((cfg / "mcp.json").read_text(encoding="utf-8"))
        assert "disabled" not in saved[0]
        found = asyncio.run(mcp_helper._discover_all(mcp_helper.load_mcp_config()))
        assert [t["function"]["name"] for t in found] == ["echo-stdio_echo"]
        assert asyncio.run(mcp_helper.execute_mcp_tool("echo-stdio_echo", {"text": "x"})) == "echo: x"


def test_enabled_false_written_by_hand_is_honored_and_normalized() -> None:
    """Enabled false written by hand is honored and normalized."""
    with _config_dir() as cfg:
        cfg.mkdir(parents=True)
        config_dir.save_mcp_servers([dict(_stdio_config("echo-stdio"), enabled=False)])
        assert mcp_helper.is_server_enabled(mcp_helper.load_mcp_config()[0]) is False
        assert mcp_helper.set_mcp_server_enabled("echo-stdio", False) is True
        saved = json.loads((cfg / "mcp.json").read_text(encoding="utf-8"))
        assert "enabled" not in saved[0] and saved[0]["disabled"] is True


def test_toggle_of_unknown_server_returns_none() -> None:
    """Toggle of unknown server returns none."""
    with _config_dir() as cfg:
        cfg.mkdir(parents=True)
        config_dir.save_mcp_servers([_stdio_config("echo-stdio")])
        assert mcp_helper.set_mcp_server_enabled("nope", False) is None


def test_broken_mcp_json_is_reported_not_silently_empty() -> None:
    """Broken mcp json is reported not silently empty."""
    with _config_dir() as cfg:
        cfg.mkdir(parents=True)
        assert config_dir.mcp_config_error() is None  # no file is fine
        (cfg / "mcp.json").write_text("[ {not json", encoding="utf-8")
        assert config_dir.load_mcp_servers() == []
        assert "JSON" in config_dir.mcp_config_error()
        (cfg / "mcp.json").write_text('{"label": "x"}', encoding="utf-8")
        assert "array" in config_dir.mcp_config_error()


def test_save_is_atomic_and_leaves_no_temp_file() -> None:
    """Save is atomic and leaves no temp file."""
    with _config_dir() as cfg:
        cfg.mkdir(parents=True)
        assert config_dir.save_mcp_servers([_stdio_config("echo-stdio")]) is True
        names = [p.name for p in cfg.iterdir()]
        assert "mcp.json" in names and not any(n.endswith(".tmp") for n in names)
        assert config_dir.load_mcp_servers()[0]["label"] == "echo-stdio"
