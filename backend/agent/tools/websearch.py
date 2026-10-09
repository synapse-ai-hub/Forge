"""WebsearchMixin — native tool websearch."""

import logging

from ddgs import DDGS

from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)


class WebsearchMixin:
    async def websearch(self, query: str, num_results: int = 8) -> dict:
            """Search the web using the configured provider.

            Args:
                query: The search query string.
                num_results: Number of search results to return (default: 8).

            Returns:
                dict with ``{status, message, data, usage}``.
            """
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=num_results))

                if not results:
                    return make_success_response(
                        message="No results found.",
                        data=[],
                        usage=zero_usage(),
                    )

                output = "\n".join(
                    [f"{r['title']}: {r['href']}" for r in results]
                )
                return make_success_response(
                    message=f"{len(results)} result(s) found.",
                    data=output,
                    usage=zero_usage(),
                )
            except Exception as e:
                logger.exception("Error in websearch: %s", e)
                log_error(str(e), source="tools.py:websearch")
                return make_error_response(
                    message=f"Error in websearch: {e}",
                    usage=zero_usage(),
                )
