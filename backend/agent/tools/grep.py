"""GrepMixin — native tool grep."""

import fnmatch
import logging
import os
import re

from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)


class GrepMixin:
    async def grep(self, pattern: str, path: str | None = None,
                       include: str | None = None) -> dict:
            """Search file contents using regular expressions.

            Args:
                pattern: The regex pattern to search for in file contents.
                path: The directory to search in. Defaults to current working directory.
                include: File pattern to include (e.g. ``*.py``, ``*.{ts,tsx}``).

            Returns:
                dict with ``{status, message, data, usage}``.
            """
            try:
                search = path or os.getcwd()
                results: list[str] = []

                for root, _dirs, files in os.walk(search):
                    if include:
                        files = [f for f in files if fnmatch.fnmatch(f, include)]
                    for f in files:
                        fpath = os.path.join(root, f)
                        try:
                            with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                                for i, line in enumerate(fh, 1):
                                    if re.search(pattern, line):
                                        results.append(f"{fpath}:{i}: {line.rstrip()}")
                                        if len(results) >= 100:
                                            break
                        except (OSError, UnicodeDecodeError) as e:
                            log_error(str(e), source="tools.py:grep")
                            continue
                        if len(results) >= 100:
                            break
                    if len(results) >= 100:
                        break

                if not results:
                    return make_success_response(
                        message="No files found.",
                        data=[],
                        usage=zero_usage(),
                    )

                output = "\n".join(results[:100])
                if len(results) > 100:
                    output += (
                        f"\n(Results are truncated: {len(results)} matches found. "
                        "Consider using a more specific pattern.)"
                    )

                return make_success_response(
                    message=f"{len(results)} match(es) found.",
                    data=output,
                    usage=zero_usage(),
                )
            except Exception as e:
                logger.exception("Error in grep: %s", e)
                log_error(str(e), source="tools.py:grep")
                return make_error_response(
                    message=f"Error in grep: {e}",
                    usage=zero_usage(),
                )
