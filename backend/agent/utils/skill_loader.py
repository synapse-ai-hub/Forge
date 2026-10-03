"""Load skills from an external ``skills/`` folder for dynamic prompt injection.

Scans subdirectories of ``skills/``, reads each ``SKILL.md`` frontmatter,
and extracts the ``description`` and ``triggers`` fields. The output is
formatted for injection into the ``select_skills.md`` prompt.
"""

import json
import logging
import os
import sys

# ---------------------------------------------------------------------------
# Ensure the project root is in sys.path so absolute imports (backend.*)
# resolve correctly regardless of how the file is invoked.
# ---------------------------------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.agent.utils.config_dir import get_skills_dir
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)

from backend.agent.permissions import filter_skills, get_skill_permissions


def _parse_frontmatter_line(line: str, key: str) -> str | None:
    """Extract the value of *key* from a simple frontmatter line.

    Handles both ``key: value`` and ``key: "value"`` formats.
    Returns ``None`` if the line does not contain *key*.
    """
    stripped = line.strip()
    if not stripped.startswith(key + ":"):
        return None
    value = stripped[len(key) + 1 :].strip().strip('"').strip("'")
    return value if value else None


def _parse_frontmatter(content: str) -> dict[str, str]:
    """Parse the YAML frontmatter block of a SKILL.md file.

    Returns a dict with at most ``description`` and ``triggers`` keys.
    Both values are plain strings (triggers is a comma-separated list).
    """
    result: dict[str, str] = {}
    in_frontmatter = False
    in_metadata = False

    for line in content.splitlines():
        if line.strip() == "---":
            if not in_frontmatter:
                in_frontmatter = True
                continue
            else:
                # End of frontmatter
                break

        if not in_frontmatter:
            continue

        # Check for metadata block start
        if line.strip().startswith("metadata:"):
            in_metadata = True
            continue

        # If we were in metadata, check sub-keys
        if in_metadata:
            # A line that is not indented means we left metadata
            if line and not line[0].isspace():
                in_metadata = False
            else:
                val = _parse_frontmatter_line(line, "triggers")
                if val is not None:
                    result["triggers"] = val
                continue

        # Top-level keys
        val = _parse_frontmatter_line(line, "description")
        if val is not None:
            result["description"] = val

    return result


def format_skills_section(
    skills_dir: str | None = None,
    agent_name: str | None = None,
    skill_permissions: dict | None = None,
) -> str:
    """Scan ``skills/`` subdirectories and return a formatted skills section.

    For each subdirectory that contains ``SKILL.md``, extracts the
    ``description`` and ``triggers`` from the frontmatter and formats them
    as:

        ### {folder_name}
        - **Descripción**: {description}
        - **Triggers**: {triggers}

    If *agent_name* is provided, the selected agent's skill permissions are
    resolved at runtime (via ``backend.agent.permissions``) and only skills
    whose name resolves to ``"allow"`` are included.

    Args:
        skills_dir: Path to the ``skills/`` folder. If ``None``, uses
            the config directory ``~/.config/synapseForge/skills/``.
        agent_name: Optional selected agent name. ``None`` means no
            filtering.

    Returns:
        The formatted section string, or an empty string if the folder does
        not exist or no skills are found.
    """
    if skills_dir is None:
        skills_dir = str(get_skills_dir())

    if not skills_dir or not os.path.isdir(skills_dir):
        return ""

    entries: list[str] = []
    for item in sorted(os.listdir(skills_dir)):
        skill_path = os.path.join(skills_dir, item)
        if not os.path.isdir(skill_path):
            continue

        skill_md = os.path.join(skill_path, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue

        try:
            with open(skill_md, encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError) as e:
            log_error(str(e), source="skill_loader.py:format_skills_section(read)")
            logger.warning("Error al leer %s: %s", skill_md, e)
            continue

        frontmatter = _parse_frontmatter(content)
        description = frontmatter.get("description", "")
        triggers = frontmatter.get("triggers", "")

        if not description:
            logger.warning("SKILL.md en %s no tiene description.", skill_path)
            continue

        entries.append(
            f"### {item}\n"
            f"- **Descripción**: {description}\n"
            f"- **Triggers**: {triggers}"
        )

    skill_perms: dict | None = None
    if skill_permissions is not None:
        skill_perms = skill_permissions
    elif agent_name:
        filtro = get_skill_permissions(agent_name)
        if filtro.get("status") == "success":
            skill_perms = json.loads(filtro["data"])

    return filter_skills("\n\n".join(entries), skill_perms)


def find_skill_folder(skill_name: str) -> str | None:
    """Locate the folder for a given skill name.

    Uses the config directory ``~/.config/synapseForge/skills/``.

    Only resolves inside that base directory. Names with path separators
    or parent references are rejected, and the resolved path must stay
    within the base directory. Normal names keep working unchanged.

    Args:
        skill_name: Name of the skill folder to find.

    Returns:
        Full path to the skill folder, or ``None`` if not found.
    """
    import os

    if not skill_name or not isinstance(skill_name, str):
        return None
    if "/" in skill_name or "\\" in skill_name or ".." in skill_name:
        return None
    skills_dir = get_skills_dir()
    skill_path = skills_dir / skill_name
    if skill_path.is_dir():
        try:
            base_real = os.path.realpath(str(skills_dir))
            target_real = os.path.realpath(str(skill_path))
            if target_real == base_real or target_real.startswith(base_real + os.sep):
                return str(skill_path)
        except (OSError, ValueError):
            return None
        return None
    return None


def parse_skill_md(path: str) -> tuple[str, str]:
    """Read a SKILL.md and extract the body and the Reference Guide.

    Args:
        path: Full path to ``SKILL.md``.

    Returns:
        ``(body, reference_guide)`` where:
        - ``body``: content after frontmatter (excluding the Reference Guide section)
        - ``reference_guide``: the ``## Reference Guide`` section content, or empty
    """
    body = ""
    reference_guide = ""

    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError) as e:
        log_error(str(e), source="skill_loader.py:parse_skill_md")
        logger.warning("Error al leer %s: %s", path, e)
        return body, reference_guide

    # Strip frontmatter (between --- markers)
    lines = content.splitlines()
    if lines and lines[0].strip() == "---":
        end_fm = 1
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_fm = i + 1
                break
        content = "\n".join(lines[end_fm:])

    # Split body and reference guide
    rg_marker = "## Reference Guide"
    idx_rg = content.find(rg_marker)
    if idx_rg != -1:
        body = content[:idx_rg].strip()
        reference_guide = content[idx_rg + len(rg_marker):].strip()
    else:
        body = content.strip()

    return body, reference_guide


if __name__ == '__main__':
    skills = format_skills_section()
    print(skills)
