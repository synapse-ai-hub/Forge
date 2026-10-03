"""Agent permission & prompt resolution (runtime).

Given an agent name, this module locates its markdown definition in the
``agents/`` folder (config directory) and exposes three independent resolvers,
each called from a different place:

- :func:`get_tool_permissions` — called from ``backend.agent.tools``
  (``tools_registry``). Returns **only** the tool permissions.
- :func:`get_skill_permissions` — called from
  ``backend.agent.utils.skill_loader`` (``format_skills_section``).
  Returns **only** the skill permissions.
- :func:`get_agent_prompt` — called from the system-prompt builder (loop,
  once agent selection is wired). Returns **only** the prompt body.

Each resolver reads the same markdown at runtime; none of them store
state. No defaults are applied — an agent exposes exactly what its
frontmatter declares.

The actual filtering of tools/skills is done by :func:`filter_tools` and
:func:`filter_skills` (also defined here), which the callers invoke after
resolving the permissions.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import sys
from typing import Any

import yaml

_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.utils.config_dir import get_agents_dir
from backend.agent.utils.contract import make_error_response, make_success_response
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Ensure the project root is in sys.path so absolute imports (backend.*)
# resolve correctly regardless of how the file is invoked.
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


# ---------------------------------------------------------------------------
# Folder discovery (config directory)
# ---------------------------------------------------------------------------


def _locate_agents_dir() -> str | None:
    """Locate the external ``agents/`` folder.

    Uses the config directory ``~/.config/synapseForge/agents/``.
    Returns ``None`` (no error) if the folder does not exist.
    """
    agents_dir = get_agents_dir()
    if agents_dir.is_dir():
        return str(agents_dir)
    return None


def _read_markdown(agent_name: str) -> tuple[str | None, str | None]:
    """Locate and read an agent's markdown file.

    Args:
        agent_name: Agent name (without ``.md``).

    Returns:
        ``(md_path, content)`` or ``(None, None)`` if not found.
    """
    agents_dir = _locate_agents_dir()
    if not agents_dir:
        return None, None
    # Containment: only resolve inside agents_dir. Normal names keep
    # working unchanged. Parent references or absolute paths outside
    # are rejected by returning not found.
    if "/" in agent_name or "\\" in agent_name or ".." in agent_name:
        return None, None
    md_path = os.path.join(agents_dir, f"{agent_name}.md")
    try:
        base_real = os.path.realpath(agents_dir)
        target_real = os.path.realpath(md_path)
        if target_real != base_real and not target_real.startswith(base_real + os.sep):
            return None, None
    except (OSError, ValueError):
        return None, None
    if not os.path.isfile(md_path):
        return None, None
    try:
        with open(md_path, encoding="utf-8-sig") as f:
            return md_path, f.read()
    except (OSError, UnicodeDecodeError) as e:
        log_error(str(e), source="permissions.py:_read_markdown")
        logger.warning("Error al leer %s: %s", md_path, e)
        return None, None


def _parse_frontmatter(content: str) -> dict[str, Any]:
    """Parse the YAML frontmatter block of an agent markdown string.

    Args:
        content: Full markdown content.

    Returns:
        The parsed frontmatter dict, or ``{}`` if missing/unparseable.
    """
    if not content.lstrip().startswith("---"):
        return {}

    lines = content.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}

    fm_text = "\n".join(lines[1:end])
    try:
        return yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as e:
        log_error(str(e), source="permissions.py:_parse_frontmatter")
        logger.warning("Error parseando frontmatter: %s", e)
        return {}


def _read_prompt_body(content: str) -> str:
    """Extract the prompt body (text below the frontmatter).

    Args:
        content: Full markdown content.

    Returns:
        The prompt body string, or empty if not present.
    """
    if not content.lstrip().startswith("---"):
        return content.strip()

    lines = content.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return content.strip()
    return "\n".join(lines[end + 1 :]).strip()


# ---------------------------------------------------------------------------
# Resolvers (one per concern)
# ---------------------------------------------------------------------------


def get_tool_permissions(agent_name: str | None) -> dict[str, Any]:
    """Resolve an agent's **tool** permissions at runtime.

    Reads ``agents/<agent_name>.md`` and returns the ``tools`` block
    under ``permissions``, combining it with the ``task`` block if present.

    Args:
        agent_name: Agent name (without ``.md``). ``None``/empty → empty
            permissions (no filtering).

    Returns:
        Contract response. On success, ``data`` is a JSON **string** with
        the tool permission dict.
    """
    if not agent_name:
        return make_success_response(
            message="No agent selected.", data=json.dumps({})
        )

    _, content = _read_markdown(agent_name)
    if content is None:
        return make_error_response(message=f"Agent '{agent_name}' not found.")

    fm = _parse_frontmatter(content)
    permissions = fm.get("permissions", {}) or {}
    
    tools_perms = dict(permissions.get("tools", {}) or {})
    tasks_perms = permissions.get("tasks")
    if isinstance(tasks_perms, dict) and tasks_perms:
        tools_perms["task"] = tasks_perms

    return make_success_response(
        message=f"Tool permissions for agent '{agent_name}'.",
        data=json.dumps(tools_perms),
    )


def get_skill_permissions(agent_name: str | None) -> dict[str, Any]:
    """Resolve an agent's **skill** permissions at runtime.

    Reads ``agents/<agent_name>.md`` and returns only the ``skills``
    sub-block of ``permissions`` via the unified contract.

    Args:
        agent_name: Agent name (without ``.md``). ``None``/empty → empty
            permissions (no filtering).

    Returns:
        Contract response. On success, ``data`` is a JSON **string** with
        the skill permission dict.
    """
    if not agent_name:
        return make_success_response(
            message="No agent selected.", data=json.dumps({})
        )

    _, content = _read_markdown(agent_name)
    if content is None:
        return make_error_response(message=f"Agent '{agent_name}' not found.")

    fm = _parse_frontmatter(content)
    permissions = fm.get("permissions", {}) or {}
    skills_perms = permissions.get("skills", {}) or {}

    return make_success_response(
        message=f"Skill permissions for agent '{agent_name}'.",
        data=json.dumps(skills_perms),
    )


def get_agent_prompt(agent_name: str | None) -> dict[str, Any]:
    """Resolve an agent's **prompt body** at runtime.

    Reads ``agents/<agent_name>.md`` and returns only the text below the
    frontmatter (the system prompt) via the unified contract.

    Args:
        agent_name: Agent name (without ``.md``). ``None``/empty → empty
            prompt.

    Returns:
        Contract response. On success, ``data`` is the prompt body string.
    """
    if not agent_name:
        return make_success_response(message="No agent selected.", data="")

    _, content = _read_markdown(agent_name)
    if content is None:
        return make_error_response(message=f"Agent '{agent_name}' not found.")

    return make_success_response(
        message=f"Prompt for agent '{agent_name}'.",
        data=_read_prompt_body(content),
    )


def get_agent_parameters(agent_name: str | None) -> dict[str, Any]:
    """Resolve an agent's **model parameters** from frontmatter.

    Reads ``agents/<agent_name>.md`` and extracts the ``parameters`` block
    (temperature, top_p, model, provider, max_tokens, seed, reasoning,
    response_format). Returns defaults if not specified.

    Args:
        agent_name: Agent name (without ``.md``). ``None``/empty → defaults.

    Returns:
        Contract response. On success, ``data`` is a JSON string with
        ``{"temperature": float, "top_p": float, "model": str | None,
        "provider": str | None, "max_tokens": int, "seed": int | None,
        "reasoning": str | None, "response_format": dict | None}``.
    """
    defaults = {
        "temperature": 0.0,
        "top_p": 0.5,
        "model": None,
        "provider": None,
        "max_tokens": 3000,
        "seed": None,
        "reasoning": None,
        "response_format": None,
    }

    if not agent_name:
        return make_success_response(
            message="No agent selected, using defaults.",
            data=json.dumps(defaults),
        )

    _, content = _read_markdown(agent_name)
    if content is None:
        return make_error_response(message=f"Agent '{agent_name}' not found.")

    fm = _parse_frontmatter(content)
    params = fm.get("parameters", {}) or {}

    # Merge with defaults — all supported keys are passed through
    result = {key: params.get(key, val) for key, val in defaults.items()}

    return make_success_response(
        message=f"Parameters for agent '{agent_name}'.",
        data=json.dumps(result),
    )


# ---------------------------------------------------------------------------
# Agent listing — name + description for system-prompt injection
# ---------------------------------------------------------------------------


def list_agents() -> dict:
    """List all available agents with their ``name`` and ``description``.

    Scans the ``agents/`` folder (dev/prod), parses frontmatter of each
    ``.md`` file, and returns ``name`` + ``description`` for each agent.
    Reuses existing ``_locate_agents_dir`` and ``_parse_frontmatter``.

    Returns:
        Contract response. On success, ``data`` is a JSON list of
        ``{"name": str, "description": str}``.
    """
    agents_dir = _locate_agents_dir()
    if not agents_dir:
        return make_success_response(
            message="No agents folder found.",
            data=json.dumps([]),
        )

    result: list[dict[str, str]] = []
    for entry in sorted(os.listdir(agents_dir)):
        if not entry.endswith(".md") or entry.upper() in ("AGENT.MD", "ROUTER.MD"):
            continue
        md_path = os.path.join(agents_dir, entry)
        try:
            with open(md_path, encoding="utf-8-sig") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError) as e:
            log_error(str(e), source="permissions.py:list_agents")
            logger.warning("Error al leer %s: %s", md_path, e)
            continue

        fm = _parse_frontmatter(content)
        name = fm.get("name", entry[:-3])
        description = fm.get("description", "")
        result.append({"name": name, "description": description})

    return make_success_response(
        message=f"{len(result)} agente(s) encontrado(s).",
        data=json.dumps(result),
    )


# ---------------------------------------------------------------------------
# Filtering helpers (called by tools_registry & format_skills_section)
# ---------------------------------------------------------------------------


def wildcard_match(pattern: str, text: str) -> bool:
    """Return ``True`` if *text* matches the wildcard *pattern*.

    Supports a single ``*`` wildcard (matches any sequence, including
    empty). ``Wildcard.match`` for the simple cases
    used in agent frontmatter.

    Args:
        pattern: Pattern possibly containing ``*``.
        text: Value to test against the pattern.

    Returns:
        ``True`` if *text* matches *pattern*.
    """
    if pattern == "*":
        return True
    if pattern == text:
        return True
    regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
    return re.match(regex, text) is not None


def dict_to_ruleset(perm_dict: dict[str, Any] | None) -> list[dict[str, str]]:
    """Convert a flat permission dict into a list of rules.

    Only string-valued entries become rules; nested dicts are ignored.

    Args:
        perm_dict: Permission mapping (e.g. ``{"read": "allow", ...}``).

    Returns:
        List of ``{"permission": str, "pattern": "*", "action": str}``.
    """
    rules: list[dict[str, str]] = []
    if not perm_dict:
        return rules
    for key, value in perm_dict.items():
        if isinstance(value, dict):
            continue
        rules.append(
            {"permission": str(key), "pattern": "*", "action": str(value)}
        )
    return rules


def evaluate(
    permission: str,
    pattern: str,
    *rulesets: list[dict[str, str]],
) -> str:
    """Evaluate the action for a permission/pattern against rulesets.

    ``evaluate``: scans all rulesets, finds the **last**
    rule whose ``permission`` and ``pattern`` both match (via wildcard),
    and returns its action. If no rule matches, returns ``"ask"``.

    Args:
        permission: The permission name to check (e.g. a tool name).
        pattern: The pattern to match (usually ``"*"``).
        *rulesets: One or more lists of rules. Later rulesets take
            precedence over earlier ones.

    Returns:
        One of ``"allow"``, ``"deny"`` or ``"ask"``.
    """
    rules: list[dict[str, str]] = []
    for rs in rulesets:
        rules.extend(rs)

    for rule in reversed(rules):
        if wildcard_match(rule.get("permission", ""), permission) and wildcard_match(
            rule.get("pattern", "*"), pattern
        ):
            return rule.get("action", "ask")

    return "ask"


def is_tool_allowed(
    tool_perms: dict[str, Any] | None,
    tool_name: str,
    tool_args: dict[str, Any] | None = None,
) -> bool:
    """Return whether a tool call is explicitly allowed (deny by default).

    Runtime enforcement counterpart of :func:`filter_tools`: while
    ``filter_tools`` decides which tools are *shown* to the LLM, this
    function validates each *execution* attempt against the same
    permission semantics, so a tool that was filtered out cannot be
    invoked anyway.

    Supported formats (mirroring ``filter_tools``):

    - **Flat** (``{"read": "allow"}``): allowed when the name matches the
      key (wildcard) and the value is exactly ``"allow"``.
    - **Nested group with exact match** (``{"task": {"explorer": "allow"}}``):
      for the single tool named like the group key (``task``), the first
      relevant argument (``agent_name`` for ``task``) must match one of the
      allowed sub-keys.
    - **Nested group with prefix** (``{"notebooklm": {"*": "allow"}}``):
      tools named ``<group>_<sub>`` are allowed when the group has
      ``"*": "allow"`` or the sub-tool name is explicitly allowed.

    Args:
        tool_perms: Effective tool permission dict of the running agent.
            ``None``/empty → not allowed (deny by default).
        tool_name: Name of the tool being invoked.
        tool_args: Arguments of the call (used to resolve the sub-key of
            grouped tools such as ``task``).

    Returns:
        ``True`` only when the call resolves to an explicit ``"allow"``.
    """
    if not tool_perms or not tool_name:
        return False

    # --- Nested permission (group): exact match or prefix ---
    for key, sub in tool_perms.items():
        if not isinstance(sub, dict):
            continue
        if tool_name == key:
            # Single tool constrained to allowed sub-keys (e.g. task →
            # agent_name). Resolve the discriminating argument.
            arg_name = "agent_name" if key == "task" else None
            if arg_name is None:
                # Unknown grouping argument: require the catch-all.
                return sub.get("*") == "allow"
            value = (tool_args or {}).get(arg_name, "")
            for sub_key, action in sub.items():
                if isinstance(action, str) and action == "allow" and wildcard_match(sub_key, str(value)):
                    return True
            return False
        if tool_name.startswith(key + "_"):
            if sub.get("*") == "allow":
                return True
            sub_tool = tool_name[len(key) + 1:]
            for sub_key, action in sub.items():
                if isinstance(action, str) and action == "allow" and wildcard_match(sub_key, sub_tool):
                    return True
            return False

    # --- Flat permission (e.g. read: allow) ---
    ruleset = dict_to_ruleset(tool_perms)
    if ruleset and evaluate(tool_name, "*", ruleset) == "allow":
        return True

    return False


def filter_tools(
    tools: list[dict[str, Any]],
    tool_perms: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Filter a tool registry by an agent's tool permissions.

    Works as an allow-list (no deny): only tools that resolve to
    ``"allow"`` are returned.

    Supports two formats:

    - **Flat** (e.g. ``"query": "allow"``): the tool is allowed without
      restrictions on its arguments. A top-level ``"*": "allow"`` allows
      every tool.
    - **Nested** (e.g. ``"task": {"explorer": "allow"}``): the key is a
      group. It matches a single tool by exact name (``task``) or a set of
      tools by server prefix (``notebooklm`` → every ``notebooklm_*``
      tool). If the group dict contains ``"*": "allow"``, every tool in
      the group is allowed. Otherwise only the explicitly allowed sub-keys
      are kept; for a single tool (like ``task``) the first ``string``
      parameter is constrained to an ``enum`` of the allowed sub-keys.

    When *tool_perms* is ``None``, empty, or contains no entries that
    resolve to ``"allow"``, no tools are returned (deny by default).

    Args:
        tools: List of tool schemas in API format.
        tool_perms: Top-level permission dict from the agent frontmatter.

    Returns:
        Filtered list of tool schemas.
    """
    if not tool_perms:
        return []

    # Separate flat (string values) from nested (dict values)
    flat_perms: dict[str, Any] = {}
    nested_perms: dict[str, Any] = {}
    for k, v in tool_perms.items():
        if isinstance(v, dict):
            nested_perms[k] = v
        else:
            flat_perms[k] = v

    ruleset = dict_to_ruleset(flat_perms)

    filtered: list[dict[str, Any]] = []
    for tool in tools:
        name = tool.get("function", {}).get("name", "")
        if not name:
            continue

        # --- Nested permission (group): match exact name or prefix ---
        # e.g. "task": {explorer: allow}      → matches the "task" tool (exact)
        #      "notebooklm": {"*": "allow"}   → matches every "notebooklm_*" tool
        group_key = None
        sub: dict[str, Any] = {}
        for k, v in nested_perms.items():
            if name == k or name.startswith(k + "_"):
                group_key = k
                sub = v
                break

        if group_key is not None:
            # "*" catch-all → allow every tool in the group
            if sub.get("*") == "allow":
                filtered.append(tool)
                logger.debug("Tool '%s' allowed by group '%s' (*).", name, group_key)
                continue

            allowed = [
                key for key, val in sub.items()
                if isinstance(val, str) and val == "allow"
            ]
            if not allowed:
                logger.debug(
                    "Tool '%s' denied by nested permission (no allow entries).", name
                )
                continue

            # Single tool (exact match, e.g. task): constrain first string param
            if name == group_key:
                # Deep-copy to avoid mutating the cached registry
                tool_copy = copy.deepcopy(tool)
                func = tool_copy.get("function", {})
                params = func.get("parameters", {})
                props = params.get("properties", {})

                # Apply enum to the first string parameter
                for pname, pschema in props.items():
                    if pschema.get("type") == "string" and pname != "self":
                        pschema["enum"] = allowed
                        break

                filtered.append(tool_copy)
                logger.debug("Tool '%s' allowed with enum=%s", name, allowed)
                continue

            # Prefixed tools (MCP group): include only explicitly allowed sub-tools
            sub_tool = name[len(group_key) + 1:]
            if sub_tool in allowed:
                filtered.append(tool)
                logger.debug("Tool '%s' allowed by group '%s'.", name, group_key)
            continue

        # --- Flat permission (e.g. query: allow) ---
        if ruleset:
            action = evaluate(name, "*", ruleset)
            if action == "allow":
                filtered.append(tool)
            else:
                logger.debug("Tool '%s' filtered out by flat permission (%s).", name, action)
        # else: no flat rules and no nested rules → deny (deny-by-default)

    return filtered


def filter_skills(
    skills_text: str,
    skill_perms: dict[str, Any] | None,
) -> str:
    """Filter a formatted skills section by an agent's skill permissions.

    Parses the ``### <name>`` headers, keeps only blocks whose name
    resolves to ``"allow"``, and rebuilds the string. When *skill_perms*
    is ``None``, empty, or contains no flat string entries, no skills
    are returned (deny by default).

    Args:
        skills_text: Output of ``format_skills_section`` (markdown).
        skill_perms: The ``skill`` sub-dict from the agent frontmatter.

    Returns:
        Filtered markdown skills section.
    """
    if not skill_perms:
        return ""
    if not skills_text.strip():
        return skills_text

    ruleset = dict_to_ruleset(skill_perms)
    if not ruleset:
        return ""

    blocks = skills_text.split("\n\n")
    kept: list[str] = []
    for block in blocks:
        match = re.match(r"^###\s+(.+)$", block.strip(), re.MULTILINE)
        if not match:
            kept.append(block)
            continue
        name = match.group(1).strip()
        if evaluate(name, "*", ruleset) == "allow":
            kept.append(block)
        else:
            logger.debug("Skill '%s' filtered out by permission.", name)

    return "\n\n".join(kept)
