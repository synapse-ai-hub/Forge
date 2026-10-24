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
from collections.abc import Iterator

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
def _config_dir(files: dict[str, str]) -> Iterator[Path]:
    """Point the app's config dir to a temp folder with the given agents/*.md files.

    Args:
        files: File name → text of the agents to create.

    Yields:
        Control while the config dir points to the temporary folder.
    """
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
    """Get the tool names the router receives for a ``config.yaml`` permissions dict.

    Args:
        router_perms: The ``permissions`` block of the config, or None.

    Returns:
        The tool names.
    """
    perms = _router_tool_permissions(router_perms)
    return [t["function"]["name"] for t in agent.tools.tools_registry(perms)]


def test_template_with_all_tools_equals_original() -> None:
    """Rendering with every tool enabled gives back the pre-Jinja text."""
    assert agent.prompt("system_prompt", tools=_all_tool_names()) == ORIGINAL.read_text(encoding="utf-8")


def test_mandatory_with_all_tools_equals_original() -> None:
    """Mandatory with all tools equals original."""
    assert agent.prompt("mandatory", tools=_all_tool_names()) == MANDATORY.read_text(encoding="utf-8")


def test_mandatory_drops_todo_line_without_write() -> None:
    """Mandatory drops todo line without write."""
    assert "archivo TODO" in agent.prompt("mandatory", tools=["write"])
    assert "archivo TODO" not in agent.prompt("mandatory", tools=["read"])


def test_default_router_prompt_has_security_after_mandatory() -> None:
    """Default router prompt has security after mandatory."""
    names = _router_tool_names(None)
    prompt = build_system_prompt(None, tools=names)
    assert prompt.index("## MANDATORY:") < prompt.index("## Seguridad") < prompt.index("## Fecha")
    assert "{%" not in prompt and "{{" not in prompt


def test_small_yaml_drops_sections_of_missing_tools() -> None:
    """Small yaml drops sections of missing tools."""
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


def test_router_without_tools_has_no_tool_sections() -> None:
    """Router without tools has no tool sections."""
    names = _router_tool_names({"tools": {}})
    # Only the always-on floor remains: rag on the internal collections.
    assert names == ["rag"]
    prompt = build_system_prompt(None, tools=names)
    assert "## Cómo encontrar y leer información" not in prompt
    assert "Seguir enlaces o descargar archivos" not in prompt
    assert "## Seguridad" in prompt


def test_shell_adds_command_and_sql_rules() -> None:
    """Shell adds command and sql rules."""
    names = _router_tool_names({"tools": {"shell": "allow"}})
    assert names == ["rag", "shell"]
    prompt = build_system_prompt(None, tools=names)
    assert "comandos destructivos" in prompt
    assert "usá parámetros" in prompt


def test_agent_md_is_plain_text_never_a_template() -> None:
    """A literal ``{{ }}`` in AGENT.md reaches the prompt untouched."""
    with _config_dir({"AGENT.md": AGENT_MD}):
        prompt = build_system_prompt(None, tools=_router_tool_names(None))
    assert "{{ llaves }}" in prompt and "{% bloques %}" in prompt


def test_subagent_gets_security_for_its_own_tools() -> None:
    """A sub-agent prompt carries ## Seguridad, adapted to the agent's own tools."""
    with _config_dir({"qa.md": QA_AGENT, "lector.md": LECTOR_AGENT}):
        qa = build_system_prompt("qa")
        lector = build_system_prompt("lector")
    assert "## Seguridad" in qa and "comandos destructivos" in qa
    assert qa.index("## MANDATORY:") < qa.index("## Seguridad") < qa.index("## Fecha")
    assert "## Seguridad" in lector and "comandos destructivos" not in lector
    assert "archivo TODO" not in lector


def test_user_template_renders_plain_message_untouched() -> None:
    """User template with only a message returns it byte by byte."""
    assert agent.prompt("user_prompt", user_message="hola") == "hola"


def test_user_template_renders_all_sections_in_order() -> None:
    """User template appends contexto, attachments and frontier in order."""
    out = agent.prompt(
        "user_prompt",
        user_message="hacé X",
        contexto="CTX",
        attachments_section="<inicio_adjuntos>\n**Archivo: f**\nT\n<fin_adjuntos>",
        frontier="FRON",
    )
    assert out.index("hacé X") < out.index("## Contexto") < out.index("CTX")
    assert out.index("CTX") < out.index("<inicio_adjuntos>")
    assert out.index("<fin_adjuntos>") < out.index("## Trabajo sin cerrar")
    assert out.index("## Trabajo sin cerrar") < out.index("FRON")


def test_build_user_message_attachments_match_legacy_format() -> None:
    """Attachments render exactly like the old effective_message."""
    from backend.agent.utils.loop_helpers import build_user_message

    out = build_user_message(
        "hola", file_contents=[("a.txt", "AAA"), ("b.txt", "BBB")]
    )
    assert out == (
        "hola\n\n<inicio_adjuntos>\n"
        "**Archivo: a.txt**\nAAA\n**Archivo: b.txt**\nBBB\n<fin_adjuntos>"
    )


def test_router_system_prompt_has_no_contexto() -> None:
    """Context files travel in the user message, not the router system."""
    prompt = build_system_prompt(None, tools=_router_tool_names(None))
    assert "## Contexto" not in prompt


def test_subagent_system_prompt_has_no_contexto() -> None:
    """Sub-agents stay isolated: no context files in their system prompt."""
    with _config_dir({"qa.md": QA_AGENT, "lector.md": LECTOR_AGENT}):
        assert "## Contexto" not in build_system_prompt("lector")
        assert "## Contexto" not in build_system_prompt("qa")


def test_task_forwards_parent_attachments_to_subagent() -> None:
    """task() passes the turn attachments to the child loop user message."""
    import asyncio
    from unittest import mock

    from backend.agent.tools.task import TaskMixin
    from backend.agent.utils.loop_helpers import _tool_call_ctx

    mixin = TaskMixin()
    mixin._task_config = {
        "agent_name": "lector",
        "tool_permissions": {},
        "skill_permissions": {},
        "parameters": {},
        "parent_model": "m",
        "parent_provider": "p",
    }
    files = [("doc.txt", "CONTENIDO")]
    token = _tool_call_ctx.set(
        {
            "parent_session_id": "sess-1",
            "depth": 0,
            "stream_cancel_event": None,
            "tool_permissions": {},
            "task_config": mixin._task_config,
            "subagent_event_queue": None,
            "file_contents": files,
        }
    )
    captured: dict = {}
    try:
        with _config_dir({"lector.md": LECTOR_AGENT}):
            with (
                mock.patch("backend.instances.session_manager") as sm,
                mock.patch("backend.agent.loop.AgentLoop") as loop_cls,
            ):
                sm.create_session.return_value = {"status": "success"}

                async def fake_run(**kwargs):  # type: ignore[no-untyped-def]
                    captured.update(kwargs)
                    yield 'data: {"type": "chunk", "content": "ok"}\n\n'
                    yield "data: [DONE]\n\n"

                loop_cls.return_value.run = fake_run
                result = asyncio.run(mixin.task("lector", "revisá esto"))
    finally:
        _tool_call_ctx.reset(token)
    assert result["status"] == "success"
    assert captured.get("file_contents") == files


def test_build_user_message_omits_empty_sections() -> None:
    """None, empty string and empty list leave a plain message."""
    from backend.agent.utils.loop_helpers import build_user_message

    assert build_user_message("hola") == "hola"
    assert (
        build_user_message("hola", contexto=None, file_contents=None, frontier=None)
        == "hola"
    )
    out = build_user_message("hola", contexto="", file_contents=[], frontier="")
    assert out == "hola"
    assert "## Contexto" not in out
    assert "## Trabajo sin cerrar" not in out
    assert "<inicio_adjuntos>" not in out


def test_build_user_message_falls_back_without_template() -> None:
    """Without user_prompt.jinja the message plus attachments survive."""
    from unittest import mock

    from backend.agent.utils.loop_helpers import build_user_message
    from backend.instances import agent as agent_singleton

    with mock.patch.object(
        agent_singleton, "prompt", side_effect=FileNotFoundError("x")
    ):
        assert build_user_message("hola") == "hola"
        assert build_user_message(
            "hola", file_contents=[("a.txt", "AAA")]
        ) == "hola\n\n<inicio_adjuntos>\n**Archivo: a.txt**\nAAA\n<fin_adjuntos>"


def test_build_user_message_never_raises_on_malformed_files() -> None:
    """Malformed file_contents never raise; the plain message survives."""
    from backend.agent.utils.loop_helpers import build_user_message

    assert build_user_message("hola", file_contents=[("solo_uno",)]) == "hola"  # type: ignore[list-item]
    assert build_user_message("hola", file_contents=[None]) == "hola"  # type: ignore[list-item]
    assert build_user_message("hola", file_contents="texto") == "hola"  # type: ignore[arg-type]


def test_subagent_style_render_has_attachments_without_contexto() -> None:
    """Sub-agent user content carries attachments but never ## Contexto."""
    from backend.agent.utils.loop_helpers import build_user_message

    out = build_user_message(
        "revisá esto", contexto="", file_contents=[("d.txt", "C")]
    )
    assert "<inicio_adjuntos>" in out and "**Archivo: d.txt**" in out
    assert "## Contexto" not in out
