"""Every prompt template renders cleanly through the real ``Agent.prompt``."""

from __future__ import annotations

from pathlib import Path

from jinja2 import meta

from backend.instances import agent

PROMPTS = Path(__file__).resolve().parents[2] / "backend" / "agent" / "prompts"


STRUCTURED = {
    "tools": ["read"],
    "decision": False,
    "programada": True,
    "agentes": [{"name": "<<agente>>", "description": "<<descripcion-agente>>"}],
    "seleccion": {
        "agentes": ["<<agente-elegido>>"],
        "tools": ["<<tool-elegida>>"],
        "tool_args": {"<<tool-elegida>>": {"<<arg>>": 1}},
        "skills": ["<<skill-elegida>>"],
        "rag": ["<<rag-elegida>>"],
    },
    "agentes_disponibles": [{"name": "<<agente>>", "description": "<<descripcion-agente>>", "tools": ["<<tool>>"]}],
    "tools_disponibles": [{
        "name": "<<tool>>",
        "description": "<<descripcion-tool>>",
        "parameters": {
            "type": "object",
            "properties": {"<<parametro>>": {"type": "string", "description": "<<descripcion-parametro>>"}},
            "required": ["<<parametro>>"],
        },
    }],
    "skills_disponibles": [{"name": "<<skill>>", "description": "<<descripcion-skill>>"}],
    "rag_disponibles": ["<<coleccion>>"],
    "mcp_disponibles": [{"label": "<<mcp>>"}],
}
"""Samples for the variables that are lists or dicts (the rest get a placeholder text)."""


def _variables_of(name: str) -> set[str]:
    """Find the variables a template needs, including the templates it includes.

    Args:
        name: Template name (without extension).

    Returns:
        The names of the undeclared variables of the template and of its includes.
    """
    source = (PROMPTS / f"{name}.jinja").read_text(encoding="utf-8")
    tree = agent._prompt_env.parse(source)
    variables = set(meta.find_undeclared_variables(tree))
    for included in meta.find_referenced_templates(tree):
        if included:
            variables |= _variables_of(Path(included).stem)
    return variables


def _context_for(name: str) -> dict:
    """Build dummy values for every variable the template declares.

    Args:
        name: Template name (without extension).

    Returns:
        The variables of the template (and of the templates it includes) with a sample value each.
    """
    return {v: STRUCTURED.get(v, f"<<{v}>>") for v in _variables_of(name)}


def test_prompts_dir_only_has_jinja_templates() -> None:
    """Prompts dir only has jinja templates."""
    assert not list(PROMPTS.glob("*.md")), "los prompts viven como .jinja"
    assert list(PROMPTS.glob("*.jinja"))


def test_every_template_renders_without_falling_back_to_raw_text() -> None:
    """Every template renders without falling back to raw text."""
    for path in sorted(PROMPTS.glob("*.jinja")):
        name = path.stem
        context = _context_for(name)
        out = agent.prompt(name, **context)
        assert out.strip(), name
        assert "{{" not in out and "{%" not in out, f"{name}: render fallido (texto crudo)"
        for value in context.values():
            if isinstance(value, str):
                assert value in out, f"{name}: la variable {value} no llegó al texto"


def test_missing_variable_does_not_break_the_chat() -> None:
    """A template that uses an unknown variable returns its raw text instead of raising."""
    out = agent.prompt("title")  # needs message and titles
    assert "{{ message }}" in out
