"""HelpMixin — native tool help."""

import logging

from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)


class HelpMixin:
    async def help(self) -> dict:
            """Read the agent's internal documentation about how it works.

            Use this tool when the user asks for help with how the agent works,
            or asks you to explain how to create tools, sub-agents, etc.

            Returns the content of the ``help.jinja`` prompt, which explains how to
            create tools, skills, agents, change models, configure the context
            window, verbose mode, etc.

            Returns:
                dict with ``{status, message, data, usage}``.
            """
            try:
                from backend.instances import agent

                try:
                    content = agent.prompt("help")
                except FileNotFoundError:
                    return make_error_response(
                        message="No se encontró el archivo de documentación interna (help.jinja).",
                        usage=zero_usage(),
                    )
                return make_success_response(
                    message="Documentación interna cargada.",
                    data=content,
                    usage=zero_usage(),
                )
            except Exception as e:
                logger.exception("Error in help: %s", e)
                log_error(str(e), source="tools.py:help")
                return make_error_response(
                    message=f"Error cargando documentación interna: {e}",
                    usage=zero_usage(),
                )
