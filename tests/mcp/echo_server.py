"""Tiny real MCP server used by the MCP tests.

    python echo_server.py stdio
    python echo_server.py http <port>
    python echo_server.py sse <port>

It exposes one tool, ``echo``, and speaks the real protocol over the
chosen transport (the same SDK servers use).
"""

from __future__ import annotations

import sys

from mcp.server.mcpserver import MCPServer

server = MCPServer("echo")


@server.tool()
def echo(text: str) -> str:
    """Return the text it receives."""
    return f"echo: {text}"


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "stdio":
        server.run("stdio")
    elif mode == "http":
        server.run("streamable-http", port=int(sys.argv[2]))
    elif mode == "sse":
        server.run("sse", port=int(sys.argv[2]))
    else:
        raise SystemExit(f"unknown mode: {mode}")
