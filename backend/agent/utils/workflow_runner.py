"""Deterministic DAG runner with barriers, retries, commits and shared state.

Own development, no LangGraph dependency. Patterns taken as reference from
LangGraph PregelRunner: super-step per ``step``, concurrent tasks in the same
super-step, commit per task, retry per node.

Same ``step`` runs in parallel with ``asyncio.gather`` and a barrier.
Different ``step`` runs sequentially.

The runner executes ONE attempt of a run (:meth:`WorkflowRunner.execute_attempt`).
Retries of the whole run, the judge, notifications and persistence of the run
row live in :mod:`backend.agent.utils.workflow_service`. Every node is
committed to ``workflow_run_steps`` (``open`` when dispatched, ``done`` with its
complete result): a later attempt, or a resume after a backend crash, rebuilds
the shared state from the committed nodes and only runs what is missing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from backend.agent.utils import workflow_db

logger = logging.getLogger(__name__)

NODE_MESSAGE_LIMIT = 2000
"""Characters of a node result stored in the run session (the commit row keeps it whole)."""


def _as_text(data: Any) -> str:
    """Return a node result as text (JSON for dicts and lists)."""
    if data is None:
        return ""
    if isinstance(data, (dict, list)):
        try:
            return json.dumps(data, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(data)
    return str(data)


class WorkflowRunner:
    """Execute one attempt of a validated workflow, step by step."""

    def __init__(self, agent, session_manager) -> None:
        """Store shared singletons.

        Args:
            agent: Agent singleton with tools and model resolution.
            session_manager: Session manager for persistence and config.
        """
        self._agent = agent
        self._session_manager = session_manager

    async def execute_attempt(
        self,
        run_id: str,
        session_id: str,
        workflow: dict[str, Any],
        attempt: int,
        cancel_event: asyncio.Event,
    ) -> dict[str, Any]:
        """Run the nodes that are not committed yet.

        Runs under a least-privilege permission snapshot: only the tools the
        validated YAML references. The snapshot is a ``ContextVar`` that is
        reset when the attempt ends, so the ambient permissions are never
        mutated.

        Args:
            run_id: Run identifier (owner of the commit rows).
            session_id: Session that holds the execution.
            workflow: Validated workflow data from the loader.
            attempt: Attempt number (1..3).
            cancel_event: Set when the user cancels the run.

        Returns:
            ``{"status": "success" | "error" | "cancelled", "results": {...},
            "failures": [{"node", "type", "error"}], "final_text": str}``.
        """
        from backend.agent.utils.error_logger import log_error
        from backend.agent.utils.loop_helpers import _tool_call_ctx, execute_tool

        nodes = list(workflow.get("nodes", []))
        allowed: dict[str, str] = {}
        try:
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                kind = node.get("type")
                if kind == "tool" and node.get("tool"):
                    # "task" delegates to sub-agents with its own nested
                    # permission model: never allow it flat here. Use
                    # "agent" nodes for delegation inside workflows.
                    if str(node["tool"]) != "task":
                        allowed[str(node["tool"])] = "allow"
                elif kind == "run":
                    allowed["shell"] = "allow"
                elif kind == "rag":
                    allowed["rag"] = "allow"
        except Exception as exc:
            log_error(str(exc), source="workflow_runner.py:allowset")
        token = _tool_call_ctx.set({"tool_permissions": allowed})
        try:
            return await self._attempt(
                run_id, session_id, workflow, nodes, attempt, cancel_event, execute_tool,
            )
        finally:
            try:
                _tool_call_ctx.reset(token)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Attempt
    # ------------------------------------------------------------------

    def _resume_state(self, run_id: str, nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Rebuild the committed results of a run.

        A node is skipped only when its commit is valid: committed nodes of
        the first step that still has pending work are kept (siblings of a
        failed node), committed nodes of later steps are invalidated because
        they ran without the missing context.

        Args:
            run_id: Run identifier.
            nodes: Normalized workflow nodes.

        Returns:
            Node id → ``{"result": str, "child": str | None}``.
        """
        latest: dict[str, dict[str, Any]] = {}
        for row in workflow_db.load_done_steps(run_id):
            latest[row["node_id"]] = row
        pending_steps = [n["step"] for n in nodes if n["id"] not in latest]
        if pending_steps:
            restart = min(pending_steps)
            workflow_db.invalidate_steps_after(run_id, restart)
            latest = {k: v for k, v in latest.items() if v["step"] <= restart}
        known = {n["id"] for n in nodes}
        return {
            k: {"result": v.get("result") or "", "child": v.get("child_session_id")}
            for k, v in latest.items()
            if k in known
        }

    async def _attempt(
        self,
        run_id: str,
        session_id: str,
        workflow: dict[str, Any],
        nodes: list[dict[str, Any]],
        attempt: int,
        cancel_event: asyncio.Event,
        execute_tool,
    ) -> dict[str, Any]:
        """Execute the pending steps of the DAG (see :meth:`execute_attempt`)."""
        on_failure = workflow.get("on_failure", "continue")
        name = workflow.get("name", "workflow")
        committed = self._resume_state(run_id, nodes)
        state: dict[str, Any] = {
            "input": "",
            "results": {k: v["result"] for k, v in committed.items()},
            "errors": {},
            "workflow": name,
        }
        failures: list[dict[str, str]] = []
        steps = sorted({n["step"] for n in nodes})

        for step in steps:
            if cancel_event.is_set():
                return self._outcome("cancelled", state, failures, nodes)
            group = [n for n in nodes if n["step"] == step]
            pending = [(pos, n) for pos, n in enumerate(group) if n["id"] not in committed]
            if not pending:
                continue

            rows: dict[str, int | None] = {}
            for pos, node in pending:
                rows[node["id"]] = workflow_db.open_step(
                    run_id, attempt, step, pos, node["id"], node["type"], node.get("args"),
                )
            outcomes = await asyncio.gather(
                *(
                    self._run_node(session_id, node, state, cancel_event, execute_tool)
                    for _, node in pending
                )
            )

            aborted = False
            for (_, node), outcome in zip(pending, outcomes):
                row_id = rows.get(node["id"])
                if outcome["status"] == "success":
                    data = _as_text(outcome["data"])
                    workflow_db.commit_step(row_id, data, outcome.get("child_id"))
                    committed[node["id"]] = {"result": data, "child": outcome.get("child_id")}
                    state["results"][node["id"]] = data
                    self._save_node_message(session_id, node, step, data, None)
                elif outcome["status"] == "cancelled":
                    workflow_db.fail_step(row_id, "Cancelado por el usuario.", outcome.get("child_id"))
                else:
                    message = str(outcome.get("message") or "Nodo fallido.")
                    workflow_db.fail_step(row_id, message, outcome.get("child_id"))
                    state["errors"][node["id"]] = message
                    failures.append({"node": node["id"], "type": node["type"], "error": message})
                    self._save_node_message(session_id, node, step, "", message)
                    if on_failure == "abort":
                        aborted = True
            if cancel_event.is_set():
                return self._outcome("cancelled", state, failures, nodes)
            if aborted:
                return self._outcome("error", state, failures, nodes)

        return self._outcome("error" if failures else "success", state, failures, nodes)

    @staticmethod
    def _outcome(
        status: str,
        state: dict[str, Any],
        failures: list[dict[str, str]],
        nodes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build the attempt result, resolving the final answer of the run."""
        final_text = ""
        for node in nodes:
            if node.get("final"):
                final_text = str(state["results"].get(node["id"], "") or "")
        return {
            "status": status,
            "results": dict(state["results"]),
            "failures": failures,
            "final_text": final_text,
        }

    def _save_node_message(
        self,
        session_id: str,
        node: dict[str, Any],
        step: int,
        data: str,
        error: str | None,
    ) -> None:
        """Store a short record of a node in the run session."""
        from backend.agent.utils.error_logger import log_error

        try:
            if error is None:
                self._session_manager.save_message(
                    session_id, "assistant",
                    content=f"[nodo {node['id']}] {data[:NODE_MESSAGE_LIMIT]}",
                    turn_number=1, step=step, status="success", message="",
                )
            else:
                self._session_manager.save_message(
                    session_id, "assistant",
                    content=f"Error en nodo {node['id']}: {error}",
                    turn_number=1, step=step, status="error", message=error,
                )
        except Exception as exc:
            log_error(str(exc), source="workflow_runner.py:save_node_message")

    # ------------------------------------------------------------------
    # Node execution
    # ------------------------------------------------------------------

    async def _run_node(
        self,
        session_id: str,
        node: dict[str, Any],
        state: dict[str, Any],
        cancel_event: asyncio.Event,
        execute_tool,
    ) -> dict[str, Any]:
        """Run one node with its own retries (exponential backoff).

        Returns:
            ``{"status": "success" | "error" | "cancelled", "message", "data",
            "child_id"}``.
        """
        from backend.agent.utils.error_logger import log_error

        attempts = int(node.get("retries", 0)) + 1
        last_error = ""
        child_id = None
        for attempt in range(1, attempts + 1):
            if cancel_event.is_set():
                return {"status": "cancelled", "message": "Cancelado.", "data": "", "child_id": child_id}
            try:
                if node["type"] == "agent":
                    result = await self._run_agent_node(session_id, node, state, cancel_event)
                elif node["type"] == "tool":
                    result = await self._run_tool_node(node, state, execute_tool)
                elif node["type"] == "run":
                    result = await self._run_run_node(node, execute_tool)
                else:
                    result = await self._run_rag_node(node, state, execute_tool)
                child_id = result.get("child_id") or child_id
                if result.get("status") == "error":
                    last_error = str(result.get("message", "")) or "Nodo fallido."
                    if attempt < attempts:
                        await asyncio.sleep(2 ** (attempt - 1))
                        continue
                    return {"status": "error", "message": last_error, "data": "", "child_id": child_id}
                return {
                    "status": "success",
                    "message": result.get("message", ""),
                    "data": result.get("data", ""),
                    "child_id": child_id,
                }
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log_error(str(exc), source="workflow_runner.py:_run_node")
                last_error = str(exc) or "Nodo fallido."
                if attempt < attempts:
                    await asyncio.sleep(2 ** (attempt - 1))
        return {"status": "error", "message": last_error or "Nodo fallido.", "data": "", "child_id": child_id}

    async def _run_agent_node(
        self,
        session_id: str,
        node: dict[str, Any],
        state: dict[str, Any],
        cancel_event: asyncio.Event,
    ) -> dict[str, Any]:
        """Run an agent node in a child session, return only final text."""
        import json as _json

        from backend.agent.loop import AgentLoop
        from backend.agent.permissions import get_agent_parameters, get_skill_permissions, get_tool_permissions
        from backend.agent.utils.error_logger import log_error

        agent_name = node.get("agent_name", "")
        try:
            if not agent_name or ".." in agent_name or "/" in agent_name or "\\" in agent_name:
                return {"status": "error", "message": f"Nombre de agente inválido en nodo '{node.get('id', '')}'.", "data": ""}
            from backend.agent.utils.config_dir import get_agents_dir

            agent_file = get_agents_dir() / f"{agent_name}.md"
            if not agent_file.is_file():
                return {"status": "error",
                        "message": f"No se encontró el agente '{agent_name}' (nodo '{node.get('id', '')}'). Revisá que exista en la carpeta de agentes.",
                        "data": ""}
        except Exception as exc:
            log_error(str(exc), source="workflow_runner.py:agent_exists")
            return {"status": "error", "message": f"No se pudo verificar el agente '{agent_name}'.", "data": ""}
        prompt_template = node.get("prompt", "") or state.get("input", "")
        try:
            context = _json.dumps(state.get("results", {}), ensure_ascii=False)[:4000]
        except Exception:
            context = ""
        has_context = bool(state.get("results"))
        prompt = (
            f"{prompt_template}\n\nContexto de steps previos:\n{context}"
            if has_context and context
            else prompt_template
        )

        tool_perms: dict = {}
        tp = get_tool_permissions(agent_name)
        if tp.get("status") == "success":
            try:
                tool_perms = _json.loads(tp["data"])
            except (ValueError, TypeError):
                tool_perms = {}
        skill_perms: dict = {}
        sp = get_skill_permissions(agent_name)
        if sp.get("status") == "success":
            try:
                skill_perms = _json.loads(sp["data"])
            except (ValueError, TypeError):
                skill_perms = {}
        parameters: dict = {}
        pr = get_agent_parameters(agent_name)
        if pr.get("status") == "success":
            try:
                parameters = _json.loads(pr.get("data", "{}"))
            except (ValueError, TypeError):
                parameters = {}

        child_id = f"{session_id}:{agent_name}:{uuid.uuid4().hex[:8]}"
        try:
            create_res = self._session_manager.create_session(child_id, parent_id=session_id)
            if create_res.get("status") != "success":
                return {"status": "error", "message": "No se pudo crear la sesión hija.", "data": ""}
        except Exception as exc:
            log_error(str(exc), source="workflow_runner.py:child_session")
            return {"status": "error", "message": "No se pudo crear la sesión hija.", "data": ""}

        loop = AgentLoop(agent=self._agent, session_manager=self._session_manager)
        final_text = ""
        try:
            async for sse in loop.run(
                session_id=child_id,
                user_message=prompt,
                tool_permissions=tool_perms,
                skill_permissions=skill_perms,
                parameters=parameters,
                agent_name=agent_name,
                depth=1,
                parent_id=session_id,
                stream_cancel_event=cancel_event,
            ):
                if sse.strip() == "data: [DONE]":
                    break
                if sse.startswith("data: "):
                    try:
                        payload = _json.loads(sse[len("data: "):].strip())
                    except (ValueError, TypeError):
                        continue
                    if payload.get("type") == "chunk":
                        final_text += payload.get("content", "")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log_error(str(exc), source="workflow_runner.py:agent_node")
            return {"status": "error", "message": f"Error en el nodo agente '{agent_name}': {exc}", "data": "",
                    "child_id": child_id}
        if not final_text.strip():
            return {"status": "error", "message": "El nodo agente no produjo respuesta.", "data": "",
                    "child_id": child_id}
        return {"status": "success", "message": "Nodo agente ok.", "data": final_text,
                "child_id": child_id}

    async def _run_tool_node(self, node: dict[str, Any], state: dict[str, Any], execute_tool) -> dict[str, Any]:
        """Run a tool node with permissions from its agent when set."""
        import json as _json

        from backend.agent.utils.error_logger import log_error

        args = dict(node.get("args", {}))
        query = node.get("query", "") or state.get("input", "")
        injected_query = False
        if query and "query" not in args and "text" not in args and "content" not in args:
            args["query"] = query
            injected_query = True
        tc = {"name": node.get("tool", ""), "args": args}
        try:
            result = await execute_tool(self._agent, tc)
        except Exception as exc:
            log_error(str(exc), source="workflow_runner.py:tool_node")
            return {"status": "error", "message": f"Tool '{tc['name']}' falló: {exc}", "data": ""}
        if (
            isinstance(result, dict) and result.get("status") == "error"
            and injected_query and "unexpected keyword argument" in str(result.get("message", ""))
        ):
            # Strict handlers (e.g. read(file_path)) reject the injected
            # context key: retry once with only the declared args.
            try:
                args.pop("query", None)
                result = await execute_tool(self._agent, {"name": node.get("tool", ""), "args": args})
            except Exception as exc:
                log_error(str(exc), source="workflow_runner.py:tool_node(retry)")
                return {"status": "error", "message": f"Tool '{tc['name']}' falló: {exc}", "data": ""}
        if isinstance(result, dict) and result.get("status") == "error":
            return result
        data = result.get("data", "") if isinstance(result, dict) else result
        try:
            text = _json.dumps(data, ensure_ascii=False) if isinstance(data, (dict, list)) else str(data)
        except Exception:
            text = str(data)
        return {"status": "success", "message": "Nodo tool ok.", "data": text}

    async def _run_run_node(self, node: dict[str, Any], execute_tool) -> dict[str, Any]:
        """Run a run node (shell command, github-actions style).

        Executes ``node["run"]`` through the ``shell`` tool so it inherits
        its sandbox (worker thread, timeout, 50 KB truncation, cancel).
        ``workdir`` is confined to the project root when set.

        Args:
            node: Normalized run node (``run``, ``timeout``, ``workdir``).
            execute_tool: Tool executor from ``loop_helpers``.

        Returns:
            Contract dict ``{status, message, data}`` with the command output.
        """
        import json as _json
        import os as _os

        from backend.agent.utils.error_logger import log_error
        from backend.agent.utils.workflow_validator import _valid_run_workdir

        command = str(node.get("run", "") or "")
        if not command.strip():
            return {"status": "error", "message": f"Nodo '{node.get('id', '')}' sin comando 'run'.", "data": ""}
        try:
            timeout = int(node.get("timeout", 30000))
        except (TypeError, ValueError):
            timeout = 30000
        timeout = min(max(timeout, 1000), 300000)
        args: dict[str, Any] = {"command": command, "timeout": timeout}
        workdir = str(node.get("workdir", "") or "").strip()
        if workdir:
            if not _valid_run_workdir(workdir):
                return {"status": "error", "message": f"Nodo '{node.get('id', '')}' con 'workdir' inválido.", "data": ""}
            try:
                base = _os.path.realpath(_os.getcwd())
                full = _os.path.realpath(_os.path.join(base, workdir.strip().replace("\\", "/")))
                if _os.path.commonpath([base, full]) != base:
                    return {"status": "error", "message": f"Nodo '{node.get('id', '')}' con 'workdir' inválido.", "data": ""}
                args["workdir"] = full
            except Exception as exc:
                log_error(str(exc), source="workflow_runner.py:run_workdir")
                return {"status": "error", "message": f"Nodo '{node.get('id', '')}' con 'workdir' inválido.", "data": ""}
        tc = {"name": "shell", "args": args}
        try:
            result = await execute_tool(self._agent, tc)
        except Exception as exc:
            log_error(str(exc), source="workflow_runner.py:run_node")
            return {"status": "error", "message": f"Comando del nodo '{node.get('id', '')}' falló: {exc}", "data": ""}
        if isinstance(result, dict) and result.get("status") == "error":
            return result
        data = result.get("data", "") if isinstance(result, dict) else result
        # Like a GitHub Actions step: a command that exits with a non-zero
        # code fails the node (the shell tool reports it as a success with
        # the return code inside its data).
        if isinstance(data, dict) and isinstance(data.get("returncode"), int) and data["returncode"] != 0:
            output = str(data.get("output", "") or "").strip()
            tail = output[-500:] if output else "sin salida"
            return {
                "status": "error",
                "message": f"El comando del nodo '{node.get('id', '')}' terminó con código {data['returncode']}: {tail}",
                "data": "",
            }
        try:
            text = _json.dumps(data, ensure_ascii=False) if isinstance(data, (dict, list)) else str(data)
        except Exception:
            text = str(data)
        return {"status": "success", "message": "Nodo run ok.", "data": text}

    async def _run_rag_node(self, node: dict[str, Any], state: dict[str, Any], execute_tool) -> dict[str, Any]:
        """Run a rag node against a collection."""
        from backend.agent.utils.error_logger import log_error

        query = node.get("query", "") or state.get("input", "")
        tc = {"name": "rag", "args": {"collection": node.get("collection", ""), "query": query}}
        try:
            result = await execute_tool(self._agent, tc)
        except Exception as exc:
            log_error(str(exc), source="workflow_runner.py:rag_node")
            return {"status": "error", "message": f"RAG falló: {exc}", "data": ""}
        if isinstance(result, dict) and result.get("status") == "error":
            return result
        data = result.get("data", "") if isinstance(result, dict) else result
        return {"status": "success", "message": "Nodo rag ok.", "data": data}
