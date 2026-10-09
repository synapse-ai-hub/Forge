"""WebfetchMixin — native tool webfetch."""

import logging
import re

import httpx
import html2text

from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)


class WebfetchMixin:
    async def webfetch(self, url: str, format: str = "markdown") -> dict:
            """Fetches content from a specified URL.

            Args:
                url: The URL to fetch. HTTP URLs will be upgraded to HTTPS.
                format: The return format. Options: ``"markdown"`` (default), ``"text"``, ``"html"``.

            Returns:
                dict with ``{status, message, data, usage}``.
            """
            try:
                url = url.replace("http://", "https://")
                async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                    resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                    resp.raise_for_status()
                    content = resp.text

                if format == "html":
                    return make_success_response(
                        message="Content fetched successfully.",
                        data=content[:10000],
                        usage=zero_usage(),
                    )
                if format == "text":
                    text = re.sub(r"<[^>]+>", "", content)
                    return make_success_response(
                        message="Content fetched successfully.",
                        data=text[:10000],
                        usage=zero_usage(),
                    )

                # Markdown
                try:
                
                    converter = html2text.HTML2Text()
                    converter.body_width = 0
                    md = converter.handle(content)[:10000]
                    return make_success_response(
                        message="Content fetched successfully.",
                        data=md,
                        usage=zero_usage(),
                    )
                except ImportError as e:
                    log_error(str(e), source="tools.py:webfetch(html2text)")
                    # Fallback: strip tags
                    text = re.sub(r"<[^>]+>", "", content)
                    return make_success_response(
                        message="Content fetched successfully (html2text not available, using text fallback).",
                        data=text[:10000],
                        usage=zero_usage(),
                    )
            except Exception as e:
                logger.exception("Error in webfetch: %s", e)
                log_error(str(e), source="tools.py:webfetch")
                return make_error_response(
                    message=f"Error fetching URL: {e}",
                    usage=zero_usage(),
                )
