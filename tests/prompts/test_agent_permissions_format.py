"""Agent frontmatter format: what the prompts teach is what the runtime reads.

The agent-creation prompts and the scheduler write agent ``.md`` files; the
runtime reads ``permissions.tools`` / ``permissions.tasks`` / ``permissions.skills``
through ``get_tool_permissions`` and ``get_skill_permissions``. These tests run
those real functions against the examples and files the app generates.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
from pathlib import Path

from backend.agent.permissions import get_skill_permissions, get_tool_permissions
from backend.agent.utils.scheduler_helpers import _ensure_scheduler_agent

PROMPTS = Path(__file__).resolve().parents[2] / "backend" / "agent" / "prompts"


@contextlib.contextmanager
def _config_dir():
    """Point the app's config dir to an empty temp folder; yield its agents dir."""
    with tempfile.TemporaryDirectory() as tmp:
        agents = Path(tmp) / "synapseForge" / "agents"
        agents.mkdir(parents=True)
        previous = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = tmp
        try:
            yield agents
        finally:
            if previous is None:
                os.environ.pop("XDG_CONFIG_HOME", None)
            else:
                os.environ["XDG_CONFIG_HOME"] = previous


def _example_agent(prompt_file: str) -> tuple[str, str]:
    """First ```markdown example of an agent prompt: (agent name, file text)."""
    text = (PROMPTS / prompt_file).read_text(encoding="utf-8")
    example = re.search(r"```markdown\n(.*?)```", text, re.S).group(1)
    return re.search(r"^name:\s*(\S+)", example, re.M).group(1), example


def _resolved(name: str) -> tuple[dict, dict]:
    tools = json.loads(get_tool_permissions(name)["data"])
    skills = json.loads(get_skill_permissions(name)["data"])
    return tools, skills


def test_create_and_iterate_examples_are_read_by_the_runtime():
    for prompt_file in ("create_agent.jinja", "iterate_agent.jinja"):
        name, example = _example_agent(prompt_file)
        with _config_dir() as agents:
            (agents / f"{name}.md").write_text(example, encoding="utf-8")
            tools, skills = _resolved(name)
        assert tools.get("read") == "allow" and tools.get("shell") == "allow", prompt_file
        assert any(v == "allow" for v in skills.values()), prompt_file


def test_prompts_do_not_teach_the_singular_keys():
    for prompt_file in ("create_agent.jinja", "iterate_agent.jinja"):
        text = (PROMPTS / prompt_file).read_text(encoding="utf-8")
        assert not re.search(r"^\s*permission:", text, re.M), prompt_file
        assert not re.search(r"^\s*skill:", text, re.M), prompt_file


def test_scheduler_agent_file_is_read_by_the_runtime():
    task = {
        "name": "tarea-prueba",
        "tool_permissions": {"read": "allow", "task": {"explorador": "allow"}},
        "skill_permissions": {"mi-skill": "allow"},
        "parameters": {},
    }
    with _config_dir():
        assert _ensure_scheduler_agent(task) == "tarea-prueba"
        tools, skills = _resolved("tarea-prueba")
    assert tools == {"read": "allow", "task": {"explorador": "allow"}}
    assert skills == {"mi-skill": "allow"}
