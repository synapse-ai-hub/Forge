"""Internal context7 server: visibility, enforcement and execution.

The ``context7docs_*`` tools live in a code-defined MCP server (not in
``mcp.json``) and must only reach the tool-creator turn. These tests use
fake schemas and monkeypatched discovery/calls: no network, no ``npx``.
"""

from __future__ import annotations

import asyncio
import copy
from types import SimpleNamespace

import pytest

from backend.agent.permissions import filter_tools, is_tool_allowed
from backend.agent.tools import Tools
from backend.agent.utils import mcp_helper as mh


def _schema(name: str) -> dict:
    """Build a minimal tool schema entry.

    Args:
        name: Tool name for the schema.

    Returns:
        The schema dict in API format.
    """
    return {
        "type": "function",
        "function": {"name": name, "description": "fake", "parameters": {}},
    }


@pytest.fixture
def _clean_mappings():
    """Snapshot and restore the global discovery mappings and cache.

    Yields:
        Nothing; restores state on teardown.
    """
    saved_internal = copy.deepcopy(mh._internal_mcp_tool_to_server)
    saved_mcp = copy.deepcopy(mh._mcp_tool_to_server)
    saved_cache = mh._context7_schemas_cache
    mh._internal_mcp_tool_to_server.clear()
    mh._mcp_tool_to_server.clear()
    mh._context7_schemas_cache = None
    try:
        yield
    finally:
        mh._internal_mcp_tool_to_server.clear()
        mh._internal_mcp_tool_to_server.update(saved_internal)
        mh._mcp_tool_to_server.clear()
        mh._mcp_tool_to_server.update(saved_mcp)
        mh._context7_schemas_cache = saved_cache


@pytest.fixture
def _fake_registry(_clean_mappings):
    """Registry with one native, one normal MCP and two internal tools.

    Returns:
        The fake registry list.
    """
    mh._mcp_tool_to_server["mynotes_query-docs"] = "mynotes"
    mh._internal_mcp_tool_to_server["context7docs_resolve-library-id"] = (
        mh.CONTEXT7_INTERNAL_LABEL
    )
    mh._internal_mcp_tool_to_server["context7docs_query-docs"] = (
        mh.CONTEXT7_INTERNAL_LABEL
    )
    return [
        _schema("read"),
        _schema("mynotes_query-docs"),
        _schema("context7docs_resolve-library-id"),
        _schema("context7docs_query-docs"),
    ]


def test_internal_server_resolves(_clean_mappings) -> None:
    """The code-defined server resolves by label; unknown labels do not."""
    server = mh.get_internal_mcp_server(mh.CONTEXT7_INTERNAL_LABEL)
    assert server is not None
    assert "npx" in server["command"][0]
    assert mh.get_internal_mcp_server("nope") is None


def test_is_internal_mcp_tool(_fake_registry) -> None:
    """Only mapped internal tools are detected as internal."""
    assert mh.is_internal_mcp_tool("context7docs_query-docs")
    assert not mh.is_internal_mcp_tool("read")
    assert not mh.is_internal_mcp_tool("mynotes_query-docs")
    assert not mh.is_internal_mcp_tool("unknown_tool")


def test_flat_wildcard_denies_internal(_fake_registry) -> None:
    """Flat '*' shows normal tools but never internal ones (both gates)."""
    names = [t["function"]["name"] for t in filter_tools(_fake_registry, {"*": "allow"})]
    assert "read" in names
    assert "mynotes_query-docs" in names
    assert "context7docs_query-docs" not in names
    assert not is_tool_allowed({"*": "allow"}, "context7docs_query-docs")
    assert is_tool_allowed({"*": "allow"}, "read")


def test_nested_grant_admits_internal(_fake_registry) -> None:
    """An explicit nested grant shows and allows the internal tools."""
    perms = {"read": "allow", mh.CONTEXT7_INTERNAL_LABEL: {"*": "allow"}}
    names = [t["function"]["name"] for t in filter_tools(_fake_registry, perms)]
    assert "context7docs_query-docs" in names
    assert "context7docs_resolve-library-id" in names
    assert is_tool_allowed(perms, "context7docs_query-docs")
    assert is_tool_allowed(perms, "context7docs_resolve-library-id")


def test_partial_wildcard_parity(_fake_registry) -> None:
    """A partial 'query-*' grant admits only query-docs in both gates."""
    perms = {"read": "allow", mh.CONTEXT7_INTERNAL_LABEL: {"query-*": "allow"}}
    names = [t["function"]["name"] for t in filter_tools(_fake_registry, perms)]
    assert "context7docs_query-docs" in names
    assert "context7docs_resolve-library-id" not in names
    assert is_tool_allowed(perms, "context7docs_query-docs")
    assert not is_tool_allowed(perms, "context7docs_resolve-library-id")


def test_empty_perms_deny_everything(_fake_registry) -> None:
    """Empty or None permissions deny internal tools in both gates."""
    assert filter_tools(_fake_registry, {}) == []
    assert not is_tool_allowed({}, "context7docs_query-docs")
    assert not is_tool_allowed(None, "context7docs_query-docs")


def test_has_mcp_tools_ignores_internal(_clean_mappings, monkeypatch) -> None:
    """Internal-only registries must not count as having MCP tools."""
    tools = Tools.__new__(Tools)
    tools._tools_registry = [_schema("context7docs_query-docs")]
    mh._internal_mcp_tool_to_server["context7docs_query-docs"] = (
        mh.CONTEXT7_INTERNAL_LABEL
    )
    assert tools._has_mcp_tools() is False
    mh._mcp_tool_to_server["mynotes_query-docs"] = "mynotes"
    tools._tools_registry.append(_schema("mynotes_query-docs"))
    assert tools._has_mcp_tools() is True


def test_ensure_registers_and_is_idempotent(_clean_mappings, monkeypatch) -> None:
    """Schemas are appended once and mapped to the internal label."""
    calls = []

    def _fake_discovery() -> list:
        calls.append(1)
        schemas = [_schema("context7docs_resolve-library-id"), _schema("context7docs_query-docs")]
        # Mirror the real get_context7_tools: map names to the internal label.
        for schema in schemas:
            mh._internal_mcp_tool_to_server[schema["function"]["name"]] = (
                mh.CONTEXT7_INTERNAL_LABEL
            )
        return schemas

    monkeypatch.setattr(mh, "get_context7_tools", _fake_discovery)
    registry: list = [_schema("read")]
    added = mh.ensure_context7_in_registry(registry)
    assert sorted(added) == [
        "context7docs_query-docs",
        "context7docs_resolve-library-id",
    ]
    assert len(registry) == 3
    assert mh.is_internal_mcp_tool("context7docs_query-docs")
    # Second call: no duplicates.
    assert mh.ensure_context7_in_registry(registry) == []
    assert len(registry) == 3


def test_execute_internal_skips_selfheal(_clean_mappings, monkeypatch) -> None:
    """Prefix fallback resolves internal tools without re-discovering mcp.json."""
    seen: dict = {}

    async def _fake_call(config: dict, name: str, args: dict):
        seen["config"] = config
        seen["name"] = name
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="docs")])

    def _no_rediscover() -> None:
        raise AssertionError("self-heal must not run for internal tools")

    monkeypatch.setattr(mh, "_call_server_tool", _fake_call)
    monkeypatch.setattr(mh, "rediscover_mcp_servers", _no_rediscover)
    result = asyncio.run(mh.execute_mcp_tool("context7docs_query-docs", {"q": "x"}))
    assert result == "docs"
    assert seen["name"] == "query-docs"
    assert seen["config"]["label"] == mh.CONTEXT7_INTERNAL_LABEL


def test_execute_internal_anti_hijack(_clean_mappings, monkeypatch) -> None:
    """A colliding mcp.json entry must not hijack the internal server."""
    mh._mcp_tool_to_server["context7docs_query-docs"] = "evil"
    mh._internal_mcp_tool_to_server["context7docs_query-docs"] = (
        mh.CONTEXT7_INTERNAL_LABEL
    )
    seen: dict = {}

    async def _fake_call(config: dict, name: str, args: dict):
        seen["config"] = config
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="ok")])

    monkeypatch.setattr(mh, "_call_server_tool", _fake_call)
    monkeypatch.setattr(
        mh, "load_mcp_config", lambda: [{"label": "evil", "command": ["evil"]}]
    )
    result = asyncio.run(mh.execute_mcp_tool("context7docs_query-docs", {}))
    assert result == "ok"
    assert seen["config"]["label"] == mh.CONTEXT7_INTERNAL_LABEL
