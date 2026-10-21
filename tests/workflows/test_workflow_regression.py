"""Regression tests for the workflow redesign.

Each test pins a decision taken on purpose, checked through its contract (rows
in the tables, HTTP responses, what the agent sees) and not through internals.
Everything runs against an isolated SQLite database and workflows folder in a
temp directory; no real LLM is called (the judge and the explainer are stubbed
at the LLM boundary, ``agent.decision`` / ``agent.llm_process``).

Covers: tables and migration, engine (backoff, parallelism, judge gate),
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
from backend.agent.permissions import get_tool_permissions, is_tool_allowed
from backend.agent.utils import notifications_helpers, workflow_db
from backend.agent.utils import workflow_judge
from backend.agent.utils.workflow_judge import GENERIC_FAILURE_TEXT, explain_failure, judge_run
from backend.agent.utils.workflow_service import WorkflowService
from backend.instances import agent, session_manager
from tests.workflows.test_workflow_runs import PY, _run, _simple_flow, env  # noqa: F401 (env is a fixture)

NEW_TABLES = {
    "workflows", "workflow_runs", "workflow_run_steps",
    "notifications", "creator_runs",
}


# ───────────────────────── 1. Tables and migration ─────────────────────────


def test_an_existing_database_without_the_new_tables_gets_them(env):
    _, _, query, _ = env
    conn = session_manager._get_connection()
    try:
        for table in ("notifications", "workflow_run_steps",
                      "workflow_runs", "workflows", "creator_runs"):
            conn.execute(f"DROP TABLE {table}")
        conn.commit()
    finally:
        conn.close()
    assert not NEW_TABLES & {r["name"] for r in query("select name from sqlite_master where type='table'")}

    session_manager._get_connection().close()  # what the app does on every start
    assert NEW_TABLES <= {r["name"] for r in query("select name from sqlite_master where type='table'")}


def test_notifications_origin_is_enforced_by_the_table(env):
    _, _, query, tmp = env
    workflow_db.ensure_workflow("wf")
    conn = sqlite3.connect(str(tmp / "agent.db"))
    insert = (
        "insert into notifications (kind,workflow_name,task_id,title,status,created_at) "
        "values ('workflow',?,?,'t','success','2026-01-01T00:00:00')"
    )
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(insert, ("wf", "task-1"))  # both origins
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(insert, (None, None))  # no origin
        conn.execute(insert, ("wf", None))
        conn.commit()
    finally:
        conn.close()
    assert len(query("select 1 from notifications")) == 1


# ───────────────────────── 2. Engine ─────────────────────────


def test_attempts_back_off_exponentially_and_stop_at_three(env, monkeypatch):
    svc, write, query, _ = env
    waits: list[float] = []

    async def fake_backoff(cancel_event, seconds):
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

    async def go():
        started = await svc.start_run("always-fails")
        return started, await started["task"]

    started, outcome = _run(go())
    assert waits == [2, 4], "two waits between three attempts, doubling"
    assert outcome["status"] == "error"
    assert query("select attempt from workflow_runs where id=?", (started["run_id"],))[0]["attempt"] == 3


def test_different_workflows_run_in_parallel(env):
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

    async def go():
        a = await svc.start_run("par-a")
        b = await svc.start_run("par-b")
        return await asyncio.gather(a["task"], b["task"])

    first, second = _run(go())
    assert first["status"] == "success" and second["status"] == "success"
    assert {r["status"] for r in query("select status from workflow_runs")} == {"success"}


def test_a_negative_judge_ends_in_error_without_retrying(env, monkeypatch):
    svc, write, query, _ = env
    _simple_flow(write)

    async def verdict(*args, **kwargs):
        return False, "El resultado no cumple lo esperado."

    monkeypatch.setattr(workflow_judge, "judge_run", verdict)

    async def go():
        started = await svc.start_run("ok-flow")
        return started, await started["task"]

    started, outcome = _run(go())
    assert outcome["status"] == "error"
    run = query("select status,attempt,error_text from workflow_runs where id=?", (started["run_id"],))[0]
    assert run["status"] == "error" and run["attempt"] == 1
    assert run["error_text"] == "El resultado no cumple lo esperado."
    notification = notifications_helpers.list_notifications()[0]
    assert notification["status"] == "error" and notification["message"] == run["error_text"]


def test_the_judge_receives_the_results_of_the_nodes(env, monkeypatch):
    svc, write, _, _ = env
    _simple_flow(write)
    received: dict = {}

    async def spy(agent_, name, run_id, description, nodes, results, final_text):
        received.update(name=name, results=dict(results), final=final_text)
        return True, ""

    monkeypatch.setattr(workflow_judge, "judge_run", spy)

    async def go():
        started = await svc.start_run("ok-flow")
        return await started["task"]

    _run(go())
    assert received["name"] == "ok-flow"
    assert set(received["results"]) == {"a", "b", "fin"}
    assert "FIN" in received["final"]


# ───────────────────────── 3. Judge and explainer ─────────────────────────


def _fake_agent(*, decision_ready=False, decision=None, llm=None, model="m-test", provider="OPENAI"):
    """Real prompt renderer, stubbed LLM boundary."""
    calls = {"decision": 0, "llm": 0}

    async def _decision(state, questions):
        calls["decision"] += 1
        return await decision(state, questions)

    async def _llm(**kwargs):
        calls["llm"] += 1
        return await llm(**kwargs)

    fake = SimpleNamespace(
        decision_ready=decision_ready, decision=_decision, llm_process=_llm,
        prompt=agent.prompt, default_model=model, provider=provider,
    )
    return fake, calls


_USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "total_time": 0.1}
_NODES = [{"id": "a", "type": "run"}]


def _judge(fake, **kwargs):
    return _run(judge_run(fake, "wf", "run-1", "hace algo", _NODES, {"a": "listo"}, "listo", **kwargs))


def _open_run_1():
    """Register workflow ``wf`` and its run ``run-1`` (the spend of the engine calls lives in the run)."""
    workflow_db.ensure_workflow("wf")
    conn = session_manager._get_connection()
    try:
        conn.execute(
            "insert or ignore into workflow_runs (id, workflow_name, started_at) values ('run-1', 'wf', '2026-01-01T00:00:00')"
        )
        conn.commit()
    finally:
        conn.close()


def _usage_rows(query):
    rows = []
    for run in query("select usage_calls from workflow_runs where usage_calls is not null"):
        rows += [
            {k: call[k] for k in ("purpose", "provider", "model", "total_tokens")}
            for call in json.loads(run["usage_calls"])
        ]
    return rows


def test_judge_uses_the_decision_model_when_it_is_ready(env):
    _, _, query, _ = env
    _open_run_1()
    seen = {}

    async def decision(state, questions):
        seen["state"], seen["questions"] = state, questions
        return {"data": {"available": True, "answers": {"done": {"noul": 0.95}},
                         "provider": "OPENAI", "model": "d-test"}, "usage": _USAGE}

    fake, calls = _fake_agent(decision_ready=True, decision=decision)
    assert _judge(fake) == (True, "")
    assert calls == {"decision": 1, "llm": 0}
    assert seen["state"]["nodes"][0]["result"] == "listo", "the decision model receives the node results"
    assert "instructions" in seen["questions"]["done"]
    assert _usage_rows(query) == [
        {"purpose": "judge", "provider": "OPENAI", "model": "d-test", "total_tokens": 15}]


def test_decision_model_below_the_threshold_is_a_negative_verdict(env):
    async def decision(state, questions):
        return {"data": {"available": True, "answers": {"done": {"noul": 0.2}}}, "usage": _USAGE}

    fake, _ = _fake_agent(decision_ready=True, decision=decision)
    ok, reason = _judge(fake)
    assert ok is False and reason


def test_judge_falls_back_to_the_llm_when_the_decision_model_is_not_ready(env):
    _, _, query, _ = env
    _open_run_1()
    prompts = []

    async def llm(**kwargs):
        prompts.append(kwargs["prompt"])
        return {"status": "success", "data": '{"ok": false, "reason": "faltó el dato"}', "usage": _USAGE}

    fake, calls = _fake_agent(decision_ready=False, llm=llm)
    assert _judge(fake) == (False, "faltó el dato")
    assert calls == {"decision": 0, "llm": 1}
    assert "listo" in prompts[0], "the LLM prompt carries the node results"
    assert [r["purpose"] for r in _usage_rows(query)] == ["judge"]


def test_judge_falls_back_to_the_llm_when_the_decision_model_is_unavailable(env):
    async def decision(state, questions):
        return {"data": {"available": False}}

    async def llm(**kwargs):
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
def test_judge_fails_open_when_the_llm_answer_is_unusable(env, response):
    async def llm(**kwargs):
        return response

    fake, _ = _fake_agent(llm=llm)
    assert _judge(fake) == (True, "")


def test_judge_fails_open_when_the_llm_raises_or_there_is_no_model(env):
    async def llm(**kwargs):
        raise RuntimeError("boom")

    fake, _ = _fake_agent(llm=llm)
    assert _judge(fake) == (True, "")

    async def never(**kwargs):
        raise AssertionError("must not be called")

    no_model, calls = _fake_agent(llm=never, model=None)
    assert _judge(no_model) == (True, "")
    assert calls["llm"] == 0


def test_explainer_returns_the_llm_text_or_the_generic_one(env):
    _, _, query, _ = env
    _open_run_1()
    failures = [{"node": "a", "type": "run", "error": "código 5"}]

    async def good(**kwargs):
        assert "código 5" in kwargs["prompt"]
        return {"status": "success", "data": "  No se pudo correr el paso a.  ", "usage": _USAGE}

    fake, _ = _fake_agent(llm=good)
    assert _run(explain_failure(fake, "wf", "run-1", "d", failures, 3)) == "No se pudo correr el paso a."
    assert [r["purpose"] for r in _usage_rows(query)] == ["explain"]

    async def bad(**kwargs):
        return {"status": "error", "message": "boom"}

    fake, _ = _fake_agent(llm=bad)
    assert _run(explain_failure(fake, "wf", "run-1", "d", failures, 3)) == GENERIC_FAILURE_TEXT
    no_model, _ = _fake_agent(llm=bad, model=None)
    assert _run(explain_failure(no_model, "wf", "run-1", "d", failures, 3)) == GENERIC_FAILURE_TEXT


@pytest.mark.parametrize("decision", [True, False])
def test_judge_prompt_renders_in_both_variants(decision):
    text = agent.prompt(
        "judge_workflow", decision=decision, name="wf", description="d",
        nodes_text="- a (run):\nlisto", final_text="listo",
    ) if not decision else agent.prompt("judge_workflow", decision=True)
    assert text.strip()
    assert ("listo" in text) is (not decision), "the data only goes in the prompt when there is no decision model"


# ───────────────────────── 4. Permissions ─────────────────────────


def test_router_workflows_permissions(env):
    assert _router_tool_permissions({"tools": {"read": "allow"}, "workflows": {"nightly": "allow"}}) == {
        "read": "allow", "workflow": {"nightly": "allow"},
        "rag": {"help": "allow", "agent_conversations": "allow"}}
    assert "workflow" not in _router_tool_permissions({"tools": {"read": "allow"}})
    assert "workflow" not in _router_tool_permissions({"tools": {"read": "allow"}, "workflows": {}})
    assert "workflow" not in _router_tool_permissions(None), "the floor tools never include workflows"


def test_workflow_is_denied_without_a_workflows_block():
    assert is_tool_allowed({"read": "allow"}, "workflow", {"name": "nightly"}) is False
    assert is_tool_allowed({"workflow": {"nightly": "allow"}}, "workflow", {"name": "nightly"}) is True
    assert is_tool_allowed({"workflow": {"nightly": "deny"}}, "workflow", {"name": "nightly"}) is False


def test_subagent_frontmatter_permissions(tmp_path, monkeypatch):
    import json

    import backend.agent.permissions as permissions

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "plain.md").write_text(
        "---\nname: plain\ndescription: d\npermissions:\n  tools:\n    read: allow\n---\n", encoding="utf-8")
    (agents_dir / "both.md").write_text(
        "---\nname: both\ndescription: d\npermissions:\n  tasks:\n    helper: allow\n"
        "  workflows:\n    nightly: allow\n    other: deny\n---\n", encoding="utf-8")
    monkeypatch.setattr(permissions, "get_agents_dir", lambda: agents_dir)

    assert json.loads(get_tool_permissions("plain")["data"]) == {"read": "allow"}
    assert json.loads(get_tool_permissions("both")["data"]) == {
        "task": {"helper": "allow"}, "workflow": {"nightly": "allow", "other": "deny"}}


def test_scheduled_task_workflow_permissions_reach_its_subagent(env, tmp_path, monkeypatch):
    import yaml

    agents_dir = tmp_path / "sched-agents"
    agents_dir.mkdir()
    monkeypatch.setattr(scheduler_helpers, "_agent_md_path", lambda name: str(agents_dir / f"{name}.md"))
    monkeypatch.setattr(scheduler_helpers, "_agent_name_conflict", lambda name: False)

    result = scheduler_helpers.add_task(
        "nocturna", "corré el flujo", "03:00", [1],
        tool_permissions={"read": "allow", "workflow": {"nightly": "allow"}},
    )
    assert result["status"] == "success", result
    text = (agents_dir / "nocturna.md").read_text(encoding="utf-8")
    front = yaml.safe_load(text.split("---")[1])
    assert front["permissions"]["workflows"] == {"nightly": "allow"}
    assert front["permissions"]["tools"] == {"read": "allow"}, "workflow is not a flat tool"


# ───────────────────────── 5. Chat ─────────────────────────


def test_chat_always_goes_through_the_agent_loop(env, monkeypatch):
    import backend.routes.chat as chat

    svc, write, query, _ = env
    _simple_flow(write, "nightly")
    created = []

    class StubLoop:
        def __init__(self, agent, session_manager):
            created.append(self)

        async def run(self, **kwargs):
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


def test_selecting_a_workflow_for_the_chat_is_not_an_endpoint():
    from backend.main import app as main_app

    paths = set(main_app.openapi()["paths"])
    assert not [p for p in paths if "workflow" in p and "select" in p]
    assert "/api/workflows" in paths and "/api/workflows/{name}/run" in paths
    assert "/api/notifications" in paths


# ───────────────────────── 6. Notifications and scheduled tasks ─────────────────────────


def test_notifications_api_unread_count_read_and_delete(env):
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


def test_deleting_a_scheduled_task_removes_only_its_notifications(env, tmp_path, monkeypatch):
    agents_dir = tmp_path / "sched-agents"
    agents_dir.mkdir()
    monkeypatch.setattr(scheduler_helpers, "_agent_md_path", lambda name: str(agents_dir / f"{name}.md"))
    monkeypatch.setattr(scheduler_helpers, "_agent_name_conflict", lambda name: False)

    task = scheduler_helpers.add_task("diaria", "resumen", "08:00", [1])["task"]
    _open_run_1()
    notifications_helpers.add_notification("task", "diaria", "success", "ok", task_id=task["id"])
    notifications_helpers.add_notification("workflow", "wf", "success", "ok", workflow_name="wf")

    assert scheduler_helpers.delete_task(task["id"])["status"] == "success"
    left = notifications_helpers.list_notifications()
    assert [n["workflow_name"] for n in left] == ["wf"]


def test_workflow_runs_notify_only_when_started_with_play(env):
    svc, write, _, _ = env
    _simple_flow(write)

    async def go():
        played = await svc.start_run("ok-flow", source="play")
        await played["task"]
        session_manager.create_session("caller-x")
        called = await svc.start_run("ok-flow", source="tool", parent_session_id="caller-x")
        await called["task"]

    _run(go())
    assert len(notifications_helpers.list_notifications()) == 1


# ───────────────────────── 7. Creators ─────────────────────────


@pytest.mark.parametrize("kind", ["agent", "skill", "tool", "workflow"])
def test_each_creator_kind_is_recorded_and_its_stream_is_untouched(env, kind):
    from backend.agent.utils import creator_runs
    from tests.creators.test_creator_runs import _Req, _sse

    _, _, query, _ = env
    events = [
        {"type": f"{kind}_action", "content": {"action": "creating"}},
        {"type": "chunk", "content": "trabajando"},
        {"type": f"{kind}_result_final", "content": {
            "status": "success", "data": {"exist": "No", kind: "mi-item"}}},
    ]

    async def stream():
        for event in events:
            yield _sse(event)

    async def collect(wrapped):
        return [chunk async for chunk in wrapped]

    raw = _run(collect(stream()))
    tracked = _run(collect(creator_runs.track_creator_run(kind, _Req(), stream())))
    assert tracked == raw, "the SSE stream reaches the client byte for byte"

    run = query("select kind,action,item_name,status from creator_runs")[0]
    assert (run["kind"], run["action"], run["item_name"], run["status"]) == (kind, "create", "mi-item", "success")


def test_a_failure_of_the_run_registry_never_breaks_a_creator(env, monkeypatch):
    from backend.agent.utils import creator_runs
    from tests.creators.test_creator_runs import _Req, _sse

    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(creator_runs, "db_transaction", boom)

    async def stream():
        yield _sse({"type": "chunk", "content": "a"})
        yield _sse({"type": "agent_result_final", "content": {"status": "success", "data": {"exist": "No"}}})

    async def collect():
        return [chunk async for chunk in creator_runs.track_creator_run("agent", _Req(), stream())]

    assert len(_run(collect())) == 2
