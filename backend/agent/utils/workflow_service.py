"""Workflow runs: start, retry, resume, cancel, judge and notify.

A run is one execution of a workflow, started by the play button (``source``
``"play"``), by an agent through the ``workflow`` tool (``"tool"``) or by the
scheduler (``"schedule"``, a workflow whose YAML has a ``schedule`` block). Each
run:

1. Never opens a session nor writes in ``messages``: everything it does (its
   nodes, the decision model or LLM verdict, the output and the explanation of a
   failure, with their tokens, cost and time) is a row of ``workflow_runs``, and
   the commits to resume it go to ``workflow_run_steps``. The result reaches the
   user as a notification; only "Revisar con el agente" opens a session.
2. Executes in the background (``asyncio`` task), in parallel with the chat,
   the scheduler and other workflows.
3. Retries up to :data:`~backend.agent.utils.workflow_db.MAX_ATTEMPTS` times
   in total with exponential backoff. Every retry (and the resume after a
   backend crash) continues from the first node without a committed result.
4. When every node completed, a judge (decision model if ready, otherwise an
   LLM) decides whether the run finished well, receiving the node results.
5. A run that fails definitively gets a plain-language explanation written
   by an LLM; the technical error goes to ``error_log``.
6. Runs started with play or by the scheduler notify the user (persisted notification +
   event); the scheduled ones also go to Telegram.

Local time everywhere (``datetime.now()``).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from backend.agent.utils import workflow_db
from backend.agent.utils.error_logger import log_error, reset_error_context, set_error_context
from backend.agent.utils.notifications_helpers import notify, notify_telegram
from backend.agent.utils.workflow_db import MAX_ATTEMPTS

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

_RESULT_NOTIFICATION_LIMIT = 1000
"""Characters of the final answer carried by the success notification."""


def _shorten(text: str, limit: int = _RESULT_NOTIFICATION_LIMIT) -> str:
    """Cut a text to a limit at a line or word boundary, marking the cut.

    Args:
        text: Text to shorten.
        limit: Maximum number of characters before the cut mark.

    Returns:
        The text unchanged when it fits, otherwise its beginning followed by an ellipsis.
    """
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    boundary = max(cut.rfind("\n"), cut.rfind(" "))
    if boundary >= limit // 2:
        cut = cut[:boundary]
    return cut.rstrip() + "…"


def _workspace_note(name: str) -> str:
    """Describe the working folder of a workflow when it has files.

    Args:
        name: Workflow name.

    Returns:
        A line with the path of the folder, or an empty string when it is empty or unavailable.
    """
    try:
        from backend.agent.utils.config_dir import get_workspace_dir

        folder = get_workspace_dir(name)
        if any(folder.iterdir()):
            return f"Carpeta de trabajo: {folder}"
    except Exception as exc:
        log_error(str(exc), source="workflow_service.py:workspace_note")
    return ""


class _ActiveRun:
    """Handle of a run executing in this process."""

    def __init__(self, name: str, cancel_event: asyncio.Event) -> None:
        """Create the handle of a run.

        Args:
            name: Workflow name.
            cancel_event: Event the run checks to know the user cancelled it.
        """
        self.name = name
        self.cancel_event = cancel_event
        self.task: asyncio.Task | None = None


class WorkflowService:
    """Start, track, cancel and resume workflow runs."""

    def __init__(self) -> None:
        """Create the service with no run in memory."""
        self._active: dict[str, _ActiveRun] = {}

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def active_run_id(self, name: str) -> str | None:
        """Find the run of a workflow that is executing in this process.

        Args:
            name: Workflow name.

        Returns:
            The run id, or ``None`` when the workflow is not running.
        """
        for run_id, active in self._active.items():
            if active.name == name:
                return run_id
        return None

    def is_running(self, name: str) -> bool:
        """Check whether a run of a workflow is executing in this process.

        Args:
            name: Workflow name.

        Returns:
            ``True`` when a run of that workflow is executing.
        """
        return self.active_run_id(name) is not None

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    async def start_run(
        self,
        name: str,
        source: str = "play",
        parent_session_id: str | None = None,
    ) -> dict[str, Any]:
        """Validate a workflow and launch it in the background.

        Args:
            name: Workflow name (the id).
            source: ``"play"``, ``"tool"`` or ``"schedule"``.
            parent_session_id: Session of the calling agent (tool only).

        Returns:
            ``{"ok": True, "run_id", "task"}`` when started, or
            ``{"ok": False, "code", "message"}`` with ``code`` one of
            ``not_found``, ``invalid``, ``missing_refs``, ``conflict`` or
            ``error``. The message is friendly, ready for the user.
        """
        from backend.agent.utils.workflow_loader import load_workflow
        from backend.agent.utils.workflows_helpers import verificar_refs

        loaded = load_workflow(name)
        if loaded.get("status") != "success":
            message = str(loaded.get("message") or f"Workflow '{name}' inválido.")
            code = "not_found" if "no existe" in message else "invalid"
            return {"ok": False, "code": code, "message": message}
        workflow = loaded["data"]

        if self.is_running(name):
            return {
                "ok": False, "code": "conflict",
                "message": f"El workflow «{name}» ya se está ejecutando.",
            }

        try:
            refs = verificar_refs(workflow)
        except Exception as exc:
            log_error(str(exc), source="workflow_service.py:start_run(refs)")
            refs = {"ok": False, "faltantes": [{
                "detalle": "No se pudieron verificar los recursos del workflow.",
            }]}
        if not refs.get("ok"):
            detail = "; ".join(
                str(f.get("detalle", "")) for f in refs.get("faltantes", []) if isinstance(f, dict)
            ) or "Faltan recursos del workflow."
            return {
                "ok": False, "code": "missing_refs",
                "message": f"No se puede ejecutar el workflow «{name}»: {detail} Crealos o revisá el workflow.",
            }

        run_id = workflow_db.create_run(name, parent_session_id, source)
        if run_id is None:
            return {"ok": False, "code": "error", "message": "No se pudo registrar la ejecución."}

        task = self._launch(run_id, name, workflow, source, 1)
        await self._emit_run(run_id, name, "running", 1)
        return {"ok": True, "run_id": run_id, "task": task}

    def _launch(
        self,
        run_id: str,
        name: str,
        workflow: dict[str, Any],
        source: str,
        start_attempt: int,
    ) -> asyncio.Task:
        """Create and register the background task of a run.

        Args:
            run_id: Run identifier.
            name: Workflow name.
            workflow: Validated workflow data.
            source: ``"play"``, ``"tool"`` or ``"schedule"``.
            start_attempt: Attempt the task starts from (1..3).

        Returns:
            The task that executes the run.
        """
        active = _ActiveRun(name, asyncio.Event())
        self._active[run_id] = active
        task = asyncio.create_task(
            self._execute(run_id, name, workflow, source, active.cancel_event, start_attempt)
        )
        active.task = task
        return task

    # ------------------------------------------------------------------
    # Cancel / shutdown / resume
    # ------------------------------------------------------------------

    async def cancel(self, run_id: str) -> bool:
        """Cancel a run (it is persisted as ``cancelled``).

        A run that is not executing in this process but is still ``running`` in the
        database (the backend restarted) is closed as cancelled so the UI stops
        waiting for it.

        Args:
            run_id: Run identifier.

        Returns:
            ``True`` when the run was cancelled, ``False`` when there is nothing to cancel.
        """
        active = self._active.get(run_id)
        if active is None or active.task is None:
            # Not executing in this process (the backend restarted while the
            # run was open): close the orphan row so the UI stops waiting.
            run = workflow_db.get_run(run_id)
            if run and run.get("status") == "running":
                await self._finalize_cancelled(run_id, run["workflow_name"])
                return True
            return False
        active.cancel_event.set()
        active.task.cancel()
        return True

    async def shutdown(self) -> None:
        """Stop the tasks of this process leaving their runs as ``running``.

        The next start resumes them from the last committed node.
        """
        tasks = [a.task for a in self._active.values() if a.task is not None]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def resume_interrupted(self) -> int:
        """Resume the runs a backend stop or crash left as ``running``.

        The nodes that were in flight are marked as failed and executed
        again. The interrupted attempt counts: a run with all its attempts
        consumed is closed as failed.

        Returns:
            Number of runs resumed.
        """
        from backend.agent.utils.workflow_loader import load_workflow

        resumed = 0
        for run in workflow_db.list_running_runs():
            run_id = run["id"]
            if run_id in self._active:
                continue
            name = run["workflow_name"]
            source = run.get("source") or "play"
            try:
                workflow_db.fail_open_steps(run_id, "Interrumpido por el cierre del backend.")
                loaded = load_workflow(name)
                attempt = int(run.get("attempt") or 1)
                if loaded.get("status") != "success":
                    await self._finalize_error(
                        run_id, name, source, {},
                        [{"node": "-", "type": "workflow", "error": str(loaded.get("message"))}],
                        attempt,
                    )
                    continue
                if source == "tool":
                    # The agent that was waiting for the result is gone; its own
                    # frontier brings the pending call back and it can ask again.
                    await self._finalize_error(
                        run_id, name, source, loaded["data"],
                        [{"node": "-", "type": "workflow",
                          "error": "La ejecución se interrumpió porque el backend se cerró."}],
                        attempt,
                        explanation="La ejecución se interrumpió porque la aplicación se cerró.",
                    )
                    continue
                if attempt >= MAX_ATTEMPTS:
                    await self._finalize_error(
                        run_id, name, source, loaded["data"],
                        [{"node": "-", "type": "workflow",
                          "error": "La ejecución se interrumpió y ya no quedaban intentos."}],
                        attempt,
                    )
                    continue
                self._launch(run_id, name, loaded["data"], source, attempt + 1)
                resumed += 1
            except Exception as exc:
                log_error(str(exc), source="workflow_service.py:resume_interrupted")
        return resumed

    # ------------------------------------------------------------------
    # Notification
    # ------------------------------------------------------------------

    @staticmethod
    async def _notify_finished(
        source: str,
        name: str,
        status: str,
        message: str,
        run_id: str,
        description: str,
    ) -> None:
        """Notify the user that a run ended (not the runs called by an agent).

        A played run notifies as ``workflow``. A scheduled run notifies as
        ``schedule`` and is also sent to Telegram.

        Args:
            source: ``"play"``, ``"tool"`` or ``"schedule"``.
            name: Workflow name.
            status: ``"success"`` or ``"error"``.
            message: Short text of the result or the explanation of the failure.
            run_id: Run identifier.
            description: Description of the workflow (what the task does).
        """
        if source not in ("play", "schedule"):
            return
        await notify(
            kind="workflow" if source == "play" else "schedule",
            workflow_name=name, title=name, status=status, message=message,
            run_id=run_id,
        )
        if source == "schedule":
            await notify_telegram(
                status, description, message, datetime.now().strftime("%d/%m/%Y %H:%M")
            )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def _execute(
        self,
        run_id: str,
        name: str,
        workflow: dict[str, Any],
        source: str,
        cancel_event: asyncio.Event,
        start_attempt: int,
    ) -> dict[str, Any]:
        """Run the task body: attempts, output, judge and finalization of a run.

        Args:
            run_id: Run identifier.
            name: Workflow name.
            workflow: Validated workflow data.
            source: ``"play"`` or ``"tool"``.
            cancel_event: Set when the user cancels the run.
            start_attempt: Attempt the run starts from (1..3).

        Returns:
            The outcome ``{status, run_id, result, error_text}``.
        """
        token = set_error_context(turn_number=1)
        try:
            return await self._attempts(
                run_id, name, workflow, source, cancel_event, start_attempt
            )
        except asyncio.CancelledError:
            if not cancel_event.is_set():
                # Backend shutdown: leave the run as "running" so the next
                # start resumes it from the last committed node.
                raise
            return await self._finalize_cancelled(run_id, name)
        except Exception as exc:
            log_error(str(exc), source="workflow_service.py:_execute")
            attempt = (workflow_db.get_run(run_id) or {}).get("attempt") or 1
            return await self._finalize_error(
                run_id, name, source, workflow,
                [{"node": "-", "type": "workflow", "error": str(exc)}], int(attempt),
            )
        finally:
            self._active.pop(run_id, None)
            try:
                reset_error_context(token)
            except Exception:
                pass

    async def _attempts(
        self,
        run_id: str,
        name: str,
        workflow: dict[str, Any],
        source: str,
        cancel_event: asyncio.Event,
        start_attempt: int,
    ) -> dict[str, Any]:
        """Run attempts with exponential backoff until success or exhaustion.

        When every node completes, the output is generated from all node
        results (the raw text of the final node is only a fallback) and it
        is judged.

        Args:
            run_id: Run identifier.
            name: Workflow name.
            workflow: Validated workflow data.
            source: ``"play"`` or ``"tool"``.
            cancel_event: Set when the user cancels the run.
            start_attempt: Attempt the run starts from (1..3).

        Returns:
            The outcome ``{status, run_id, result, error_text}``.
        """
        from backend.agent.utils.workflow_judge import explain_failure, generate_output, judge_run
        from backend.agent.utils.workflow_runner import WorkflowRunner
        from backend.instances import agent

        runner = WorkflowRunner(agent=agent)
        outcome: dict[str, Any] = {"status": "error", "failures": [], "results": {}, "final_text": ""}
        attempt = start_attempt
        while attempt <= MAX_ATTEMPTS:
            workflow_db.set_run_attempt(run_id, attempt)
            if attempt > 1:
                await self._emit_run(run_id, name, "running", attempt)
            outcome = await runner.execute_attempt(run_id, workflow, attempt, cancel_event)
            if outcome["status"] != "error":
                break
            for failure in outcome["failures"]:
                log_error(
                    f"Workflow '{name}' (run {run_id}, intento {attempt}): nodo "
                    f"'{failure['node']}' ({failure['type']}) falló: {failure['error']}",
                    source="workflow_service.py:attempt_failed",
                )
            if attempt >= MAX_ATTEMPTS:
                break
            if await self._backoff(cancel_event, 2 ** attempt):
                outcome = {**outcome, "status": "cancelled"}
                break
            attempt += 1

        if outcome["status"] == "cancelled":
            return await self._finalize_cancelled(run_id, name)

        if outcome["status"] == "success":
            # The final node (``final: true``) aggregates everything: the
            # report is always generated from all node results, so a final
            # tool/run node (raw data) becomes a real report instead of a
            # raw dump. The raw text of the final node is only kept when
            # generation fails.
            generated = await generate_output(
                agent, name, run_id, str(workflow.get("description", "")),
                workflow.get("nodes", []), outcome["results"],
            )
            if (generated or "").strip():
                outcome = {**outcome, "final_text": generated}
            ok, reason = await judge_run(
                agent, name, run_id, str(workflow.get("description", "")),
                workflow.get("nodes", []), outcome["results"], outcome["final_text"],
                source=source,
            )
            if ok:
                return await self._finalize_success(
                    run_id, name, source, workflow, outcome["final_text"]
                )
            return await self._finalize_error(
                run_id, name, source, workflow,
                [{"node": "-", "type": "juez", "error": reason}],
                attempt, explanation=reason,
            )

        return await self._finalize_error(
            run_id, name, source, workflow, outcome["failures"], attempt,
            explainer=explain_failure,
        )

    @staticmethod
    async def _backoff(cancel_event: asyncio.Event, seconds: float) -> bool:
        """Wait between attempts.

        Args:
            cancel_event: Set when the user cancels the run.
            seconds: Seconds to wait.

        Returns:
            ``True`` when the run was cancelled meanwhile.
        """
        try:
            await asyncio.wait_for(cancel_event.wait(), timeout=seconds)
            return True
        except asyncio.TimeoutError:
            return False

    # ------------------------------------------------------------------
    # Finalization
    # ------------------------------------------------------------------

    async def _finalize_success(
        self,
        run_id: str,
        name: str,
        source: str,
        workflow: dict[str, Any],
        final_text: str,
    ) -> dict[str, Any]:
        """Close a run as successful and notify.

        Args:
            run_id: Run identifier.
            name: Workflow name.
            source: ``"play"``, ``"tool"`` or ``"schedule"`` (the ``"tool"`` runs do not notify).
            workflow: Workflow data.
            final_text: Output of the run.

        Returns:
            The outcome ``{status, run_id, result, error_text}``.
        """
        answer = final_text.strip() or "Workflow completado sin respuesta final."
        note = _workspace_note(name)
        workflow_db.finish_run(run_id, "success", answer, None)
        workflow_db.delete_run_steps(run_id)
        summary = _shorten(answer)
        await self._notify_finished(
            source, name, "success", f"{note}\n\n{summary}" if note else summary,
            run_id, str(workflow.get("description", "")),
        )
        await self._emit_run(run_id, name, "success", None)
        return {"status": "success", "run_id": run_id, "result": answer, "error_text": ""}

    async def _finalize_error(
        self,
        run_id: str,
        name: str,
        source: str,
        workflow: dict[str, Any],
        failures: list[dict[str, str]],
        attempts: int,
        explanation: str | None = None,
        explainer: Callable[..., Awaitable[str]] | None = None,
    ) -> dict[str, Any]:
        """Close a run as failed: explain it in plain language and notify.

        Args:
            run_id: Run identifier.
            name: Workflow name.
            source: ``"play"``, ``"tool"`` or ``"schedule"`` (the ``"tool"`` runs do not notify).
            workflow: Workflow data.
            failures: One dict per failed node with ``node``, ``type`` and ``error``.
            attempts: Attempts the run consumed.
            explanation: Ready-made user text (judge reason); skips the LLM.
            explainer: Coroutine function that explains the failure with the LLM;
                ``explain_failure`` when ``None`` (used only without ``explanation``).

        Returns:
            The outcome ``{status, run_id, result, error_text}``.
        """
        from backend.agent.utils.workflow_judge import GENERIC_FAILURE_TEXT, explain_failure

        for failure in failures:
            log_error(
                f"Workflow '{name}' (run {run_id}) terminó con error en '{failure.get('node')}' "
                f"({failure.get('type')}): {failure.get('error')}",
                source="workflow_service.py:run_failed",
            )
        text = explanation
        if not text:
            from backend.instances import agent

            text = await (explainer or explain_failure)(
                agent, name, run_id, str(workflow.get("description", "")), failures, attempts,
            ) or GENERIC_FAILURE_TEXT
        workflow_db.finish_run(run_id, "error", None, text)
        await self._notify_finished(
            source, name, "error", text, run_id, str(workflow.get("description", "")),
        )
        await self._emit_run(run_id, name, "error", None)
        return {"status": "error", "run_id": run_id, "result": "", "error_text": text}

    async def _finalize_cancelled(self, run_id: str, name: str) -> dict[str, Any]:
        """Close a run cancelled by the user (persisted as ``cancelled``).

        Args:
            run_id: Run identifier.
            name: Workflow name.

        Returns:
            The outcome ``{status, run_id, result, error_text}``.
        """
        workflow_db.fail_open_steps(run_id, "Cancelado por el usuario.")
        workflow_db.finish_run(run_id, "cancelled", None, None)
        await self._emit_run(run_id, name, "cancelled", None)
        return {"status": "cancelled", "run_id": run_id, "result": "", "error_text": ""}

    async def _emit_run(self, run_id: str, name: str, status: str, attempt: int | None) -> None:
        """Tell the web UI that a run changed state.

        Args:
            run_id: Run identifier.
            name: Workflow name.
            status: New status of the run.
            attempt: Current attempt, when it is running.
        """
        try:
            from backend.event_bus import event_bus

            await event_bus.emit({
                "type": "workflow_run",
                "content": {
                    "run_id": run_id, "workflow": name, "status": status,
                    "attempt": attempt,
                },
            })
        except Exception as exc:
            log_error(str(exc), source="workflow_service.py:_emit_run")


# Module-level singleton used by the routes, the tool and the lifespan.
workflow_service = WorkflowService()
