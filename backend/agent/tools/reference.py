"""ReferenceMixin — native tool reference."""

import logging
import os

from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.skill_loader import find_skill_folder

logger = logging.getLogger(__name__)


class ReferenceMixin:
    async def reference(self, skill: str, file: str) -> dict:
            """Load a specific reference file from a skill's directory.

            Use this when the skill's Reference Guide is large and you only
            need a specific reference file (e.g., a product catalog, API spec).

            Args:
                skill: The skill folder name.
                file: The reference filename (e.g., "products.md", "api.md",
                      or "references/drainage.md" for files in the references/ subfolder).

            Returns:
                dict with ``{status, message, data, usage}``.
                ``data`` contains the file content as plain text.
            """
            try:
                skill_folder = find_skill_folder(skill)
                if not skill_folder:
                    return make_error_response(
                        message=f"Skill '{skill}' no encontrada.",
                        usage=zero_usage(),
                    )

                # Try direct path first, then references/ subfolder.
                # Containment: the resolved path must stay inside skill_folder.
                # Normal names keep working unchanged. Parent references or
                # absolute paths outside the skill are rejected.
                ref_path = os.path.join(skill_folder, file)
                if not os.path.isfile(ref_path):
                    # Try references/ subfolder
                    ref_path = os.path.join(skill_folder, "references", file)
                try:
                    base_real = os.path.realpath(skill_folder)
                    target_real = os.path.realpath(ref_path)
                    if target_real != base_real and not target_real.startswith(base_real + os.sep):
                        return make_error_response(
                            message=f"Referencia '{file}' fuera de la skill '{skill}'.",
                            usage=zero_usage(),
                        )
                except (OSError, ValueError) as e:
                    log_error(str(e), source="tools.py:reference(containment)")
                    return make_error_response(
                        message=f"Referencia '{file}' inválida en skill '{skill}'.",
                        usage=zero_usage(),
                    )
            
                if not os.path.isfile(ref_path):
                    return make_error_response(
                        message=f"Referencia '{file}' no existe en skill '{skill}'.",
                        usage=zero_usage(),
                    )

                with open(ref_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                return make_success_response(
                    message=f"Referencia '{file}' de skill '{skill}' cargada.",
                    data=content,
                    usage=zero_usage(),
                )
            except Exception as e:
                logger.exception("Error in reference: %s", e)
                log_error(str(e), source="tools.py:reference")
                return make_error_response(
                    message=f"Error loading reference: {e}",
                    usage=zero_usage(),
                )
