"""ListDirMixin — native tool list_dir."""

import logging
import os
import re

from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)


class ListDirMixin:
    async def list_dir(self, path: str = ".") -> dict:
            """List files and directories in a given path.

            Args:
                path: Directory path to list. Defaults to current working directory.

            Returns:
                dict with ``{status, message, data, usage}``.
            """
            try:
                # Normalize path: on Windows, drive-relative paths like "D:/" or "D:"
                # resolve to the current working directory on that drive, not the root.
                # We need to explicitly convert them to the actual root "D:\\".
                if os.name == "nt":
                    # Match "D:/" or "D:" (drive letter + optional slash)
                    if re.match(r'^[A-Za-z]:/?$', path):
                        search = path.rstrip("/") + "\\"
                    else:
                        search = os.path.abspath(path)
                else:
                    search = os.path.abspath(path)

                if not os.path.isdir(search):
                    return make_error_response(
                        message=f"The path must be a directory: {search}",
                        usage=zero_usage(),
                    )

                entries = os.listdir(search)
                items = []
                for entry in sorted(entries):
                    full = os.path.join(search, entry)
                    item_type = "dir" if os.path.isdir(full) else "file"
                    items.append({"name": entry, "type": item_type})

                if not items:
                    return make_success_response(
                        message="Directory is empty.",
                        data=[],
                        usage=zero_usage(),
                    )

                return make_success_response(
                    message=f"{len(items)} entradas encontradas en {search}.",
                    data=items,
                    usage=zero_usage(),
                )
            except Exception as e:
                logger.exception("Error in list_dir: %s", e)
                log_error(str(e), source="tools.py:list_dir")
                return make_error_response(
                    message=f"Error listing directory: {e}",
                    usage=zero_usage(),
                )
