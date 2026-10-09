"""GlobMixin — native tool glob."""

import glob as glob_module
import logging
import os

from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)


class GlobMixin:
    async def glob(self, pattern: str, path: str | None = None) -> dict:
            """Fast file pattern matching tool.

            Supports glob patterns like ``**/*.js`` or ``src/**/*.ts``.

            Args:
                pattern: The glob pattern to match files against.
                path: The directory to search in. Defaults to current working directory.

            Returns:
                dict with ``{status, message, data, usage}``.
            """
            try:
                search = path or os.getcwd()
                if not os.path.isdir(search):
                    return make_error_response(
                        message=f"The path must be a directory: {search}",
                        usage=zero_usage(),
                    )

                files = glob_module.glob(pattern, root_dir=search, recursive=True)
                limit = 100
                results = [os.path.normpath(os.path.join(search, f)) for f in sorted(files)]

                if not results:
                    return make_success_response(
                        message="No files found.",
                        data=[],
                        usage=zero_usage(),
                    )

                output = "\n".join(results[:limit])
                if len(results) > limit:
                    output += (
                        f"\n(Results are truncated: showing first {limit}. "
                        "Consider using a more specific pattern.)"
                    )

                return make_success_response(
                    message=f"{min(len(results), limit)} file(s) found.",
                    data=output,
                    usage=zero_usage(),
                )
            except Exception as e:
                logger.exception("Error in glob: %s", e)
                log_error(str(e), source="tools.py:glob")
                return make_error_response(
                    message=f"Error in glob: {e}",
                    usage=zero_usage(),
                )
