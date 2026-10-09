"""QueryModelCapabilitiesMixin — native tool query_model_capabilities."""

import json
import logging

from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)


class QueryModelCapabilitiesMixin:
    async def query_model_capabilities(self, provider: str, model: str) -> dict:
            """Query model capabilities from the local catalog without huge context.

            Thin wrapper over ``GET /config/models/capabilities``: calls the
            endpoint function in-process and returns its payload under the
            unified contract, so creator agents can validate frontmatter
            parameters instead of inventing them.

            Args:
                provider: Provider name (e.g. ``"openrouter"``,
                    ``"google"``, ``"LOCAL"``).
                model: Model identifier (e.g. ``"qwen/qwen3-32b"``).

            Returns:
                dict with ``{status, message, data, usage}``. On success,
                ``data`` holds the endpoint payload (``reasoning_supported``,
                ``reasoning_options``, ``reasoning_type``,
                ``response_format_supported``, ``temperature_supported``,
                ``tool_call_supported``, ``found``, ...).
            """
            try:
                prov = (provider or "").strip()
                model_id = (model or "").strip()
                if not prov or not model_id:
                    return make_error_response(
                        message="Provider and model are required.",
                        usage=zero_usage(),
                    )

                from backend.routes.config import (
                    get_model_capabilities as capabilities_endpoint,
                )

                resp = await capabilities_endpoint(model=model_id, provider=prov)
                payload = json.loads(resp.body.decode("utf-8"))
                if resp.status_code != 200 or payload.get("status") != "success":
                    return make_error_response(
                        message=payload.get("message", "Error querying capabilities."),
                        usage=zero_usage(),
                    )
                if payload.get("found") is False:
                    return make_error_response(
                        message=(
                            f"Model '{model_id}' not found for provider "
                            f"'{prov}' in the local catalog."
                        ),
                        usage=zero_usage(),
                    )
                return make_success_response(
                    message=f"Capabilities for '{prov}/{model_id}'.",
                    data=payload,
                    usage=zero_usage(),
                )
            except Exception as e:
                logger.exception("Error in query_model_capabilities: %s", e)
                log_error(str(e), source="tools.py:query_model_capabilities")
                return make_error_response(
                    message=f"Error querying model capabilities: {e}",
                    usage=zero_usage(),
                )
