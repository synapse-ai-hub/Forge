"""EditMixin — native tool edit."""

import logging
import os

from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)


class EditMixin:
    async def edit(self, file_path: str, old_string: str, new_string: str,
                       replace_all: bool = False) -> dict:
            """Performs exact string replacements in a file.

            Args:
                file_path: The absolute path to the file to modify.
                old_string: The text to replace.
                new_string: The text to replace it with (must be different from old_string).
                replace_all: Replace all occurrences of old_string (default False).

            Returns:
                dict with ``{status, message, data, usage}``.
            """
            try:
                if not os.path.exists(file_path):
                    return make_error_response(
                        message=f"File not found: {file_path}",
                        usage=zero_usage(),
                    )
                if old_string == new_string:
                    return make_error_response(
                        message="old_string and new_string are identical.",
                        usage=zero_usage(),
                    )

                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                if replace_all:
                    if old_string not in content:
                        return make_error_response(
                            message=f"old_string not found in {file_path}",
                            usage=zero_usage(),
                        )
                    new_content = content.replace(old_string, new_string)
                    count = content.count(old_string)
                else:
                    count = content.count(old_string)
                    if count == 0:
                        return make_error_response(
                            message=f"old_string not found in {file_path}",
                            usage=zero_usage(),
                        )
                    if count > 1:
                        return make_error_response(
                            message=f"Found {count} matches. Provide more context or use replace_all=True.",
                            usage=zero_usage(),
                        )
                    new_content = content.replace(old_string, new_string)

                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)

                return make_success_response(
                    message=f"Edit applied successfully ({count} replacement(s)).",
                    data={"file_path": file_path, "replacements": count},
                    usage=zero_usage(),
                )
            except Exception as e:
                logger.exception("Error in edit: %s", e)
                log_error(str(e), source="tools.py:edit")
                return make_error_response(
                    message=f"Error editing file: {e}",
                    usage=zero_usage(),
                )
