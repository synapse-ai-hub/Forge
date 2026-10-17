"""Every prompt template renders cleanly through the real ``Agent.prompt``."""

from __future__ import annotations

from pathlib import Path

from jinja2 import meta

from backend.instances import agent

PROMPTS = Path(__file__).resolve().parents[2] / "backend" / "agent" / "prompts"


def _context_for(name: str) -> dict:
    """Dummy values for every variable the template declares."""
    source = (PROMPTS / f"{name}.jinja").read_text(encoding="utf-8")
    variables = meta.find_undeclared_variables(agent._prompt_env.parse(source))
    flags = {"tools": ["read"], "decision": False}
    return {v: flags.get(v, f"<<{v}>>") for v in variables}


def test_prompts_dir_only_has_jinja_templates():
    assert not list(PROMPTS.glob("*.md")), "los prompts viven como .jinja"
    assert list(PROMPTS.glob("*.jinja"))


def test_every_template_renders_without_falling_back_to_raw_text():
    for path in sorted(PROMPTS.glob("*.jinja")):
        name = path.stem
        context = _context_for(name)
        out = agent.prompt(name, **context)
        assert out.strip(), name
        assert "{{" not in out and "{%" not in out, f"{name}: render fallido (texto crudo)"
        for value in context.values():
            if isinstance(value, str):
                assert value in out, f"{name}: la variable {value} no llegó al texto"


def test_missing_variable_does_not_break_the_chat():
    """A template that uses an unknown variable returns its raw text instead of raising."""
    out = agent.prompt("title")  # needs message and titles
    assert "{{ message }}" in out
