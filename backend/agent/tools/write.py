"""WriteMixin — native tool write."""

import logging
import os

from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)


class WriteMixin:
    async def write(self, file_path: str, content: str) -> dict:
            """Writes content to a file on the local filesystem.

            Creates parent directories if they do not exist.

            Args:
                file_path: The absolute path to the file to write.
                content: The content to write to the file.

            Returns:
                dict with ``{status, message, data, usage}``.
            """
            try:
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                return make_success_response(
                    message="Wrote file successfully.",
                    data={"file_path": file_path},
                    usage=zero_usage(),
                )
            except Exception as e:
                logger.exception("Error in write: %s", e)
                log_error(str(e), source="tools.py:write")
                return make_error_response(
                    message=f"Error writing file: {e}",
                    usage=zero_usage(),
                )
