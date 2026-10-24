"""Regression tests for the workflow redesign.

Each test pins a decision taken on purpose, checked through its contract (rows
in the tables, HTTP responses, what the agent sees) and not through internals.
Everything runs against an isolated SQLite database and workflows folder in a
temp directory; no real LLM is called (the judge and the explainer are stubbed
at the LLM boundary, ``agent.decision`` / ``agent.llm_process``).

Covers: tables, engine (backoff, parallelism, judge gate),
judge and explainer, permissions, the chat, notifications and scheduled tasks.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.agent.utils.scheduler_helpers as scheduler_helpers
from backend.agent.loop.helpers import _router_tool_permissions
from backend.agent.permissions import get_tool_permissions
from backend.agent.utils import notifications_helpers, workflow_db
from backend.agent.utils import workflow_judge
from backend.agent.utils.workflow_judge import GENERIC_FAILURE_TEXT, explain_failure, judge_run
from backend.agent.utils.workflow_service import WorkflowService
from backend.instances import agent, session_manager
from tests.workflows.test_workflow_runs import PY, WorkflowEnv, _run, _simple_flow, env  # noqa: F401 (env is a fixture)
from pathlib import Path
from collections.abc import Awaitable, Callable, Coroutine, Iterator, AsyncIterator
from typing import Any
from backend.agent.session import SessionManager
from backend.agent.agent import Agent

NEW_TABLES = {
    "workflows", "workflow_runs", "workflow_run_steps",
    "notifications", "creators",
}


# ───────────────────────── 1. Tables ─────────────────────────


def test_a_new_database_has_all_the_tables(env: WorkflowEnv) -> None:
    """A new database has all the tables.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
    _, _, query, _ = env
    assert NEW_TABLES <= {r["name"] for r in query("select name from sqlite_master where type='table'")}


def test_notifications_origin_is_enforced_by_the_table(env: WorkflowEnv) -> None:
    """Notifications origin is enforced by the table.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
    _, _, query, tmp = env
    workflow_db.ensure_workflow("wf")
    conn = sqlite3.connect(str(tmp / "agent.db"))
    conn.execute("PRAGMA foreign_keys=ON")
    insert = (
        "insert into notifications (kind,workflow_name,title,status,created_at) "
        "values ('workflow',?,'t','success','2026-01-01T00:00:00')"
    )
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(insert, (None,))  # no workflow
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(insert, ("unknown",))  # a workflow that is not registered
        conn.execute(insert, ("wf",))
        conn.commit()
    finally:
        conn.close()
    assert len(query("select 1 from notifications")) == 1


# ───────────────────────── 2. Engine ─────────────────────────


def test_attempts_back_off_exponentially_and_stop_at_three(
    env: WorkflowEnv,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Attempts back off exponentially and stop at three.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
        monkeypatch: Pytest monkeypatch fixture.
    """
    svc, write, query, _ = env
    waits: list[float] = []

    async def fake_backoff(cancel_event: asyncio.Event, seconds: float) -> bool:
        """Record the wait instead of sleeping.

        Args:
            cancel_event: Cancel event of the run (ignored).
            seconds: Seconds the engine would wait.

        Returns:
            ``False``: the run was not cancelled.
        """
        waits.append(seconds)
        return False

    monkeypatch.setattr(WorkflowService, "_backoff", staticmethod(fake_backoff))
    write("always-fails", f"""
name: always-fails
description: fails
retries: 0
nodes:
- {{id: a, type: run, step: 1, final: true, run: '"{PY}" -c "import sys; sys.exit(2)"'}}
""")

    async def go() -> tuple[dict, dict]:
        """Start ``always-fails`` and wait for it.

        Returns:
            ``(started, outcome)``.
        """
        started = await svc.start_run("always-fails")
        return started, await started["task"]

    started, outcome = _run(go())
    assert waits == [2, 4], "two waits between three attempts, doubling"
    assert outcome["status"] == "error"
    assert query("select attempt from workflow_runs where run_id=? and kind='run'", (started["run_id"],))[0]["attempt"] == 3


def test_different_workflows_run_in_parallel(env: WorkflowEnv) -> None:
    """Different workflows run in parallel.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
    svc, write, query, tmp = env
    for name, other in (("par-a", "par-b"), ("par-b", "par-a")):
        mine = (tmp / f"{name}.started").as_posix()
        theirs = (tmp / f"{other}.started").as_posix()
        # Each node announces itself and waits until the other one announced:
        # it only finishes if both are running at the same time.
        code = (
            f"import os,time,sys; open(r'{mine}','w').write('1'); t=time.time()\n"
            f"while not os.path.exists(r'{theirs}'):\n"
            f"    time.sleep(0.05)\n"
            f"    if time.time()-t>20: sys.exit(9)\n"
        )
        script = tmp / f"{name}.py"
        script.write_text(code, encoding="utf-8")
        write(name, f"""
name: {name}
description: waits for its twin
retries: 0
nodes:
- {{id: n, type: run, step: 1, final: true, timeout: 60000, run: '"{PY}" "{script.as_posix()}"'}}
""")

    async def go() -> list[dict]:
        """Start two workflows and wait for both.

        Returns:
            The outcomes of ``par-a`` and ``par-b``.
        """
        a = await svc.start_run("par-a")
        b = await svc.start_run("par-b")
        return await asyncio.gather(a["task"], b["task"])

    first, second = _run(go())
    assert first["status"] == "success" and second["status"] == "success"
    assert {r["status"] for r in query("select status from workflow_runs where kind='run'")} == {"success"}


def test_a_negative_judge_ends_in_error_without_retrying(
    env: WorkflowEnv,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A negative judge ends in error without retrying.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
        monkeypatch: Pytest monkeypatch fixture.
    """
    svc, write, query, _ = env
    _simple_flow(write)

    async def verdict(*args: Any, **kwargs: Any) -> tuple[bool, str]:
        """Reject the run like a judge that finds the result wrong.

        Args:
            *args: Ignored.
            **kwargs: Ignored.

        Returns:
            ``(False, reason)``.
        """
        return False, "El resultado no cumple lo esperado."

    monkeypatch.setattr(workflow_judge, "judge_run", verdict)

    async def go() -> tuple[dict, dict]:
        """Start ``ok-flow`` and wait for it.

        Returns:
            ``(started, outcome)``.
        """
        started = await svc.start_run("ok-flow")
        return started, await started["task"]

    started, outcome = _run(go())
    assert outcome["status"] == "error"
    run = query("select status,attempt,error_text from workflow_runs where run_id=? and kind='run'", (started["run_id"],))[0]
    assert run["status"] == "error" and run["attempt"] == 1
    assert run["error_text"] == "El resultado no cumple lo esperado."
    notification = notifications_helpers.list_notifications()[0]
    assert notification["status"] == "error" and notification["message"] == run["error_text"]


def test_the_judge_receives_the_results_of_the_nodes(
    env: WorkflowEnv,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The judge receives the results of the nodes.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
        monkeypatch: Pytest monkeypatch fixture.
    """
    svc, write, _, _ = env
    _simple_flow(write)
    received: dict = {}

    async def spy(
        agent_: Agent,
        name: str,
        run_id: str,
        description: str,
        nodes: list[dict[str, Any]],
        results: dict[str, str],
        final_text: str,
    ) -> tuple[bool, str]:
        """Record what the judge receives.

        Args:
            agent_: Agent of the judge (ignored).
            name: Workflow name.
            run_id: Id of the run.
            description: Description of the workflow.
            nodes: Nodes of the workflow.
            results: Result of every node.
            final_text: Final output of the run.

        Returns:
            ``(True, "")``: the run is accepted.
        """
        received.update(name=name, results=dict(results), final=final_text)
        return True, ""

    monkeypatch.setattr(workflow_judge, "judge_run", spy)

    async def go() -> dict:
        """Start ``ok-flow`` and wait for it.

        Returns:
            The outcome of the run.
        """
        started = await svc.start_run("ok-flow")
        return await started["task"]

    _run(go())
    assert received["name"] == "ok-flow"
    assert set(received["results"]) == {"a", "b", "fin"}
    assert "FIN" in received["final"]


# ───────────────────────── 3. Judge and explainer ─────────────────────────


def _fake_agent(
    *,
    decision_ready: bool = False,
    decision: Callable[..., Awaitable[dict[str, Any]]] | None = None,
    llm: Callable[..., Awaitable[dict[str, Any]]] | None = None,
    model: str = "m-test",
    provider: str = "OPENAI",
) -> tuple[SimpleNamespace, dict[str, int]]:
    """Build an agent with the real prompt renderer and a stubbed LLM boundary.

    Args:
        decision_ready: Whether the decision model is ready.
        decision: Coroutine function that answers the decision call.
        llm: Coroutine function that answers the ``llm_process`` call.
        model: Chat model of the agent.
        provider: Provider of that model.

    Returns:
        ``(agent, calls)``: the agent and a counter of the decision and LLM calls.
    """
    calls = {"decision": 0, "llm": 0}

    async def _decision(state: str | dict[str, Any], questions: dict[str, Any]) -> dict[str, Any]:
        """Count the decision call and delegate it.

        Args:
            state: State sent to the decision model.
            questions: Questions sent to the decision model.

        Returns:
            The answer of the decision stub.
        """
        calls["decision"] += 1
        return await decision(state, questions)

    async def _llm(**kwargs: Any) -> dict[str, Any]:
        """Count the LLM call and delegate it.

        Args:
            **kwargs: Arguments of ``llm_process``.

        Returns:
            The answer of the LLM stub.
        """
        calls["llm"] += 1
        return await llm(**kwargs)

    fake = SimpleNamespace(
        decision_ready=decision_ready, decision=_decision, llm_process=_llm,
        prompt=agent.prompt, default_model=model, provider=provider,
    )
    return fake, calls


_USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "total_time": 0.1}
_NODES = [{"id": "a", "type": "run"}]


def _judge(fake: SimpleNamespace, **kwargs: Any) -> tuple[bool, str]:
    """Run the judge on a run whose single node returned ``listo``.

    Args:
        fake: Agent built by ``_fake_agent``.
        **kwargs: Extra arguments for ``judge_run``.

    Returns:
        The ``(ok, reason)`` verdict.
    """
    return _run(judge_run(fake, "wf", "run-1", "hace algo", _NODES, {"a": "listo"}, "listo", **kwargs))


def _open_run_1() -> None:
    """Register workflow ``wf`` and its run ``run-1`` (its engine calls are stored as rows of the run)."""
    workflow_db.ensure_workflow("wf")
    conn = session_manager._get_connection()
    try:
        conn.execute(
            "insert or ignore into workflow_runs (run_id, workflow_name, kind, started_at) values ('run-1', 'wf', 'run', '2026-01-01T00:00:00')"
        )
        conn.commit()
    finally:
        conn.close()


def _usage_rows(query: Callable[..., list[dict]]) -> list[dict[str, Any]]:
    """Read the engine LLM calls stored as rows of ``workflow_runs``.

    Args:
        query: Function that queries the temporary database.

    Returns:
        One dict per call with its purpose, provider, model and tokens.
    """
    return query(
        "select kind as purpose, provider, model, total_tokens from workflow_runs "
        "where kind in ('output', 'decision', 'judge', 'explain') order by id"
    )


def test_judge_uses_the_decision_model_when_it_is_ready(env: WorkflowEnv) -> None:
    """Judge uses the decision model when it is ready.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
    _, _, query, _ = env
    _open_run_1()
    seen = {}

    async def decision(state: str | dict[str, Any], questions: dict[str, Any]) -> dict[str, Any]:
        """Record what the decision model receives and approve.

        Args:
            state: State sent to the decision model.
            questions: Questions sent to the decision model.

        Returns:
            An available answer with a high confidence.
        """
        seen["state"], seen["questions"] = state, questions
        return {"data": {"available": True, "answers": {"done": {"noul": 0.95}},
                         "provider": "OPENAI", "model": "d-test"}, "usage": _USAGE}

    fake, calls = _fake_agent(decision_ready=True, decision=decision)
    assert _judge(fake) == (True, "")
    assert calls == {"decision": 1, "llm": 0}
    assert seen["state"]["nodes"][0]["result"] == "listo", "the decision model receives the node results"
    assert "instructions" in seen["questions"]["done"]
    assert _usage_rows(query) == [
        {"purpose": "decision", "provider": "OPENAI", "model": "d-test", "total_tokens": 15}]
    verdict = query("select status,result from workflow_runs where kind='decision'")[0]
    assert verdict["status"] == "approved" and json.loads(verdict["result"]) == {"done": {"noul": 0.95}}


def test_decision_model_below_the_threshold_is_a_negative_verdict(env: WorkflowEnv) -> None:
    """Decision model below the threshold is a negative verdict.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
    async def decision(state: str | dict[str, Any], questions: dict[str, Any]) -> dict[str, Any]:
        """Answer with a low confidence.

        Args:
            state: State sent to the decision model (ignored).
            questions: Questions sent to the decision model (ignored).

        Returns:
            An available answer with a low confidence.
        """
        return {"data": {"available": True, "answers": {"done": {"noul": 0.2}}}, "usage": _USAGE}

    fake, _ = _fake_agent(decision_ready=True, decision=decision)
    ok, reason = _judge(fake)
    assert ok is False and reason


def test_judge_falls_back_to_the_llm_when_the_decision_model_is_not_ready(env: WorkflowEnv) -> None:
    """Judge falls back to the llm when the decision model is not ready.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
    _, _, query, _ = env
    _open_run_1()
    prompts = []

    async def llm(**kwargs: Any) -> dict[str, Any]:
        """Record the prompt and reject the run.

        Args:
            **kwargs: Arguments of ``llm_process``.

        Returns:
            A successful answer whose JSON says ``ok: false``.
        """
        prompts.append(kwargs["prompt"])
        return {"status": "success", "data": '{"ok": false, "reason": "faltó el dato"}', "usage": _USAGE}

    fake, calls = _fake_agent(decision_ready=False, llm=llm)
    assert _judge(fake) == (False, "faltó el dato")
    assert calls == {"decision": 0, "llm": 1}
    assert "listo" in prompts[0], "the LLM prompt carries the node results"
    assert [r["purpose"] for r in _usage_rows(query)] == ["judge"]
    assert query("select status from workflow_runs where kind='judge'") == [{"status": "rejected"}]


def test_judge_falls_back_to_the_llm_when_the_decision_model_is_unavailable(env: WorkflowEnv) -> None:
    """Judge falls back to the llm when the decision model is unavailable.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
    async def decision(state: str | dict[str, Any], questions: dict[str, Any]) -> dict[str, Any]:
        """Answer like a decision model that is not ready.

        Args:
            state: State sent to the decision model (ignored).
            questions: Questions sent to the decision model (ignored).

        Returns:
            An answer with ``available`` false.
        """
        return {"data": {"available": False}}

    async def llm(**kwargs: Any) -> dict[str, Any]:
        """Approve the run.

        Args:
            **kwargs: Arguments of ``llm_process`` (ignored).

        Returns:
            A successful answer whose JSON says ``ok: true``.
        """
        return {"status": "success", "data": '{"ok": true}', "usage": _USAGE}

    fake, calls = _fake_agent(decision_ready=True, decision=decision, llm=llm)
    assert _judge(fake) == (True, "")
    assert calls == {"decision": 1, "llm": 1}


@pytest.mark.parametrize("response", [
    {"status": "success", "data": "no es json", "usage": _USAGE},
    {"status": "success", "data": '{"reason": "sin ok"}', "usage": _USAGE},
    {"status": "error", "message": "boom"},
    None,
])
def test_judge_fails_open_when_the_llm_answer_is_unusable(
    env: WorkflowEnv,
    response: dict[str, Any] | None,
) -> None:
    """Judge fails open when the llm answer is unusable.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
        response: Value of ``response`` for this case, from ``pytest.mark.parametrize``.
    """
    async def llm(**kwargs: Any) -> dict[str, Any] | None:
        """Return the answer the test is parametrized with.

        Args:
            **kwargs: Arguments of ``llm_process`` (ignored).

        Returns:
            The parametrized answer.
        """
        return response

    fake, _ = _fake_agent(llm=llm)
    assert _judge(fake) == (True, "")


def test_judge_fails_open_when_the_llm_raises_or_there_is_no_model(env: WorkflowEnv) -> None:
    """Judge fails open when the llm raises or there is no model.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
    async def llm(**kwargs: Any) -> None:
        """Fail like an LLM that is down.

        Args:
            **kwargs: Arguments of ``llm_process`` (ignored).

        Raises:
            RuntimeError: Always.
        """
        raise RuntimeError("boom")

    fake, _ = _fake_agent(llm=llm)
    assert _judge(fake) == (True, "")

    async def never(**kwargs: Any) -> None:
        """Fail the test if it is called.

        Args:
            **kwargs: Arguments of ``llm_process`` (ignored).

        Raises:
            AssertionError: Always.
        """
        raise AssertionError("must not be called")

    no_model, calls = _fake_agent(llm=never, model=None)
    assert _judge(no_model) == (True, "")
    assert calls["llm"] == 0


def test_explainer_returns_the_llm_text_or_the_generic_one(env: WorkflowEnv) -> None:
    """Explainer returns the llm text or the generic one.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
    _, _, query, _ = env
    _open_run_1()
    failures = [{"node": "a", "type": "run", "error": "código 5"}]

    async def good(**kwargs: Any) -> dict[str, Any]:
        """Explain the failure with a padded text.

        Args:
            **kwargs: Arguments of ``llm_process``; the prompt must mention the error of the node.

        Returns:
            A successful answer.
        """
        assert "código 5" in kwargs["prompt"]
        return {"status": "success", "data": "  No se pudo correr el paso a.  ", "usage": _USAGE}

    fake, _ = _fake_agent(llm=good)
    assert _run(explain_failure(fake, "wf", "run-1", "d", failures, 3)) == "No se pudo correr el paso a."
    assert [r["purpose"] for r in _usage_rows(query)] == ["explain"]

    async def bad(**kwargs: Any) -> dict[str, Any]:
        """Fail the explanation call.

        Args:
            **kwargs: Arguments of ``llm_process`` (ignored).

        Returns:
            An error answer.
        """
        return {"status": "error", "message": "boom"}

    fake, _ = _fake_agent(llm=bad)
    assert _run(explain_failure(fake, "wf", "run-1", "d", failures, 3)) == GENERIC_FAILURE_TEXT
    no_model, _ = _fake_agent(llm=bad, model=None)
    assert _run(explain_failure(no_model, "wf", "run-1", "d", failures, 3)) == GENERIC_FAILURE_TEXT


@pytest.mark.parametrize("decision", [True, False])
def test_judge_prompt_renders_in_both_variants(decision: bool) -> None:
    """Judge prompt renders in both variants.

    Args:
        decision: Value of ``decision`` for this case, from ``pytest.mark.parametrize``.
    """
    text = agent.prompt(
        "judge_workflow", decision=decision, name="wf", description="d",
        nodes_text="- a (run):\nlisto", final_text="listo",
    ) if not decision else agent.prompt("judge_workflow", decision=True)
    assert text.strip()
    assert ("listo" in text) is (not decision), "the data only goes in the prompt when there is no decision model"


# ───────────────────────── 4. Permissions ─────────────────────────


def test_router_ignores_legacy_workflows_block(env: WorkflowEnv) -> None:
    """Router ignores legacy workflows block.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
    assert _router_tool_permissions({"tools": {"read": "allow"}, "workflows": {"nightly": "allow"}}) == {
        "read": "allow",
        "skill": "allow",
        "rag": {"help": "allow", "agent_conversations": "allow"}}
    assert "workflow" not in _router_tool_permissions({"tools": {"read": "allow"}})
    assert "workflow" not in _router_tool_permissions({"tools": {"read": "allow"}, "workflows": {}})
    assert "workflow" not in _router_tool_permissions(None), "the floor tools never include workflows"


def test_subagent_frontmatter_permissions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Subagent frontmatter permissions.

    Args:
        tmp_path: Temporary directory of the test.
        monkeypatch: Pytest monkeypatch fixture.
    """
    import json

    import backend.agent.permissions as permissions

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "plain.md").write_text(
        "---\nname: plain\ndescription: d\npermissions:\n  tools:\n    read: allow\n---\n", encoding="utf-8")
    (agents_dir / "both.md").write_text(
        "---\nname: both\ndescription: d\npermissions:\n  tasks:\n    helper: allow\n---\n",
        encoding="utf-8")
    monkeypatch.setattr(permissions, "get_agents_dir", lambda: agents_dir)

    assert json.loads(get_tool_permissions("plain")["data"]) == {"read": "allow"}
    assert json.loads(get_tool_permissions("both")["data"]) == {
        "task": {"helper": "allow"}}


# ───────────────────────── 5. Chat ─────────────────────────


def test_chat_always_goes_through_the_agent_loop(env: WorkflowEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    """Chat always goes through the agent loop.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
        monkeypatch: Pytest monkeypatch fixture.
    """
    import backend.routes.chat as chat

    svc, write, query, _ = env
    _simple_flow(write, "nightly")
    created = []

    class StubLoop:
        """Agent loop that answers a fixed text."""
        def __init__(self, agent: Agent, session_manager: SessionManager) -> None:
            """Register the instance.

            Args:
                agent: Agent singleton.
                session_manager: Session manager.
            """
            created.append(self)

        async def run(self, **kwargs: Any) -> AsyncIterator[str]:
            """Answer a fixed text.

            Args:
                **kwargs: Arguments of ``AgentLoop.run`` (ignored).

            Yields:
                SSE events.
            """
            yield 'data: {"type": "chunk", "content": "hola"}\n\n'
            yield "data: [DONE]\n\n"

    monkeypatch.setattr(chat, "AgentLoop", StubLoop)
    app = FastAPI()
    app.include_router(chat.router, prefix="/api")
    response = TestClient(app).post(
        "/api/chat", data={"message": "ejecutá el workflow nightly", "session_id": "s-chat-1"})

    assert response.status_code == 200 and "hola" in response.text
    assert len(created) == 1
    assert query("select 1 from workflow_runs") == [], "chatting never starts a workflow"


def test_selecting_a_workflow_for_the_chat_is_not_an_endpoint() -> None:
    """Selecting a workflow for the chat is not an endpoint."""
    from backend.main import app as main_app

    paths = set(main_app.openapi()["paths"])
    assert not [p for p in paths if "workflow" in p and "select" in p]
    assert "/api/workflows" in paths and "/api/workflows/{name}/run" in paths
    assert "/api/notifications" in paths


# ───────────────────────── 6. Notifications and scheduled tasks ─────────────────────────


def test_notifications_api_unread_count_read_and_delete(env: WorkflowEnv) -> None:
    """Notifications api unread count read and delete.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
    import backend.routes.notifications as routes

    _open_run_1()
    for i in range(3):
        notifications_helpers.add_notification(
            "workflow", f"t{i}", "success", "listo", run_id=f"r{i}", workflow_name="wf")

    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    client = TestClient(app)

    items = client.get("/api/notifications").json()["notifications"]
    assert len(items) == 3 and sum(1 for n in items if not n["read"]) == 3

    assert client.post("/api/notifications/read").status_code == 200
    items = client.get("/api/notifications").json()["notifications"]
    assert all(n["read"] for n in items), "opening the bell marks everything as read"

    assert client.delete(f"/api/notifications/{items[0]['id']}").status_code == 200
    assert client.delete(f"/api/notifications/{items[0]['id']}").status_code == 404
    assert len(client.get("/api/notifications").json()["notifications"]) == 2

    assert client.delete("/api/notifications").status_code == 200
    assert client.get("/api/notifications").json()["notifications"] == []


SCHEDULED_FLOW = """
name: {name}
description: dos nodos y un horario
schedule:
  enabled: {enabled}
  slots:
{slots}
nodes:
- {{id: a, type: run, step: 1, run: 'echo A', final: true}}
"""
"""Workflow with a ``schedule`` block; ``slots`` is already indented YAML."""


def _write_scheduled(
    write: Callable[[str, str], None],
    name: str,
    slots: str,
    enabled: str = "true",
) -> None:
    """Write a scheduled workflow.

    Args:
        write: Function that writes a workflow YAML.
        name: Workflow name.
        slots: YAML of the slots, indented under ``slots:``.
        enabled: ``true`` or ``false``.
    """
    write(name, SCHEDULED_FLOW.format(name=name, enabled=enabled, slots=slots))


def test_schedule_block_is_validated() -> None:
    """The schedule block accepts a list of slots and rejects the invalid ones."""
    from backend.agent.utils.workflow_validator import normalize_schedule

    ok, error = normalize_schedule({"enabled": True, "slots": [{"time": "09:00", "days": [3, 1, 1]}]})
    assert error is None and ok == {"enabled": True, "slots": [{"time": "09:00", "days": [1, 3]}]}
    assert normalize_schedule(None) == (None, None)
    for bad in (
        "9",
        {"enabled": "yes", "slots": [{"time": "09:00", "days": [1]}]},
        {"enabled": True, "slots": []},
        {"enabled": True, "slots": [{"time": "25:00", "days": [1]}]},
        {"enabled": True, "slots": [{"time": "09:00", "days": []}]},
        {"enabled": True, "slots": [{"time": "09:00", "days": [7]}]},
    ):
        assert normalize_schedule(bad)[1], bad


def test_only_the_workflows_with_a_schedule_are_scheduled_tasks(env: WorkflowEnv) -> None:
    """Only the workflows with a schedule block are listed as scheduled tasks.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
    _, write, _, _ = env
    _simple_flow(write, "manual")
    _write_scheduled(write, "diaria", "  - {time: '08:00', days: [1, 2]}\n  - {time: '18:30', days: [5]}")

    tasks = scheduler_helpers.list_tasks()
    assert [t["name"] for t in tasks] == ["diaria"]
    assert tasks[0]["time"] == "08:00" and tasks[0]["days"] == [1, 2]
    assert tasks[0]["repetitions"] == [{"time": "18:30", "days": [5]}]
    assert tasks[0]["enabled"] is True


def test_updating_a_task_rewrites_its_schedule_and_keeps_the_nodes(env: WorkflowEnv) -> None:
    """Updating a task rewrites its schedule block and keeps the nodes of the workflow.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
    _, write, _, _ = env
    _write_scheduled(write, "diaria", "  - {time: '08:00', days: [1]}")

    result = scheduler_helpers.update_task("diaria", time_str="21:15", days=[0, 6], enabled=False)
    assert result["status"] == "success"
    task = scheduler_helpers.get_task("diaria")
    assert task and task["time"] == "21:15" and task["days"] == [0, 6] and task["enabled"] is False
    assert loader.load_workflow("diaria")["data"]["nodes"][0]["id"] == "a"

    assert scheduler_helpers.update_task("diaria", time_str="99:99")["status"] == "error"
    assert scheduler_helpers.update_task("diaria", prompt="otro")["status"] == "error"
    assert scheduler_helpers.update_task("no-existe", enabled=True)["status"] == "error"


def test_deleting_a_scheduled_task_removes_its_file_runs_and_notifications(env: WorkflowEnv) -> None:
    """Deleting a scheduled task removes its YAML, its rows and only its notifications.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
    _, write, query, tmp = env
    _write_scheduled(write, "diaria", "  - {time: '08:00', days: [1]}")
    _open_run_1()
    workflow_db.ensure_workflow("diaria")
    notifications_helpers.add_notification("schedule", "diaria", "success", "ok", workflow_name="diaria")
    notifications_helpers.add_notification("workflow", "wf", "success", "ok", workflow_name="wf")

    assert scheduler_helpers.delete_task("diaria")["status"] == "success"
    assert not (tmp / "workflows" / "diaria.yaml").exists()
    assert [n["workflow_name"] for n in notifications_helpers.list_notifications()] == ["wf"]
    assert query("select 1 from workflows where name='diaria'") == []


def test_the_scheduler_starts_a_due_slot_once_and_notifies_as_schedule(
    env: WorkflowEnv,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scheduler starts a due slot once; the run is notified as schedule and sent to Telegram.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
        monkeypatch: Pytest monkeypatch fixture.
    """
    from datetime import datetime as real_datetime

    svc, write, query, _ = env
    fixed = real_datetime(2026, 10, 21, 14, 18, 5)  # a Wednesday: 3 in the 0 = Sunday convention

    class _Clock(real_datetime):
        """Datetime whose ``now`` is a fixed instant."""

        @classmethod
        def now(cls, tz: Any = None) -> real_datetime:
            """Return the fixed instant.

            Args:
                tz: Ignored.

            Returns:
                The fixed instant.
            """
            return fixed

    sent: list[tuple[str, str, str]] = []

    async def fake_telegram(status: str, prompt: str, detail: str, finished_local: str) -> None:
        """Record what would be sent to Telegram.

        Args:
            status: ``success`` or ``error``.
            prompt: What the task does.
            detail: Result summary.
            finished_local: Finish timestamp (ignored).
        """
        sent.append((status, prompt, detail))

    monkeypatch.setattr(scheduler_helpers, "datetime", _Clock)
    monkeypatch.setattr(workflow_db, "datetime", _Clock)
    monkeypatch.setattr(service_module, "notify_telegram", fake_telegram)
    _write_scheduled(write, "diaria", "  - {time: '14:18', days: [3]}")
    _write_scheduled(write, "otro-dia", "  - {time: '14:18', days: [1]}")
    _write_scheduled(write, "pausada", "  - {time: '14:18', days: [3]}", enabled="false")

    async def go() -> None:
        """Check the schedules twice in the same minute and wait for the run."""
        scheduler = scheduler_helpers.SchedulerService()
        await scheduler._check_due_tasks()
        await scheduler._check_due_tasks()
        await asyncio.gather(*[a.task for a in list(svc._active.values()) if a.task])
        await scheduler_helpers.SchedulerService()._check_due_tasks()  # another service, same minute

    _run(go())
    runs = query("select workflow_name,source,status from workflow_runs where kind='run'")
    assert runs == [{"workflow_name": "diaria", "source": "schedule", "status": "success"}]
    notified = notifications_helpers.list_notifications()
    assert [(n["kind"], n["workflow_name"]) for n in notified] == [("schedule", "diaria")]
    assert len(sent) == 1 and sent[0][0] == "success"
    assert scheduler_helpers.list_runs()[0]["name"] == "diaria"


def test_the_creator_prompt_has_the_scheduled_task_section_only_for_a_task() -> None:
    """The workflow creator prompt adds the schedule section and drops the approval step for a task."""
    from backend.instances import agent as prompt_agent
    from backend.routes.create.workflow import _yaml_schedule

    schedule = {"enabled": True, "slots": [{"time": "09:00", "days": [1, 2]}]}
    block = _yaml_schedule(schedule)
    assert block.startswith("schedule:") and "09:00" in block and _yaml_schedule(None) == ""

    from backend.agent.utils.create_helpers import build_resource_context

    context = {
        "nombre": "n", "descripcion": "d", "conversacion": "c", "archivo": "C:/wf/n.yaml",
        "carpeta_workflows": "C:/wf", "carpeta_prompts": "C:/wf/prompts", "carpeta_workspace": "C:/ws",
        **_run(build_resource_context()),
    }
    task = prompt_agent.prompt("create_workflow", programada=True, horarios=block, **context)
    plain = prompt_agent.prompt("create_workflow", programada=False, horarios="", **context)
    assert "TAREA PROGRAMADA" in task and "09:00" in task and "aprobación del usuario" not in task
    assert "TAREA PROGRAMADA" not in plain and "aprobación del usuario" in plain
    # The folders are absolute paths and prompt_file goes without the extension.
    for rendered in (task, plain):
        assert "{%" not in rendered and "~/.config" not in rendered
        assert "C:/wf/n.yaml" in rendered and "C:/wf/prompts/analizar.toml" in rendered
        assert 'prompt_file: "analizar"' in rendered


def test_workflow_runs_notify_only_when_started_with_play(env: WorkflowEnv) -> None:
    """Workflow runs notify only when started with play.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
    svc, write, _, _ = env
    _simple_flow(write)

    async def go() -> None:
        """Start ``ok-flow`` with play and as a tool, waiting for both."""
        played = await svc.start_run("ok-flow", source="play")
        await played["task"]
        session_manager.create_session("caller-x")
        called = await svc.start_run("ok-flow", source="tool", parent_session_id="caller-x")
        await called["task"]

    _run(go())
    assert len(notifications_helpers.list_notifications()) == 1


# ───────────────────────── 7. Creators ─────────────────────────


@pytest.mark.parametrize("kind", ["agent", "skill", "tool", "workflow"])
def test_each_creator_kind_is_recorded_and_its_stream_is_untouched(env: WorkflowEnv, kind: str) -> None:
    """Each creator kind is recorded and its stream is untouched.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
        kind: Value of ``kind`` for this case, from ``pytest.mark.parametrize``.
    """
    from backend.agent.utils import creators
    from tests.creators.test_creators import _Req, _sse

    _, _, query, _ = env
    events = [
        {"type": f"{kind}_action", "content": {"action": "creating"}},
        {"type": "chunk", "content": "trabajando"},
        {"type": f"{kind}_result_final", "content": {
            "status": "success", "data": {"exist": "No", kind: "mi-item"}}},
    ]

    async def stream() -> AsyncIterator[str]:
        """Emit the events of the creator.

        Yields:
            Each event as server-sent event text.
        """
        for event in events:
            yield _sse(event)

    async def collect(wrapped: AsyncIterator[str]) -> list[str]:
        """Collect everything a stream emits.

        Args:
            wrapped: Stream to read.

        Returns:
            The chunks it emitted.
        """
        return [chunk async for chunk in wrapped]

    raw = _run(collect(stream()))
    tracked = _run(collect(creators.track_creator_run(kind, _Req(), stream())))
    assert tracked == raw, "the SSE stream reaches the client byte for byte"

    run = query("select kind,action,item_name,status from creators where role = 'result'")[0]
    assert (run["kind"], run["action"], run["item_name"], run["status"]) == (kind, "create", "mi-item", "success")


def test_a_failure_of_the_creators_registry_never_breaks_a_creator(
    env: WorkflowEnv,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure of the creators registry never breaks a creator.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
        monkeypatch: Pytest monkeypatch fixture.
    """
    from backend.agent.utils import creators
    from tests.creators.test_creators import _Req, _sse

    def boom(*args: Any, **kwargs: Any) -> None:
        """Fail like a locked database.

        Args:
            *args: Ignored.
            **kwargs: Ignored.

        Raises:
            sqlite3.OperationalError: Always.
        """
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(creators, "db_transaction", boom)

    async def stream() -> AsyncIterator[str]:
        """Emit a chunk and a final result.

        Yields:
            The two events as server-sent event text.
        """
        yield _sse({"type": "chunk", "content": "a"})
        yield _sse({"type": "agent_result_final", "content": {"status": "success", "data": {"exist": "No"}}})

    async def collect() -> list[str]:
        """Collect what the tracked stream forwards.

        Returns:
            The chunks it forwarded.
        """
        return [chunk async for chunk in creators.track_creator_run("agent", _Req(), stream())]

    assert len(_run(collect())) == 2
