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

A run never opens a session nor writes in ``messages``: an agent node runs in
memory and everything it does (result, error, tokens, cost and time) is a row
of ``workflow_runs``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any

from backend.agent.utils import workflow_db

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.agent.agent import Agent
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


def _as_text(data: Any) -> str:
    """Convert a node result to text.

    Args:
        data: Result of a node (text, dict, list or ``None``).

    Returns:
        The text itself, JSON for dicts and lists, or an empty string for ``None``.
    """
    if data is None:
        return ""
    if isinstance(data, (dict, list)):
        try:
            return json.dumps(data, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(data)
    return str(data)


def _add_usage(spend: dict[str, Any], provider: str | None, model: str | None, usage: dict[str, Any] | None) -> None:
    """Add the usage of one LLM call to the spend of a node.

    Args:
        spend: Spend of the node (``provider``, ``model`` and ``usage``), changed in place.
        provider: Provider of the call.
        model: Model of the call.
        usage: Usage report of the call (``prompt_tokens``, ``completion_tokens``,
            ``total_tokens``, ``total_time``), or ``None`` when none was captured.
    """
    spend["provider"] = provider or spend.get("provider")
    spend["model"] = model or spend.get("model")
    total = spend.setdefault("usage", {})
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "total_time"):
        total[key] = (total.get(key) or 0) + ((usage or {}).get(key) or 0)


class WorkflowRunner:
    """Execute one attempt of a validated workflow, step by step."""

    def __init__(self, agent: Agent) -> None:
        """Store the agent singleton.

        Args:
            agent: Agent singleton with tools, prompts and model resolution.
        """
        self._agent = agent

    async def execute_attempt(
        self,
        run_id: str,
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
            workflow: Validated workflow data from the loader.
            attempt: Attempt number (1..3).
            cancel_event: Set when the user cancels the run.

        Returns:
            ``{"status": "success" | "error" | "cancelled", "results": {...},
            "failures": [{"node", "type", "error"}], "final_text": str}``.
        """
        from backend.agent.utils.config_dir import get_workspace_dir, workspace_ctx
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
        # A run has no session: a workflow node tool never hangs from the chat session.
        token = _tool_call_ctx.set({"tool_permissions": allowed, "parent_session_id": None})
        # Every command of the run (run nodes and the shell of agent nodes)
        # starts in the workflow's own folder, never in the project root.
        workspace = get_workspace_dir(str(workflow.get("name", "") or "workflow"))
        ws_token = workspace_ctx.set(str(workspace))
        try:
            return await self._attempt(
                run_id, workflow, nodes, attempt, cancel_event, execute_tool,
            )
        finally:
            for ctx, tok in ((workspace_ctx, ws_token), (_tool_call_ctx, token)):
                try:
                    ctx.reset(tok)
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
            Node id → ``{"result": str}``.
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
            k: {"result": v.get("result") or ""}
            for k, v in latest.items()
            if k in known
        }

    async def _attempt(
        self,
        run_id: str,
        workflow: dict[str, Any],
        nodes: list[dict[str, Any]],
        attempt: int,
        cancel_event: asyncio.Event,
        execute_tool: Callable[..., Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        """Execute the pending steps of the DAG (see :meth:`execute_attempt`).

        Args:
            run_id: Run identifier (owner of the commit rows).
            workflow: Validated workflow data.
            nodes: Normalized workflow nodes.
            attempt: Attempt number (1..3).
            cancel_event: Set when the user cancels the run.
            execute_tool: Tool executor from ``loop_helpers``.

        Returns:
            The attempt outcome ``{status, results, failures, final_text}``.
        """
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
            started_at = datetime.now().isoformat()
            for pos, node in pending:
                rows[node["id"]] = workflow_db.open_step(
                    run_id, attempt, step, pos, node["id"], node["type"], node.get("args"),
                )
            outcomes = await asyncio.gather(
                *(
                    self._timed_node(node, state, cancel_event, execute_tool)
                    for _, node in pending
                )
            )

            aborted = False
            for (pos, node), outcome in zip(pending, outcomes):
                row_id = rows.get(node["id"])
                spend = outcome.get("spend") or {}
                for call in spend.get("tools", []):
                    workflow_db.record_tool_call(run_id, attempt, step, pos, node["id"], **call)
                common = {
                    "started_at": started_at, "tool_name": self._tool_of(node),
                    "seconds": outcome.get("seconds", 0.0), "provider": spend.get("provider"),
                    "model": spend.get("model"), "usage": spend.get("usage"),
                }
                if outcome["status"] == "success":
                    data = _as_text(outcome["data"])
                    workflow_db.commit_step(row_id, data)
                    workflow_db.record_node(
                        run_id, attempt, step, pos, node["id"], node["type"], "success",
                        result=data, **common,
                    )
                    committed[node["id"]] = {"result": data}
                    state["results"][node["id"]] = data
                elif outcome["status"] == "cancelled":
                    workflow_db.fail_step(row_id, "Cancelado por el usuario.")
                    workflow_db.record_node(
                        run_id, attempt, step, pos, node["id"], node["type"], "cancelled",
                        error="Cancelado por el usuario.", **common,
                    )
                else:
                    message = str(outcome.get("message") or "Nodo fallido.")
                    workflow_db.fail_step(row_id, message)
                    workflow_db.record_node(
                        run_id, attempt, step, pos, node["id"], node["type"], "error",
                        error=message, **common,
                    )
                    state["errors"][node["id"]] = message
                    failures.append({"node": node["id"], "type": node["type"], "error": message})
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
        """Build the attempt result from every node result.

        Args:
            status: ``"success"``, ``"error"`` or ``"cancelled"``.
            state: Shared state of the attempt (``results`` of every node).
            failures: One dict per failed node with ``node``, ``type`` and ``error``.
            nodes: Normalized workflow nodes.

        Returns:
            The attempt outcome ``{status, results, failures, final_text}``.
            ``final_text`` is always empty here: the report is generated
            afterwards by ``generate_output`` from all results.
        """
        return {
            "status": status,
            "results": dict(state["results"]),
            "failures": failures,
            "final_text": "",
        }

    # ------------------------------------------------------------------
    # Node execution
    # ------------------------------------------------------------------

    @staticmethod
    def _tool_of(node: dict[str, Any]) -> str | None:
        """Name the tool a node runs.

        Args:
            node: Normalized node.

        Returns:
            ``shell`` for a ``run`` node, ``rag`` for a ``rag`` node, the tool of a
            ``tool`` node, or ``None`` for an ``agent`` node.
        """
        kind = node.get("type")
        if kind == "run":
            return "shell"
        if kind == "rag":
            return "rag"
        if kind == "tool":
            return str(node.get("tool") or "") or None
        return None

    async def _timed_node(
        self,
        node: dict[str, Any],
        state: dict[str, Any],
        cancel_event: asyncio.Event,
        execute_tool: Callable[..., Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        """Run one node (see :meth:`_run_node`) and measure how long it took.

        Args:
            node: Normalized node.
            state: Shared state of the attempt.
            cancel_event: Set when the user cancels the run.
            execute_tool: Tool executor from ``loop_helpers``.

        Returns:
            The outcome of :meth:`_run_node` with the ``seconds`` the node took.
        """
        started = time.monotonic()
        outcome = await self._run_node(node, state, cancel_event, execute_tool)
        return {**outcome, "seconds": round(time.monotonic() - started, 3)}

    async def _run_node(
        self,
        node: dict[str, Any],
        state: dict[str, Any],
        cancel_event: asyncio.Event,
        execute_tool: Callable[..., Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        """Run one node with its own retries (exponential backoff).

        Args:
            node: Normalized node.
            state: Shared state of the attempt.
            cancel_event: Set when the user cancels the run.
            execute_tool: Tool executor from ``loop_helpers``.

        Returns:
            ``{"status": "success" | "error" | "cancelled", "message", "data", "spend"}``;
            ``spend`` adds up the LLM calls of every retry of an agent node
            (``provider``, ``model`` and ``usage``) and keeps the tools it called
            (``tools``); it is empty in the other nodes.
        """
        from backend.agent.utils.error_logger import log_error

        attempts = int(node.get("retries", 0)) + 1
        last_error = ""
        spend: dict[str, Any] = {}
        for attempt in range(1, attempts + 1):
            if cancel_event.is_set():
                return {"status": "cancelled", "message": "Cancelado.", "data": "", "spend": spend}
            try:
                if node["type"] == "agent":
                    result = await self._run_agent_node(node, state, spend)
                elif node["type"] == "tool":
                    result = await self._run_tool_node(node, state, execute_tool)
                elif node["type"] == "run":
                    result = await self._run_run_node(node, execute_tool)
                else:
                    result = await self._run_rag_node(node, state, execute_tool)
                if result.get("status") == "error":
                    last_error = str(result.get("message", "")) or "Nodo fallido."
                    if attempt < attempts:
                        await asyncio.sleep(2 ** (attempt - 1))
                        continue
                    return {"status": "error", "message": last_error, "data": "", "spend": spend}
                return {
                    "status": "success",
                    "message": result.get("message", ""),
                    "data": result.get("data", ""),
                    "spend": spend,
                }
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log_error(str(exc), source="workflow_runner.py:_run_node")
                last_error = str(exc) or "Nodo fallido."
                if attempt < attempts:
                    await asyncio.sleep(2 ** (attempt - 1))
        return {"status": "error", "message": last_error or "Nodo fallido.", "data": "", "spend": spend}

    @staticmethod
    def _build_context(results: dict[str, Any]) -> str:
        """Render the results of the previous nodes as readable text.

        Every result goes in whole, with no cut.

        Args:
            results: Node id → result of the previous nodes.

        Returns:
            One section per node, or an empty string when there are no results.
        """
        if not results:
            return ""
        sections = []
        for node_id, value in results.items():
            sections.append(f"### {node_id}\n{_as_text(value).strip()}")
        return "\n\n".join(sections)

    async def _run_agent_node(
        self,
        node: dict[str, Any],
        state: dict[str, Any],
        spend: dict[str, Any],
    ) -> dict[str, Any]:
        """Run an agent node in memory, without a session and without writing in ``messages``.

        The agent uses its own markdown: its system prompt, the tools and skills it
        allows (``task`` is left out: a sub-agent would open a session) and its
        parameters (model, provider, temperature, top_p and max_tokens; the global
        overrides of temperature and top_p win, like in the chat). Every tool call is
        checked against its permissions. The user message is the prompt of the node
        (the ``prompt_file`` toml when it has one) followed by the results of the
        previous steps.

        Args:
            node: Normalized agent node.
            state: Shared state of the attempt.
            spend: Spend of the node, where the usage of every LLM call is added and
                every tool call is kept (``tools``).

        Returns:
            Contract dict ``{status, message, data}`` with the final text of the agent.
        """
        import json as _json

        from backend.agent.loop.helpers import _read_param_override
        from backend.agent.permissions import get_agent_parameters, get_skill_permissions, get_tool_permissions
        from backend.agent.utils.create_helpers import stream_tool_calling_loop
        from backend.agent.utils.error_logger import log_error
        from backend.agent.utils.loop_helpers import _tool_call_ctx, build_system_prompt, execute_tool
        from backend.agent.utils.skill_loader import format_skills_section

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
        if node.get("prompt_file"):
            from backend.agent.utils.workflow_loader import load_prompt_file

            loaded = load_prompt_file(str(node["prompt_file"]))
            if loaded.get("status") != "success":
                return {"status": "error", "message": str(loaded.get("message") or "No se pudo cargar el prompt."), "data": ""}
            prompt_template = loaded["data"]
        prompt = self._agent.prompt(
            "user_agent_node",
            prompt=prompt_template,
            contexto=self._build_context(state.get("results", {})),
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
        # A sub-agent (task) runs in a session of its own: never inside a workflow.
        tool_perms.pop("task", None)

        try:
            system = self._agent.prompt(
                "system_agent_node",
                base=build_system_prompt(agent_name),
                skills=format_skills_section(skill_permissions=skill_perms) if skill_perms else "",
            )
            tools = list(self._agent.tools.tools_registry(tool_perms))
        except Exception as exc:
            log_error(str(exc), source="workflow_runner.py:agent_node(prepare)")
            return {"status": "error", "message": f"No se pudo preparar el agente '{agent_name}'.", "data": ""}

        model = parameters.get("model") or getattr(self._agent, "_resolved_model", None)
        provider = parameters.get("provider") or getattr(self._agent, "provider", None)
        temperature = parameters.get("temperature", 0.0)
        top_p = parameters.get("top_p", 0.5)
        override = _read_param_override("param_temperature")
        if override is not None:
            temperature = override
        override = _read_param_override("param_top_p")
        if override is not None:
            top_p = override

        async def run_tool(name: str, args: dict[str, Any]) -> Any:
            """Run a tool call of the agent under its own permissions and keep it in the spend of the node.

            Args:
                name: Name of the tool.
                args: Arguments the agent passed.

            Returns:
                The contract dict of the tool.
            """
            started_at = datetime.now().isoformat()
            started = time.monotonic()
            # No session: a workflow the agent runs through its tool has no caller session either.
            token = _tool_call_ctx.set({"tool_permissions": tool_perms, "skill_permissions": skill_perms, "parent_session_id": None})
            result: Any = None
            try:
                result = await execute_tool(self._agent, {"name": name, "args": args})
                return result
            finally:
                _tool_call_ctx.reset(token)
                if not isinstance(result, dict):
                    status, output, error = "error", None, "La tool no respondió."
                elif result.get("status") == "error":
                    status, output, error = "error", None, str(result.get("message") or "")
                else:
                    status, output, error = "success", _as_text(result.get("data")), None
                spend.setdefault("tools", []).append({
                    "tool_name": name,
                    "status": status,
                    "result": output,
                    "error": error,
                    "seconds": round(time.monotonic() - started, 3),
                    "started_at": started_at,
                    "finished_at": datetime.now().isoformat(),
                })

        msgs: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        final_text = ""
        failure = ""
        try:
            async for event in stream_tool_calling_loop(
                msgs, tools, f"El nodo agente '{agent_name}' no pudo responder.",
                model=model, provider=provider,
                temperature=temperature, top_p=top_p,
                max_tokens=int(parameters.get("max_tokens", 8192)),
                run_tool=run_tool,
                on_usage=lambda p, m, u: _add_usage(spend, p, m, u),
            ):
                if event["type"] == "chunk":
                    final_text += event.get("content", "")
                elif event["type"] == "tool_call":
                    # Only the text after the last tool call is the answer of the agent.
                    final_text = ""
                elif event["type"] in ("error", "aborted"):
                    failure = str(event.get("content") or "")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log_error(str(exc), source="workflow_runner.py:agent_node")
            return {"status": "error", "message": f"Error en el nodo agente '{agent_name}': {exc}", "data": ""}
        if failure:
            return {"status": "error", "message": failure, "data": ""}
        if not final_text.strip():
            return {"status": "error", "message": "El nodo agente no produjo respuesta.", "data": ""}
        return {"status": "success", "message": "Nodo agente ok.", "data": final_text}

    async def _run_tool_node(
        self,
        node: dict[str, Any],
        state: dict[str, Any],
        execute_tool: Callable[..., Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        """Run a tool node.

        Args:
            node: Normalized tool node.
            state: Shared state of the attempt.
            execute_tool: Tool executor from ``loop_helpers``.

        Returns:
            Contract dict ``{status, message, data}`` with the output of the tool as text.
        """
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

    async def _run_run_node(
        self,
        node: dict[str, Any],
        execute_tool: Callable[..., Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        """Run a run node (shell command, github-actions style).

        Executes ``node["run"]`` through the ``shell`` tool so it inherits
        its sandbox (worker thread, timeout, 50 KB truncation, cancel).
        It starts in the workspace of the workflow
        (``~/.config/synapseForge/workspace/<name>``); ``workdir`` is a
        subfolder of it and cannot leave it.

        Args:
            node: Normalized run node (``run``, ``timeout``, ``workdir``).
            execute_tool: Tool executor from ``loop_helpers``.

        Returns:
            Contract dict ``{status, message, data}`` with the command output.
        """
        import json as _json
        import os as _os

        from backend.agent.utils.config_dir import workspace_ctx
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
                base = _os.path.realpath(workspace_ctx.get() or _os.getcwd())
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
        # code fails the node. The shell tool already returns an error
        # contract in that case (handled above); this is a defensive
        # fallback for tools that still report the code inside data.
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

    async def _run_rag_node(
        self,
        node: dict[str, Any],
        state: dict[str, Any],
        execute_tool: Callable[..., Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        """Run a rag node against a collection.

        Args:
            node: Normalized rag node.
            state: Shared state of the attempt.
            execute_tool: Tool executor from ``loop_helpers``.

        Returns:
            Contract dict ``{status, message, data}`` with the query results.
        """
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
