"""Workflow runs: start, retry, resume, cancel, judge and notify.

A run is one execution of a workflow, started by the play button (``source``
``"play"``) or by an agent through the ``workflow`` tool (``"tool"``). Each
run:

1. Creates a session (parent of the child sessions of its agent nodes). A
   run started with play is a top-level session titled
   ``<name> — dd/mm/yyyy HH:mm``; a run called by an agent hangs from the
   caller's session.
2. Executes in the background (``asyncio`` task), in parallel with the chat,
   the scheduler and other workflows.
3. Retries up to :data:`~backend.agent.utils.workflow_db.MAX_ATTEMPTS` times
   in total with exponential backoff. Every retry (and the resume after a
   backend crash) continues from the first node without a committed result.
4. When every node completed, a judge (decision model if ready, otherwise an
   LLM) decides whether the run finished well, receiving the node results.
5. A run that fails definitively gets a plain-language explanation written
   by an LLM; the technical error goes to ``error_log``.
6. Runs started with play notify the user (persisted notification + event).

Local time everywhere (``datetime.now()``).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from backend.agent.utils import workflow_db
from backend.agent.utils.error_logger import log_error, reset_error_context, set_error_context
from backend.agent.utils.notifications_helpers import notify
from backend.agent.utils.workflow_db import MAX_ATTEMPTS

logger = logging.getLogger(__name__)

_RESULT_NOTIFICATION_LIMIT = 1000
"""Characters of the final answer carried by the success notification."""


class _ActiveRun:
    """Handle of a run executing in this process."""

    def __init__(self, name: str, cancel_event: asyncio.Event) -> None:
        self.name = name
        self.cancel_event = cancel_event
        self.task: asyncio.Task | None = None


class WorkflowService:
    """Start, track, cancel and resume workflow runs."""

    def __init__(self) -> None:
        self._active: dict[str, _ActiveRun] = {}

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def active_run_id(self, name: str) -> str | None:
        """Return the id of the run of ``name`` executing now, if any."""
        for run_id, active in self._active.items():
            if active.name == name:
                return run_id
        return None

    def is_running(self, name: str) -> bool:
        """Return whether a run of ``name`` is executing now."""
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
            source: ``"play"`` or ``"tool"``.
            parent_session_id: Session of the calling agent (tool only).

        Returns:
            ``{"ok": True, "run_id", "session_id", "task"}`` when started, or
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

        from backend.instances import session_manager

        run_id = workflow_db.create_run(name, None, parent_session_id, source)
        if run_id is None:
            return {"ok": False, "code": "error", "message": "No se pudo registrar la ejecución."}
        session_id = run_id
        try:
            created = session_manager.create_session(
                session_id,
                metadata={"source": "workflow", "workflow": name, "run_id": run_id},
                parent_id=parent_session_id,
            )
            if created.get("status") != "success":
                raise RuntimeError(str(created.get("message")))
            workflow_db.set_run_session(run_id, session_id)
            session_manager.update_session_title(
                session_id, f"{name} — {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            )
            session_manager.save_message(
                session_id, "user",
                content=f"Ejecución del workflow «{name}».",
                turn_number=1, step=None,
            )
        except Exception as exc:
            log_error(str(exc), source="workflow_service.py:start_run(session)")
            workflow_db.finish_run(run_id, "error", None, "No se pudo abrir la sesión de la ejecución.")
            return {"ok": False, "code": "error", "message": "No se pudo abrir la sesión de la ejecución."}

        task = self._launch(run_id, name, workflow, session_id, source, 1)
        await self._emit_run(run_id, name, "running", 1, session_id)
        return {"ok": True, "run_id": run_id, "session_id": session_id, "task": task}

    def _launch(
        self,
        run_id: str,
        name: str,
        workflow: dict[str, Any],
        session_id: str,
        source: str,
        start_attempt: int,
    ) -> asyncio.Task:
        """Create and register the background task of a run."""
        active = _ActiveRun(name, asyncio.Event())
        self._active[run_id] = active
        task = asyncio.create_task(
            self._execute(run_id, name, workflow, session_id, source, active.cancel_event, start_attempt)
        )
        active.task = task
        return task

    async def run_and_wait(
        self, name: str, parent_session_id: str | None = None
    ) -> dict[str, Any]:
        """Run a workflow on behalf of an agent and wait for its outcome.

        Args:
            name: Workflow name.
            parent_session_id: Session of the calling agent.

        Returns:
            ``{"status": "success" | "error" | "cancelled", "run_id",
            "session_id", "result", "error_text"}``; start failures come back
            as ``status="error"`` with the friendly message in ``error_text``.
        """
        started = await self.start_run(name, source="tool", parent_session_id=parent_session_id)
        if not started.get("ok"):
            return {
                "status": "error", "run_id": None, "session_id": None,
                "result": "", "error_text": started.get("message", ""),
            }
        try:
            # Shielded: the cancellation of the caller must not look like a
            # backend shutdown to the run (which would leave it "running").
            return await asyncio.shield(started["task"])
        except asyncio.CancelledError:
            await self.cancel(started["run_id"])
            raise

    # ------------------------------------------------------------------
    # Cancel / shutdown / resume
    # ------------------------------------------------------------------

    async def cancel(self, run_id: str) -> bool:
        """Cancel a running run (it is persisted as ``cancelled``).

        Returns:
            ``True`` when the run was executing and the cancellation was sent.
        """
        active = self._active.get(run_id)
        if active is None or active.task is None:
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
            session_id = run.get("session_id") or run_id
            source = run.get("source") or "play"
            try:
                workflow_db.fail_open_steps(run_id, "Interrumpido por el cierre del backend.")
                loaded = load_workflow(name)
                attempt = int(run.get("attempt") or 1)
                if loaded.get("status") != "success":
                    await self._finalize_error(
                        run_id, name, session_id, source, {},
                        [{"node": "-", "type": "workflow", "error": str(loaded.get("message"))}],
                        attempt,
                    )
                    continue
                if source == "tool":
                    # The agent that was waiting for the result is gone; its own
                    # frontier brings the pending call back and it can ask again.
                    await self._finalize_error(
                        run_id, name, session_id, source, loaded["data"],
                        [{"node": "-", "type": "workflow",
                          "error": "La ejecución se interrumpió porque el backend se cerró."}],
                        attempt,
                        explanation="La ejecución se interrumpió porque la aplicación se cerró.",
                    )
                    continue
                if attempt >= MAX_ATTEMPTS:
                    await self._finalize_error(
                        run_id, name, session_id, source, loaded["data"],
                        [{"node": "-", "type": "workflow",
                          "error": "La ejecución se interrumpió y ya no quedaban intentos."}],
                        attempt,
                    )
                    continue
                self._launch(run_id, name, loaded["data"], session_id, source, attempt + 1)
                resumed += 1
            except Exception as exc:
                log_error(str(exc), source="workflow_service.py:resume_interrupted")
        return resumed

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def _execute(
        self,
        run_id: str,
        name: str,
        workflow: dict[str, Any],
        session_id: str,
        source: str,
        cancel_event: asyncio.Event,
        start_attempt: int,
    ) -> dict[str, Any]:
        """Task body: attempts, judge and finalization of a run."""
        token = set_error_context(session_id=session_id, turn_number=1)
        try:
            return await self._attempts(
                run_id, name, workflow, session_id, source, cancel_event, start_attempt
            )
        except asyncio.CancelledError:
            if not cancel_event.is_set():
                # Backend shutdown: leave the run as "running" so the next
                # start resumes it from the last committed node.
                raise
            return await self._finalize_cancelled(run_id, name, session_id)
        except Exception as exc:
            log_error(str(exc), source="workflow_service.py:_execute")
            attempt = (workflow_db.get_run(run_id) or {}).get("attempt") or 1
            return await self._finalize_error(
                run_id, name, session_id, source, workflow,
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
        session_id: str,
        source: str,
        cancel_event: asyncio.Event,
        start_attempt: int,
    ) -> dict[str, Any]:
        """Run attempts with exponential backoff until success or exhaustion."""
        from backend.agent.utils.workflow_judge import explain_failure, judge_run
        from backend.agent.utils.workflow_runner import WorkflowRunner
        from backend.instances import agent, session_manager

        runner = WorkflowRunner(agent=agent, session_manager=session_manager)
        outcome: dict[str, Any] = {"status": "error", "failures": [], "results": {}, "final_text": ""}
        attempt = start_attempt
        while attempt <= MAX_ATTEMPTS:
            workflow_db.set_run_attempt(run_id, attempt)
            if attempt > 1:
                await self._emit_run(run_id, name, "running", attempt, session_id)
            outcome = await runner.execute_attempt(run_id, session_id, workflow, attempt, cancel_event)
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
            return await self._finalize_cancelled(run_id, name, session_id)

        if outcome["status"] == "success":
            ok, reason = await judge_run(
                agent, name, run_id, str(workflow.get("description", "")),
                workflow.get("nodes", []), outcome["results"], outcome["final_text"],
            )
            if ok:
                return await self._finalize_success(
                    run_id, name, session_id, source, workflow, outcome["final_text"]
                )
            return await self._finalize_error(
                run_id, name, session_id, source, workflow,
                [{"node": "-", "type": "juez", "error": reason}],
                attempt, explanation=reason,
            )

        return await self._finalize_error(
            run_id, name, session_id, source, workflow, outcome["failures"], attempt,
            explainer=explain_failure,
        )

    @staticmethod
    async def _backoff(cancel_event: asyncio.Event, seconds: float) -> bool:
        """Wait ``seconds`` between attempts; ``True`` when cancelled meanwhile."""
        try:
            await asyncio.wait_for(cancel_event.wait(), timeout=seconds)
            return True
        except asyncio.TimeoutError:
            return False

    # ------------------------------------------------------------------
    # Finalization
    # ------------------------------------------------------------------

    def _save_final_message(
        self, session_id: str, workflow: dict[str, Any], content: str, status: str
    ) -> None:
        """Store the closing message of a run in its session."""
        try:
            from backend.instances import session_manager

            steps = [n.get("step", 1) for n in workflow.get("nodes", []) if isinstance(n, dict)]
            session_manager.save_message(
                session_id, "assistant", content=content,
                turn_number=1, step=max(steps) if steps else 1,
                status=status, message="" if status == "success" else content,
            )
        except Exception as exc:
            log_error(str(exc), source="workflow_service.py:save_final")

    async def _finalize_success(
        self,
        run_id: str,
        name: str,
        session_id: str,
        source: str,
        workflow: dict[str, Any],
        final_text: str,
    ) -> dict[str, Any]:
        """Close a run as successful and notify."""
        answer = final_text.strip() or "Workflow completado sin respuesta final."
        self._save_final_message(session_id, workflow, answer, "success")
        workflow_db.finish_run(run_id, "success", answer, None)
        if source == "play":
            await notify(
                kind="workflow", workflow_name=name, title=name, status="success",
                message=answer[:_RESULT_NOTIFICATION_LIMIT], run_id=run_id,
                session_id=session_id,
            )
        await self._emit_run(run_id, name, "success", None, session_id)
        return {"status": "success", "run_id": run_id, "session_id": session_id,
                "result": answer, "error_text": ""}

    async def _finalize_error(
        self,
        run_id: str,
        name: str,
        session_id: str,
        source: str,
        workflow: dict[str, Any],
        failures: list[dict[str, str]],
        attempts: int,
        explanation: str | None = None,
        explainer=None,
    ) -> dict[str, Any]:
        """Close a run as failed: explain it in plain language and notify.

        Args:
            explanation: Ready-made user text (judge reason); skips the LLM.
            explainer: ``explain_failure`` coroutine function; when ``None``
                (and no explanation) the generic text is used.
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
        self._save_final_message(session_id, workflow, text, "error")
        workflow_db.finish_run(run_id, "error", None, text)
        if source == "play":
            await notify(
                kind="workflow", workflow_name=name, title=name, status="error",
                message=text, run_id=run_id, session_id=session_id,
            )
        await self._emit_run(run_id, name, "error", None, session_id)
        return {"status": "error", "run_id": run_id, "session_id": session_id,
                "result": "", "error_text": text}

    async def _finalize_cancelled(self, run_id: str, name: str, session_id: str) -> dict[str, Any]:
        """Close a run cancelled by the user (persisted as ``cancelled``)."""
        workflow_db.fail_open_steps(run_id, "Cancelado por el usuario.")
        self._save_final_message(session_id, {}, "Ejecución cancelada por el usuario.", "error")
        workflow_db.finish_run(run_id, "cancelled", None, None)
        await self._emit_run(run_id, name, "cancelled", None, session_id)
        return {"status": "cancelled", "run_id": run_id, "session_id": session_id,
                "result": "", "error_text": ""}

    async def _emit_run(
        self, run_id: str, name: str, status: str, attempt: int | None, session_id: str | None
    ) -> None:
        """Tell the web UI that a run changed state."""
        try:
            from backend.event_bus import event_bus

            await event_bus.emit({
                "type": "workflow_run",
                "content": {
                    "run_id": run_id, "workflow": name, "status": status,
                    "attempt": attempt, "session_id": session_id,
                },
            })
        except Exception as exc:
            log_error(str(exc), source="workflow_service.py:_emit_run")


# Module-level singleton used by the routes, the tool and the lifespan.
workflow_service = WorkflowService()
