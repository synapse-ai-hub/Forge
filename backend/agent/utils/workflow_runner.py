"""Deterministic DAG runner with barriers, retries and shared state.

Own development, no LangGraph dependency. Patterns taken as reference
from LangGraph PregelRunner: super-step per ``step``, concurrent tasks
in the same super-step, commit per task, retry per node.

Same ``step`` runs in parallel with ``asyncio.gather`` and a barrier.
Different ``step`` runs sequentially. Only the final node answers the
parent. Same SSE format as ``AgentLoop.run``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncIterator, Optional

logger = logging.getLogger(__name__)


class WorkflowRunner:
    """Execute a validated workflow dict step by step."""

    def __init__(self, agent, session_manager) -> None:
        """Store shared singletons.

        Args:
            agent: Agent singleton with tools and model resolution.
            session_manager: Session manager for persistence and config.
        """
        self._agent = agent
        self._session_manager = session_manager

    async def run(
        self,
        session_id: str,
        user_message: str,
        workflow: dict[str, Any],
        turn_number: int = 1,
        stream_cancel_event: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[str]:
        """Run the workflow as an SSE async generator.

        Args:
            session_id: Parent session identifier.
            user_message: Original user message.
            workflow: Validated workflow data from the loader.
            turn_number: Turn number for persistence.
            stream_cancel_event: Optional cancellation event.

        Yields:
            SSE strings with the same format as ``AgentLoop.run``.
        """
        from backend.agent.utils.error_logger import log_error
        from backend.agent.utils.loop_helpers import execute_tool

        nodes = list(workflow.get("nodes", []))
        on_failure = workflow.get("on_failure", "continue")
        name = workflow.get("name", "workflow")
        state: dict[str, Any] = {
            "input": user_message,
            "results": {},
            "errors": {},
            "workflow": name,
        }
        steps = sorted({n["step"] for n in nodes})
        final_text = ""

        yield f"data: {json.dumps({'type': 'chunk', 'content': f'_Ejecutando workflow {name}._'}, ensure_ascii=False)}\n\n"

        for step in steps:
            if stream_cancel_event is not None and stream_cancel_event.is_set():
                yield f"data: {json.dumps({'type': 'chunk', 'content': 'Ejecución cancelada por el usuario.'}, ensure_ascii=False)}\n\n"
                break
            group = [n for n in nodes if n["step"] == step]

            async def _run_node(node: dict[str, Any]) -> dict[str, Any]:
                last_error = ""
                attempts = int(node.get("retries", 0)) + 1
                for attempt in range(1, attempts + 1):
                    try:
                        if stream_cancel_event is not None and stream_cancel_event.is_set():
                            return {"node_id": node["id"], "status": "error", "message": "Cancelado.", "data": ""}
                        if node["type"] == "agent":
                            result = await self._run_agent_node(
                                session_id, node, state, turn_number, stream_cancel_event,
                            )
                        elif node["type"] == "tool":
                            result = await self._run_tool_node(node, state, execute_tool)
                        else:
                            result = await self._run_rag_node(node, state, execute_tool)
                        if isinstance(result, dict) and result.get("status") == "error" and attempt < attempts:
                            last_error = str(result.get("message", ""))
                            await asyncio.sleep(1 * attempt)
                            continue
                        return {"node_id": node["id"], "status": result.get("status", "success"),
                                "message": result.get("message", ""), "data": result.get("data", "")}
                    except asyncio.CancelledError:
                        return {"node_id": node["id"], "status": "error", "message": "Cancelado.", "data": ""}
                    except Exception as exc:
                        log_error(str(exc), source="workflow_runner.py:_run_node")
                        last_error = str(exc)
                        if attempt < attempts:
                            await asyncio.sleep(1 * attempt)
                return {"node_id": node["id"], "status": "error", "message": last_error or "Nodo fallido.", "data": ""}

            if len(group) == 1:
                node = group[0]
                yield f"data: {json.dumps({'type': 'tool_call', 'content': {'name': node.get('tool') or node.get('agent_name') or node['id'], 'args': {'node_id': node['id'], 'step': step}}}, ensure_ascii=False)}\n\n"
                results = [await _run_node(node)]
            else:
                for node in group:
                    yield f"data: {json.dumps({'type': 'tool_call', 'content': {'name': node.get('tool') or node.get('agent_name') or node['id'], 'args': {'node_id': node['id'], 'step': step}}}, ensure_ascii=False)}\n\n"
                results = list(await asyncio.gather(*(_run_node(n) for n in group)))

            for outcome in results:
                node = next(n for n in group if n["id"] == outcome["node_id"])
                if outcome["status"] == "success":
                    state["results"][node["id"]] = outcome["data"]
                    yield f"data: {json.dumps({'type': 'tool_result', 'content': {'name': node['id'], 'result': {'status': 'success', 'data': outcome['data']}}}, ensure_ascii=False)}\n\n"
                else:
                    state["errors"][node["id"]] = outcome["message"]
                    try:
                        self._session_manager.save_message(
                            session_id, "assistant",
                            content=f"Error en nodo {node['id']}: {outcome['message']}",
                            turn_number=turn_number, step=step, status="error",
                            message=outcome["message"],
                        )
                    except Exception as exc:
                        log_error(str(exc), source="workflow_runner.py:save_error")
                    yield f"data: {json.dumps({'type': 'chunk', 'content': f"_Nodo {node['id']} falló tras reintentos: {outcome['message']}_"}, ensure_ascii=False)}\n\n"
                    if on_failure == "abort":
                        yield f"data: {json.dumps({'type': 'chunk', 'content': 'Workflow abortado por fallo de rama.'}, ensure_ascii=False)}\n\n"
                        yield "data: [DONE]\n\n"
                        return
                if node.get("final") or (step == steps[-1] and node == group[-1]):
                    final_text = str(outcome["data"] or final_text)

        answer = final_text.strip() or "Workflow completado sin respuesta final."
        try:
            self._session_manager.save_message(
                session_id, "assistant", content=answer,
                turn_number=turn_number, step=steps[-1] if steps else 1,
                status="success", message="",
            )
        except Exception as exc:
            from backend.agent.utils.error_logger import log_error as _log
            _log(str(exc), source="workflow_runner.py:save_final")
        yield f"data: {json.dumps({'type': 'chunk', 'content': answer}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    async def _run_agent_node(
        self,
        session_id: str,
        node: dict[str, Any],
        state: dict[str, Any],
        turn_number: int,
        stream_cancel_event: Optional[asyncio.Event],
    ) -> dict[str, Any]:
        """Run an agent node in a child session, return only final text."""
        import json as _json

        from backend.agent.loop import AgentLoop
        from backend.agent.permissions import get_agent_parameters, get_skill_permissions, get_tool_permissions
        from backend.agent.utils.error_logger import log_error

        t0 = time.time()
        agent_name = node.get("agent_name", "")
        prompt_template = node.get("prompt", "") or state.get("input", "")
        try:
            context = _json.dumps(state.get("results", {}), ensure_ascii=False)[:4000]
        except Exception:
            context = ""
        prompt = f"{prompt_template}\n\nContexto de steps previos:\n{context}" if context else prompt_template

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

        child_id = f"{session_id}:{agent_name}:{uuid.uuid4().hex[:8]}" if session_id else f"{agent_name}:{uuid.uuid4().hex[:8]}"
        try:
            create_res = self._session_manager.create_session(child_id, parent_id=session_id)
            if create_res.get("status") != "success":
                return {"status": "error", "message": "No se pudo crear la sesión hija.", "data": ""}
        except Exception as exc:
            log_error(str(exc), source="workflow_runner.py:child_session")
            return {"status": "error", "message": "No se pudo crear la sesión hija.", "data": ""}

        loop = AgentLoop(agent=self._agent, session_manager=self._session_manager)
        final_text = ""
        usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "total_time": 0.0}
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
                stream_cancel_event=stream_cancel_event,
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
        except Exception as exc:
            log_error(str(exc), source="workflow_runner.py:agent_node")
            return {"status": "error", "message": "Error en nodo agente.", "data": ""}
        total_time = round(time.time() - t0, 2)
        usage_total["total_time"] = total_time
        try:
            self._session_manager.save_message(
                session_id, "assistant",
                content=f"[nodo {node['id']}] {final_text[:2000]}",
                turn_number=turn_number, step=node.get("step", 1),
                status="success", message="",
                usage=usage_total,
            )
        except Exception as exc:
            log_error(str(exc), source="workflow_runner.py:save_node")
        if not final_text.strip():
            return {"status": "error", "message": "El nodo agente no produjo respuesta.", "data": ""}
        return {"status": "success", "message": "Nodo agente ok.", "data": final_text}

    async def _run_tool_node(self, node: dict[str, Any], state: dict[str, Any], execute_tool) -> dict[str, Any]:
        """Run a tool node with permissions from its agent when set."""
        import json as _json

        from backend.agent.utils.error_logger import log_error

        t0 = time.time()
        args = dict(node.get("args", {}))
        query = node.get("query", "") or state.get("input", "")
        if query and "query" not in args and "text" not in args and "content" not in args:
            args.setdefault("query", query)
        tc = {"name": node.get("tool", ""), "args": args}
        try:
            result = await execute_tool(self._agent, tc)
        except Exception as exc:
            log_error(str(exc), source="workflow_runner.py:tool_node")
            return {"status": "error", "message": f"Tool '{tc['name']}' falló.", "data": ""}
        if isinstance(result, dict) and result.get("status") == "error":
            return result
        data = result.get("data", "") if isinstance(result, dict) else result
        try:
            text = _json.dumps(data, ensure_ascii=False) if isinstance(data, (dict, list)) else str(data)
        except Exception:
            text = str(data)
        _ = round(time.time() - t0, 2)
        return {"status": "success", "message": "Nodo tool ok.", "data": text}

    async def _run_rag_node(self, node: dict[str, Any], state: dict[str, Any], execute_tool) -> dict[str, Any]:
        """Run a rag node against a collection."""
        from backend.agent.utils.error_logger import log_error

        query = node.get("query", "") or state.get("input", "")
        tc = {"name": "rag", "args": {"collection": node.get("collection", ""), "query": query}}
        try:
            result = await execute_tool(self._agent, tc)
        except Exception as exc:
            log_error(str(exc), source="workflow_runner.py:rag_node")
            return {"status": "error", "message": "RAG falló.", "data": ""}
        if isinstance(result, dict) and result.get("status") == "error":
            return result
        data = result.get("data", "") if isinstance(result, dict) else result
        return {"status": "success", "message": "Nodo rag ok.", "data": data}
