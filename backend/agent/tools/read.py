"""ReadMixin — native tool read."""

import logging
import os

from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)


class ReadMixin:
    async def read(self, file_path: str, offset: int = 1, limit: int = 2000) -> dict:
            """Read a file or directory from the local filesystem.

            Args:
                file_path: The absolute path to the file or directory to read.
                offset: The line number to start reading from (1-indexed).
                limit: The maximum number of lines to read (defaults to 2000).

            Returns:
                dict with ``{status, message, data, usage}``.
            """
            try:
                if not os.path.exists(file_path):
                    parent = os.path.dirname(file_path)
                    base = os.path.basename(file_path)
                    if os.path.isdir(parent):
                        similares = [f for f in os.listdir(parent) if base.lower() in f.lower()]
                        if similares:
                            return make_error_response(
                                message=f"File not found: {file_path}. Did you mean: {similares[:3]}?",
                                usage=zero_usage(),
                            )
                    return make_error_response(
                        message=f"File not found: {file_path}",
                        usage=zero_usage(),
                    )

                if os.path.isdir(file_path):
                    items = sorted(os.listdir(file_path))
                    items = [
                        f"{i}/" if os.path.isdir(os.path.join(file_path, i)) else i
                        for i in items
                    ]
                    start = offset - 1
                    sliced = items[start:start + limit]
                    output = f"<path>{file_path}</path>\n<entries>\n"
                    output += "\n".join(sliced) + "\n"
                    if start + len(sliced) < len(items):
                        output += (
                            f"(Showing {len(sliced)} of {len(items)} entries. "
                            f"Use offset={offset + len(sliced)} to continue.)"
                        )
                    else:
                        output += f"({len(items)} entries)"
                    output += "\n</entries>"
                    return make_success_response(
                        message="Directory listed successfully.",
                        data=output,
                        usage=zero_usage(),
                    )

                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()

                if offset > len(lines):
                    return make_error_response(
                        message=f"Offset {offset} is out of range ({len(lines)} lines).",
                        usage=zero_usage(),
                    )

                selected = lines[offset - 1:offset - 1 + limit]
                output = f"<path>{file_path}</path>\n<type>file</type>\n<content>\n"
                output += "".join(f"{i + offset}: {line}" for i, line in enumerate(selected))

                last_line = offset + len(selected) - 1
                if offset + len(selected) <= len(lines):
                    output += (
                        f"\n(Showing lines {offset}-{last_line} of {len(lines)}. "
                        f"Use offset={last_line + 1} to continue.)"
                    )
                else:
                    output += f"\n(End of file - total {len(lines)} lines)"
                output += "\n</content>"

                return make_success_response(
                    message="File read successfully.",
                    data=output,
                    usage=zero_usage(),
                )
            except Exception as e:
                logger.exception("Error in read: %s", e)
                log_error(str(e), source="tools.py:read")
                return make_error_response(
                    message=f"Error reading file: {e}",
                    usage=zero_usage(),
                )
