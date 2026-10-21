"""Router and sub-agent system prompts: Jinja render vs the original prompts.

Everything runs through the real functions the app uses: ``Agent.prompt``,
``build_system_prompt``, ``_router_tool_permissions`` and the real tools
registry. Only the pure-template tests compare text byte by byte; the
assembled prompt depends on the machine (agents, context files, date), so
those tests check structure.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path

from backend.agent.loop import _router_tool_permissions
from backend.agent.utils.loop_helpers import _all_tool_names, build_system_prompt
from backend.instances import agent

GOLDEN_DIR = Path(__file__).parent / "golden"
ORIGINAL = GOLDEN_DIR / "system_prompt_original.md"
MANDATORY = GOLDEN_DIR / "mandatory_original.md"

QA_AGENT = (
    "---\n"
    "name: qa\n"
    "description: Prueba cosas.\n"
    "permissions:\n"
    "  tools:\n"
    "    shell: allow\n"
    "---\n"
    "Sos QA.\n"
)
LECTOR_AGENT = "---\nname: lector\ndescription: Lee.\n---\nSos lector.\n"
AGENT_MD = "Usá {{ llaves }} y {% bloques %} literales.\n"


@contextlib.contextmanager
def _config_dir(files: dict[str, str]):
    """Point the app's config dir to a temp folder with the given agents/*.md files."""
    with tempfile.TemporaryDirectory() as tmp:
        agents = Path(tmp) / "synapseForge" / "agents"
        agents.mkdir(parents=True)
        for name, text in files.items():
            (agents / name).write_text(text, encoding="utf-8")
        previous = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = tmp
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop("XDG_CONFIG_HOME", None)
            else:
                os.environ["XDG_CONFIG_HOME"] = previous


def _router_tool_names(router_perms: dict | None) -> list[str]:
    """Tool names the router gets for a ``config.yaml`` permissions dict."""
    perms = _router_tool_permissions(router_perms)
    return [t["function"]["name"] for t in agent.tools.tools_registry(perms)]


def test_template_with_all_tools_equals_original():
    """Rendering with every tool enabled gives back the pre-Jinja text."""
    assert agent.prompt("system_prompt", tools=_all_tool_names()) == ORIGINAL.read_text(encoding="utf-8")


def test_mandatory_with_all_tools_equals_original():
    assert agent.prompt("mandatory", tools=_all_tool_names()) == MANDATORY.read_text(encoding="utf-8")


def test_mandatory_drops_todo_line_without_write():
    assert "archivo TODO" in agent.prompt("mandatory", tools=["write"])
    assert "archivo TODO" not in agent.prompt("mandatory", tools=["read"])


def test_default_router_prompt_has_security_after_mandatory():
    names = _router_tool_names(None)
    prompt = build_system_prompt(None, tools=names)
    assert prompt.index("## MANDATORY:") < prompt.index("## Seguridad") < prompt.index("## Fecha")
    assert "{%" not in prompt and "{{" not in prompt


def test_small_yaml_drops_sections_of_missing_tools():
    names = _router_tool_names(
        {"tools": {"read": "allow", "websearch": "allow", "webfetch": "allow", "search_memory": "allow"}}
    )
    assert "task" not in names and "write" not in names
    prompt = build_system_prompt(None, tools=names)
    for gone in ("## TODOs para tareas complejas",
                 "### Cómo redactar el prompt para el sub-agente"):
        assert gone not in prompt, gone
    assert "delegar las tareas" not in prompt
    assert "## Memoria de largo plazo" in prompt
    assert "## Cómo encontrar y leer información" in prompt
    assert "Seguir enlaces o descargar archivos" in prompt
    assert "comandos destructivos" not in prompt


def test_router_without_tools_has_no_tool_sections():
    names = _router_tool_names({"tools": {}})
    # Only the always-on floor remains: rag on the internal collections.
    assert names == ["rag"]
    prompt = build_system_prompt(None, tools=names)
    assert "## Cómo encontrar y leer información" not in prompt
    assert "Seguir enlaces o descargar archivos" not in prompt
    assert "## Seguridad" in prompt


def test_shell_adds_command_and_sql_rules():
    names = _router_tool_names({"tools": {"shell": "allow"}})
    assert names == ["rag", "shell"]
    prompt = build_system_prompt(None, tools=names)
    assert "comandos destructivos" in prompt
    assert "usá parámetros" in prompt


def test_agent_md_is_plain_text_never_a_template():
    """A literal ``{{ }}`` in AGENT.md reaches the prompt untouched."""
    with _config_dir({"AGENT.md": AGENT_MD}):
        prompt = build_system_prompt(None, tools=_router_tool_names(None))
    assert "{{ llaves }}" in prompt and "{% bloques %}" in prompt


def test_subagent_gets_security_for_its_own_tools():
    """A sub-agent prompt carries ## Seguridad, adapted to the agent's own tools."""
    with _config_dir({"qa.md": QA_AGENT, "lector.md": LECTOR_AGENT}):
        qa = build_system_prompt("qa")
        lector = build_system_prompt("lector")
    assert "## Seguridad" in qa and "comandos destructivos" in qa
    assert qa.index("## MANDATORY:") < qa.index("## Seguridad") < qa.index("## Fecha")
    assert "## Seguridad" in lector and "comandos destructivos" not in lector
    assert "archivo TODO" not in lector
