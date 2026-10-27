"""What the creators see of the system (agents, tools with their parameters) and what the user picked."""

from __future__ import annotations

import asyncio
from typing import Any

from backend.agent.utils.agent_helpers import get_tools_list
from backend.agent.utils.create_helpers import build_resource_context
from backend.agent.utils.loop_helpers import router_agents
from backend.agent.utils.workflows_helpers import verificar_refs
from backend.instances import agent


def test_tools_list_carries_the_full_parameters_with_their_defaults() -> None:
    """Every tool comes with its parameters, complete descriptions included."""
    tools = {t["name"]: t for t in get_tools_list()}
    props = tools["check_email"]["parameters"]["properties"]
    assert set(props) == {"folder", "sender", "date", "mark_read"}
    assert "<n>d" in props["date"]["description"], "the description is not cut at the first line"
    assert "Default" in props["date"]["description"]


def test_creator_context_has_everything_and_what_the_user_picked() -> None:
    """The creators see all the agents and tools, and the selection travels as it was picked."""
    context = asyncio.run(
        build_resource_context(
            agentes=["code-reviewer"],
            tools=["check_email"],
            tool_args={"check_email": {"date": "7d"}},
            rag=["help"],
        )
    )
    assert context["seleccion"] == {
        "agentes": ["code-reviewer"],
        "tools": ["check_email"],
        "tool_args": {"check_email": {"date": "7d"}},
        "skills": [],
        "rag": ["help"],
    }
    assert {t["name"] for t in context["tools_disponibles"]} >= {"check_email", "read", "shell"}
    assert all("description" in a and "tools" in a for a in context["agentes_disponibles"])


def test_mandatory_resources_are_rendered_by_jinja() -> None:
    """The partial tells the creator that what the user picked is mandatory, with the arguments."""
    context = asyncio.run(build_resource_context(tools=["check_email"], tool_args={"check_email": {"date": "7d"}}))
    text = agent._prompt_env.from_string('{% include "recursos_creador.jinja" %}').render(**context)
    assert "OBLIGATORIOS" in text and "nunca omitas" in text
    assert "`check_email`" in text and '"date": "7d"' in text
    assert "`folder` (string, opcional)" in text, "the parameters of every tool are listed"
    nothing = asyncio.run(build_resource_context())
    text = agent._prompt_env.from_string('{% include "recursos_creador.jinja" %}').render(**nothing)
    assert "no eligió ningún recurso" in text


def test_arguments_a_tool_does_not_have_are_reported_before_running() -> None:
    """A tool node with an invented argument is a problem of the workflow, not a failure at run time."""
    workflow: dict[str, Any] = {
        "nodes": [{"id": "mails", "type": "tool", "tool": "check_email", "args": {"dias": 7, "estado": "x"}}]
    }
    result = verificar_refs(workflow)
    assert result["ok"] is False
    detail = result["faltantes"][0]["detalle"]
    assert "dias" in detail and "estado" in detail and "date" in detail
    ok = {"nodes": [{"id": "mails", "type": "tool", "tool": "check_email", "args": {"date": "7d"}}]}
    assert verificar_refs(ok)["ok"] is True


def test_router_agents_are_a_list_that_the_template_renders() -> None:
    """The router gets its agents as data (filtered by its permissions) and jinja writes the section."""
    assert router_agents(["read"]) == [], "without the task tool there are no agents"
    agents = router_agents(["task"])
    assert agents and {"name", "description"} <= set(agents[0])
    only = router_agents(["task"], {agents[0]["name"]: "allow"})
    assert [a["name"] for a in only] == [agents[0]["name"]]
    text = agent.prompt("system_prompt", tools=["task"], agentes=only)
    assert "## Agentes" in text and f"- {only[0]['name']}: {only[0]['description']}" in text
    assert "## Agentes" not in agent.prompt("system_prompt", tools=["task"], agentes=[])
