"""WorkflowMixin — native tool workflow."""

import logging

from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)


class WorkflowMixin:
    """Native tool ``workflow``: run a saved workflow and return its result."""
    async def workflow(self, name: str) -> dict:
        """Run a saved workflow and return its result.

        A workflow is a deterministic flow of steps defined by the user. It
        runs to completion (with its own retries) and its final answer is
        returned wrapped in an XML block, like ``task`` does for sub-agents.
        The permission to call each workflow is granted per agent, in the
        ``workflows`` block of its permissions.

        Args:
            name: Name of the workflow to run.

        Returns:
            dict with ``{status, message, data, usage}``. ``data`` is the XML
            result block consumed by the calling agent as a tool result.
        """
        from backend.agent.utils.loop_helpers import _tool_call_ctx
        from backend.agent.utils.workflow_service import workflow_service

        snapshot = _tool_call_ctx.get()
        if snapshot is not None:
            parent_id = snapshot.get("parent_session_id", getattr(self, "_current_session_id", None))
        else:
            parent_id = getattr(self, "_current_session_id", None)

        try:
            outcome = await workflow_service.run_and_wait(name, parent_session_id=parent_id)
        except Exception as exc:
            logger.exception("Error ejecutando el workflow '%s': %s", name, exc)
            log_error(str(exc), source="tools.py:workflow")
            return make_error_response(
                message=f"No se pudo ejecutar el workflow '{name}'.",
                usage=zero_usage(),
            )

        status = outcome.get("status")
        if status == "success":
            xml = (
                f'<workflow id="{outcome.get("session_id")}" name="{name}" state="completed">'
                f"<workflow_result>{outcome.get('result', '')}</workflow_result>"
                f"</workflow>"
            )
            return make_success_response(
                message=f"Workflow '{name}' ejecutado.",
                data=xml,
                usage=zero_usage(),
            )
        if status == "cancelled":
            return make_error_response(
                message=f"La ejecución del workflow '{name}' fue cancelada.",
                usage=zero_usage(),
            )
        return make_error_response(
            message=outcome.get("error_text") or f"El workflow '{name}' no pudo completarse.",
            usage=zero_usage(),
        )
