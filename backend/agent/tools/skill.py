"""SkillMixin — native tool skill."""

import logging
import os

from backend.agent.permissions import dict_to_ruleset, evaluate
from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.skill_loader import find_skill_folder, parse_skill_md

logger = logging.getLogger(__name__)


class SkillMixin:
    """Native tool ``skill``: load a skill by name from the skills directory."""
    async def skill(self, name: str) -> dict:
            """Load a skill by name from the skills directory.

            Reads the SKILL.md file, parses its frontmatter and body,
            and returns the skill content formatted for injection into
            the agent's context.

            The requested name must be explicitly allowed in the calling
            agent's skill permissions (same semantics as the catalog
            filter): without an explicit ``allow`` the call is denied,
            even when the ``skill`` tool itself is enabled.

            Args:
                name: The skill folder name (must match a subdirectory
                      under the skills/ folder containing SKILL.md).

            Returns:
                dict with ``{status, message, data, usage}``.
                ``data`` contains the formatted skill content (XML block).
            """
            try:
                # --- Explicit skill permission check (deny by default) ---
                # A parallel-loop snapshot (ContextVar) takes precedence over
                # the shared Tools attribute. Lazy import: top-level would be
                # circular (loop_helpers -> instances -> agent -> tools).
                from backend.agent.utils.loop_helpers import _tool_call_ctx

                snapshot = _tool_call_ctx.get()
                if snapshot is not None and "skill_permissions" in snapshot:
                    skill_perms = snapshot.get("skill_permissions")
                else:
                    skill_perms = getattr(self, "_current_skill_permissions", None)
                if skill_perms is not None:
                    ruleset = dict_to_ruleset(skill_perms)
                    if not ruleset or evaluate(name, "*", ruleset) != "allow":
                        logger.warning(
                            "Permission denied: skill '%s' is not explicitly allowed.",
                            name,
                        )
                        log_error(
                            f"Permission denied for skill '{name}'.",
                            source="tools.py:skill(permission)",
                        )
                        return make_error_response(
                            message=f"Permiso denegado para la skill '{name}'.",
                            usage=zero_usage(),
                        )

                # Locate the skill folder
                skill_folder = find_skill_folder(name)
                if not skill_folder:
                    return make_error_response(
                        message=f"Skill '{name}' no encontrada.",
                        usage=zero_usage(),
                    )

                skill_md_path = os.path.join(skill_folder, "SKILL.md")
                if not os.path.isfile(skill_md_path):
                    return make_error_response(
                        message=f"SKILL.md no existe en skill '{name}'.",
                        usage=zero_usage(),
                    )

                # Parse the skill markdown
                body, reference_guide = parse_skill_md(skill_md_path)

                # Format for context injection
                from pathlib import Path
                base_dir = Path(skill_folder).as_uri()
                output = (
                    f"<skill_content name=\"{name}\">\n"
                    f"# Skill: {name}\n\n"
                    f"{body}\n\n"
                    f"Base directory for this skill: {base_dir}\n"
                    f"Relative paths in this skill (e.g., scripts/, reference/) are relative to this base directory.\n"
                    f"Note: file list is sampled.\n\n"
                    f"<skill_files>\n"
                    f"{reference_guide if reference_guide else '(sin Reference Guide)'}\n"
                    f"</skill_files>\n"
                    f"</skill_content>"
                )

                return make_success_response(
                    message=f"Skill '{name}' cargada.",
                    data=output,
                    usage=zero_usage(),
                )
            except Exception as e:
                logger.exception("Error in skill: %s", e)
                log_error(str(e), source="tools.py:skill")
                return make_error_response(
                    message=f"Error loading skill: {e}",
                    usage=zero_usage(),
                )
