"""SaveUserMemoryMixin — native tool save_user_memory."""

import logging

from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage

logger = logging.getLogger(__name__)


class SaveUserMemoryMixin:
    """Native tool ``save_user_memory``: save a concrete user preference."""

    async def save_user_memory(self, text: str) -> dict:
        """Save a concrete user preference for future turns.

        Use it only when the user states an explicit preference or
        instruction to remember (e.g. language, tone, format, timezone,
        company, role). Do not save vague comments, opinions, secrets
        or inferred data. If in doubt, ask the user first instead of
        saving.

        Args:
            text: Short literal preference to remember (max 500 chars).

        Returns:
            dict with ``{status, message, data, usage}``.
        """
        try:
            from backend.agent.utils.rag_helpers import add_user_memory

            if not text or not text.strip():
                return make_error_response(
                    message="La preferencia está vacía.",
                    usage=zero_usage(),
                )
            return add_user_memory(text.strip(), origin="auto")
        except Exception as e:
            logger.exception("Error in save_user_memory: %s", e)
            return make_error_response(
                message="Error guardando la preferencia.",
                usage=zero_usage(),
            )
