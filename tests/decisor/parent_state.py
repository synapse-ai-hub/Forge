"""Recreate the synapseForge parent-agent prompt, standalone.

Builds the parent-agent (router) system prompt through the real code
path (``build_system_prompt(None)`` plus the temp-dir suffix, exactly
as ``backend/agent/loop/agent_loop.py`` does), appends the real tools array and
the skills catalog, and prints the complete state text. Independent
from the decision probe: its output can be fed to
``tests/decisor/decision_cli.py -p`` for benchmark runs.

Usage:
    python tests/decisor/parent_state.py -p "mensaje del usuario"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from backend.agent.agent import Agent
from backend.agent.loop import _ROUTER_TOOLS, _load_router_permissions
from backend.agent.utils.config_dir import get_config_dir
from backend.agent.utils.loop_helpers import build_system_prompt
from backend.agent.utils.skill_loader import format_skills_section


def build_parent_tools(agent: Agent) -> list[dict[str, Any]]:
    """Rebuild the parent-agent tools array, verbatim as loop.py does.

    The parent agent is the router: if ``config.yaml`` defines router
    permissions they are used exclusively, otherwise the guaranteed
    floor applies. The array is resolved through the real
    ``tools_registry`` — the same array the LLM receives for native
    function calling. Real code, no mocks.

    Args:
        agent: Agent instance (provides ``agent.tools``).

    Returns:
        List of tool schemas in API format.
    """
    router_perms = _load_router_permissions()
    if router_perms is not None:
        # config.yaml defines permissions — use them exclusively.
        tool_permissions: dict[str, Any] = {}
        for name, action in (router_perms.get("tools") or {}).items():
            tool_permissions[name] = action
        tasks_perms = router_perms.get("tasks")
        if isinstance(tasks_perms, dict) and tasks_perms:
            tool_permissions["task"] = tasks_perms
    else:
        # No config.yaml — use the guaranteed floor.
        tool_permissions = {
            "task": "allow",
            "help": "allow",
            "search_memory": "allow",
            "read": "allow",
            "websearch": "allow",
            "webfetch": "allow",
        }
    try:
        return list(agent.tools.tools_registry(tool_permissions))
    except AttributeError:
        return _ROUTER_TOOLS


def build_parent_system_prompt() -> str:
    """Rebuild the parent-agent system prompt, verbatim as loop.py does.

    The parent agent is the router (``agent_name`` is ``None``), so this
    calls ``build_system_prompt(None)`` and appends the temp-dir section,
    mirroring ``backend/agent/loop.py`` (build-system-prompt block).
    Real code, no mocks.

    Returns:
        The exact system prompt string the parent agent receives.
    """
    temp_dir = get_config_dir() / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    system_prompt = build_system_prompt(None)
    system_prompt = "{}\n\n## Directorio temporal\n{}".format(
        system_prompt, str(temp_dir))
    return system_prompt


def build_parent_state(user_message: str) -> str:
    """Build the complete parent-agent state text.

    Args:
        user_message: User message appended at the end.

    Returns:
        System prompt plus tools / skills / user message agregado
        (added because the loop is not running here).
    """
    agent = Agent()
    tools = build_parent_tools(agent)
    # NOTE: the parent (router) never receives a skills section today
    # (loop.py only appends it for sub-agents). The full catalog is
    # included so the decision model can see it.
    skills_section = format_skills_section(skill_permissions=None)
    system_prompt = build_parent_system_prompt()
    base_text = (
        "## Tools disponibles\n"
        "```json\n"
        "{}\n"
        "```\n"
        "\n"
        "## Skills disponibles\n"
        "```\n"
        "{}\n"
        "```\n"
        "\n"
        "## Mensaje del usuario\n"
        "{}\n".format(
            json.dumps(tools, ensure_ascii=False, indent=2),
            skills_section,
            user_message,
        )
    )
    return "{}\n{}".format(system_prompt, base_text)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: print the parent state to stdout.

    Args:
        argv: Argument list (defaults to ``sys.argv``).

    Returns:
        Process exit code.
    """
    os.chdir(REPO_ROOT)
    parser = argparse.ArgumentParser(
        description="Recrea el prompt del agente padre y lo imprime.")
    parser.add_argument("-p", "--prompt", required=True,
                        help="Mensaje del usuario (va al final).")
    args = parser.parse_args(argv)
    # Raw UTF-8 bytes: the prompt contains non-cp1252 chars and the
    # Windows console would crash on print().
    sys.stdout.buffer.write((build_parent_state(args.prompt) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
