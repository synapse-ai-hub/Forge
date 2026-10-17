"""MCP endpoints: the toggle writes mcp.json and rebuilds the real tools registry.

Uses the real routers (``agent_items`` and ``config.listings``) and the real
``agent.tools`` registry with the echo server over stdio, with
``XDG_CONFIG_HOME`` pointing to a temp folder.
"""

from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.agent.utils import config_dir
from backend.instances import agent
from backend.routes import agent_items
from backend.routes.config import listings
from tests.mcp.test_mcp_transports import _config_dir, _stdio_config

app = FastAPI()
app.include_router(agent_items.router, prefix="/api")
app.include_router(listings.router, prefix="/api/config")
client = TestClient(app)


def _registry_names() -> list[str]:
    return [t["function"]["name"] for t in agent.tools._tools_registry]


def test_toggle_endpoint_writes_the_json_and_updates_the_registry():
    with _config_dir() as cfg:
        cfg.mkdir(parents=True)
        config_dir.save_mcp_servers([_stdio_config("echo-stdio")])
        try:
            agent.tools._tools_registry = agent.tools._build_tools_registry()
            assert "echo-stdio_echo" in _registry_names()

            res = client.put("/api/agent/mcp/echo-stdio/enabled", json={"enabled": False})
            assert res.status_code == 200 and res.json()["status"] == "success"
            assert json.loads((cfg / "mcp.json").read_text(encoding="utf-8"))[0]["disabled"] is True
            assert "echo-stdio_echo" not in _registry_names()

            listing = client.get("/api/config/mcp").json()
            assert listing["error"] is None
            assert [(s["label"], s["status"]) for s in listing["servers"]] == [("echo-stdio", "disabled")]

            res = client.put("/api/agent/mcp/echo-stdio/enabled", json={"enabled": True})
            assert res.status_code == 200
            assert "echo-stdio_echo" in _registry_names()
            assert client.get("/api/config/mcp").json()["servers"][0]["status"] == "connected"
        finally:
            config_dir.save_mcp_servers([])
            agent.tools._tools_registry = agent.tools._build_tools_registry()


def test_toggle_endpoint_validates_input():
    with _config_dir() as cfg:
        cfg.mkdir(parents=True)
        config_dir.save_mcp_servers([_stdio_config("echo-stdio")])
        assert client.put("/api/agent/mcp/echo-stdio/enabled", json={"enabled": "yes"}).status_code == 400
        assert client.put("/api/agent/mcp/nope/enabled", json={"enabled": False}).status_code == 404


def test_listing_reports_a_broken_mcp_json():
    with _config_dir() as cfg:
        cfg.mkdir(parents=True)
        (cfg / "mcp.json").write_text("[ {broken", encoding="utf-8")
        data = client.get("/api/config/mcp").json()
    assert data["servers"] == [] and "JSON" in data["error"]
