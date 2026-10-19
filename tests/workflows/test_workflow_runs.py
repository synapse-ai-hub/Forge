"""Workflow runs: execution, retry/resume, cancel, notifications and permissions.

Runs the real ``WorkflowService``/``WorkflowRunner``, the real routes' helpers
and the real ``execute_tool`` against an isolated SQLite database and an
isolated workflows folder in a temp directory, so the user's ``agent.db`` and
``~/.config/synapseForge/workflows`` are never touched. Nodes are ``run``
nodes (shell commands), so no LLM is needed: without a selected model the
judge and the failure explainer take their fallback paths.
"""

from __future__ import annotations

import asyncio
import sqlite3
import sys

import pytest

import backend.agent.utils.db as dbmod
import backend.agent.utils.error_logger as error_logger
import backend.agent.utils.workflow_loader as loader
import backend.agent.utils.workflow_service as service_module
import backend.agent.utils.workflows_helpers as helpers
from backend.agent.permissions import filter_tools, get_tool_permissions, is_tool_allowed
from backend.agent.utils import notifications_helpers, workflow_db
from backend.agent.utils.loop_helpers import _tool_call_ctx, execute_tool
from backend.agent.utils.workflow_service import WorkflowService
from backend.instances import agent, session_manager

PY = sys.executable.replace("\\", "/")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Isolated DB and workflows folder; returns ``(service, helpers)``."""
    db_file = str(tmp_path / "agent.db")
    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()

    monkeypatch.setattr(dbmod, "DB_PATH", db_file)
    monkeypatch.setattr(error_logger, "_DB_PATH", db_file)
    monkeypatch.setattr(error_logger, "_conn", None)
    monkeypatch.setattr(session_manager, "db_path", db_file)
    monkeypatch.setattr(loader, "get_workflows_dir", lambda: wf_dir)
    monkeypatch.setattr(helpers, "_WORKFLOWS_DIR", wf_dir)

    session_manager._get_connection().close()  # creates every table (the app does it at startup)

    svc = WorkflowService()
    monkeypatch.setattr(service_module, "workflow_service", svc)

    def write(name: str, text: str) -> None:
        (wf_dir / f"{name}.yaml").write_text(text, encoding="utf-8")

    def query(sql: str, args: tuple = ()) -> list[dict]:
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]
        finally:
            conn.close()

    yield svc, write, query, tmp_path

    if error_logger._conn is not None:
        try:
            error_logger._conn.close()
        except Exception:
            pass
        error_logger._conn = None


def _run(coro):
    return asyncio.run(coro)


def _simple_flow(write, name: str = "ok-flow") -> None:
    write(name, f"""
name: {name}
description: dos nodos en paralelo y uno final
nodes:
- {{id: a, type: run, step: 1, run: 'echo A'}}
- {{id: b, type: run, step: 1, run: 'echo B'}}
- {{id: fin, type: run, step: 2, final: true, run: 'echo FIN'}}
""")


def test_success_persists_run_steps_session_and_notification(env):
    svc, write, query, _ = env
    _simple_flow(write)

    async def go():
        started = await svc.start_run("ok-flow")
        assert started["ok"], started
        return started, await started["task"]

    started, outcome = _run(go())
    assert outcome["status"] == "success"
    assert "FIN" in outcome["result"]

    run = query("select * from workflow_runs where id=?", (started["run_id"],))[0]
    assert run["status"] == "success" and run["attempt"] == 1 and run["source"] == "play"
    steps = query("select node_id,state from workflow_run_steps where run_id=? order by id", (started["run_id"],))
    assert {(s["node_id"], s["state"]) for s in steps} == {("a", "done"), ("b", "done"), ("fin", "done")}
    assert query("select name from workflows") == [{"name": "ok-flow"}]

    session = query("select title,parent_id from sessions where session_id=?", (started["run_id"],))[0]
    assert session["parent_id"] is None and session["title"].startswith("ok-flow — ")

    notifications = notifications_helpers.list_notifications()
    assert len(notifications) == 1
    assert notifications[0]["status"] == "success" and notifications[0]["read"] is False
    assert notifications[0]["workflow_name"] == "ok-flow" and notifications[0]["run_id"] == started["run_id"]


def test_failing_node_retries_resuming_from_the_failed_node(env):
    svc, write, query, tmp = env
    marker = (tmp / "marker.txt").as_posix()
    counter = (tmp / "counter.txt").as_posix()
    write("retry-flow", f"""
name: retry-flow
description: the second node fails the first time
retries: 0
nodes:
- id: a
  type: run
  step: 1
  run: '"{PY}" -c "open(r\\"{counter}\\",\\"a\\").write(\\"x\\")"'
- id: b
  type: run
  step: 2
  final: true
  run: '"{PY}" -c "import os,sys; p=r\\"{marker}\\"; ok=os.path.exists(p); open(p,\\"w\\").write(\\"1\\"); sys.exit(0 if ok else 3)"'
""")

    async def go():
        started = await svc.start_run("retry-flow")
        return started, await started["task"]

    started, outcome = _run(go())
    assert outcome["status"] == "success"
    assert (tmp / "counter.txt").read_text() == "x", "the committed node must not run again"
    steps = query("select node_id,state,attempt from workflow_run_steps where run_id=? order by id", (started["run_id"],))
    assert [(s["node_id"], s["state"], s["attempt"]) for s in steps] == [
        ("a", "done", 1), ("b", "failed", 1), ("b", "done", 2),
    ]
    assert query("select attempt from workflow_runs where id=?", (started["run_id"],))[0]["attempt"] == 2


def test_definitive_failure_uses_three_attempts_logs_and_notifies(env):
    svc, write, query, _ = env
    write("fail-flow", f"""
name: fail-flow
description: always fails
retries: 0
nodes:
- id: a
  type: run
  step: 1
  final: true
  run: '"{PY}" -c "import sys; sys.exit(5)"'
""")

    async def go():
        started = await svc.start_run("fail-flow")
        return started, await started["task"]

    started, outcome = _run(go())
    assert outcome["status"] == "error"
    assert outcome["error_text"], "the user gets an explanation (generic when no LLM is available)"
    run = query("select * from workflow_runs where id=?", (started["run_id"],))[0]
    assert run["status"] == "error" and run["attempt"] == 3 and run["error_text"]
    assert [s["state"] for s in query("select state from workflow_run_steps where run_id=? order by id", (started["run_id"],))] == ["failed"] * 3
    logged = query("select exception from error_log where source like 'workflow_service%'")
    assert any("código 5" in row["exception"] for row in logged), "the technical error goes to error_log"
    notification = notifications_helpers.list_notifications()[0]
    assert notification["status"] == "error" and notification["message"] == outcome["error_text"]


def test_cancel_is_persisted_without_notification_and_blocks_a_second_play(env):
    svc, write, query, _ = env
    write("slow-flow", f"""
name: slow-flow
description: slow
retries: 0
nodes:
- id: a
  type: run
  step: 1
  final: true
  timeout: 60000
  run: '"{PY}" -c "import time; time.sleep(40)"'
""")

    async def go():
        started = await svc.start_run("slow-flow")
        second = await svc.start_run("slow-flow")
        await asyncio.sleep(1.5)
        assert await svc.cancel(started["run_id"])
        return started, second, await started["task"]

    started, second, outcome = _run(go())
    assert second["ok"] is False and second["code"] == "conflict"
    assert outcome["status"] == "cancelled"
    assert query("select status from workflow_runs where id=?", (started["run_id"],))[0]["status"] == "cancelled"
    assert notifications_helpers.list_notifications() == []


def test_missing_reference_does_not_create_a_run(env):
    svc, write, query, _ = env
    write("broken", """
name: broken
description: broken ref
nodes:
- {id: x, type: tool, step: 1, tool: no-existe-esta-tool, final: true}
""")
    started = _run(svc.start_run("broken"))
    assert started["ok"] is False and started["code"] == "missing_refs"
    assert "No se puede ejecutar" in started["message"]
    assert query("select * from workflow_runs") == []


def test_interrupted_run_resumes_from_the_last_committed_node(env):
    svc, write, query, _ = env
    _simple_flow(write)
    run_id = workflow_db.create_run("ok-flow", None, None, "play")
    session_manager.create_session(run_id, metadata={"source": "workflow"})
    workflow_db.set_run_session(run_id, run_id)
    first = workflow_db.open_step(run_id, 1, 1, 0, "a", "run", {})
    workflow_db.commit_step(first, '"A"')
    workflow_db.open_step(run_id, 1, 1, 1, "b", "run", {})  # in flight when the backend died

    async def go():
        resumed = await svc.resume_interrupted()
        for _ in range(100):
            if not svc._active:
                break
            await asyncio.sleep(0.2)
        return resumed

    assert _run(go()) == 1
    run = query("select status,attempt from workflow_runs where id=?", (run_id,))[0]
    assert run["status"] == "success" and run["attempt"] == 2
    steps = query("select node_id,state,attempt from workflow_run_steps where run_id=? order by id", (run_id,))
    assert [(s["node_id"], s["state"], s["attempt"]) for s in steps] == [
        ("a", "done", 1), ("b", "failed", 1), ("b", "done", 2), ("fin", "done", 2),
    ]


def test_workflow_tool_respects_permissions_and_hangs_from_the_caller(env):
    svc, write, query, _ = env
    _simple_flow(write)
    _simple_flow(write, "other-flow")

    async def go():
        session_manager.create_session("caller-1")
        token = _tool_call_ctx.set({
            "parent_session_id": "caller-1",
            "tool_permissions": {"workflow": {"ok-flow": "allow"}},
        })
        try:
            allowed = await execute_tool(agent, {"name": "workflow", "args": {"name": "ok-flow"}})
            denied = await execute_tool(agent, {"name": "workflow", "args": {"name": "other-flow"}})
        finally:
            _tool_call_ctx.reset(token)
        return allowed, denied

    allowed, denied = _run(go())
    assert allowed["status"] == "success" and "<workflow id=" in allowed["data"]
    assert denied["status"] == "error" and "Permission denied" in denied["message"]
    child = query("select parent_id from sessions where parent_id='caller-1'")
    assert len(child) == 1, "the run session hangs from the caller session"
    assert notifications_helpers.list_notifications() == [], "runs called by an agent do not notify"


def test_workflows_permission_block_and_enum():
    perms = {"workflow": {"nightly": "allow", "other": "deny"}, "read": "allow"}
    assert is_tool_allowed(perms, "workflow", {"name": "nightly"}) is True
    assert is_tool_allowed(perms, "workflow", {"name": "other"}) is False
    assert is_tool_allowed(perms, "workflow", {"name": "missing"}) is False

    registry = agent.tools.tools_registry(perms)
    tool = next(t for t in registry if t["function"]["name"] == "workflow")
    assert tool["function"]["parameters"]["properties"]["name"]["enum"] == ["nightly"]
    assert filter_tools(agent.tools._tools_registry, {"read": "allow"}) != []
    assert all(t["function"]["name"] != "workflow" for t in filter_tools(agent.tools._tools_registry, {"read": "allow"}))


def test_notifications_read_delete_and_clear(env):
    _, _, _, _ = env
    workflow_db.ensure_workflow("wf")
    first = notifications_helpers.add_notification(
        "workflow", "wf", "success", "listo", run_id="r1", workflow_name="wf")
    second = notifications_helpers.add_notification(
        "workflow", "wf", "error", "falló", run_id="r2", workflow_name="wf")
    assert first and second

    assert notifications_helpers.mark_all_read() is True
    assert all(n["read"] for n in notifications_helpers.list_notifications())
    assert notifications_helpers.delete_notification(first["id"]) is True
    assert notifications_helpers.delete_notification(first["id"]) is False
    assert notifications_helpers.clear_notifications() is True
    assert notifications_helpers.list_notifications() == []


def test_notification_requires_exactly_one_origin(env):
    _, _, _, _ = env
    assert notifications_helpers.add_notification("workflow", "x", "success", "m") is None
    assert notifications_helpers.add_notification(
        "workflow", "x", "success", "m", workflow_name="wf", task_id="t") is None


def test_agent_frontmatter_workflows_block_becomes_the_workflow_permission(tmp_path, monkeypatch):
    import backend.agent.permissions as permissions

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "ops.md").write_text(
        "---\nname: ops\ndescription: d\npermissions:\n  tools:\n    read: allow\n"
        "  workflows:\n    nightly: allow\n---\nbody\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(permissions, "get_agents_dir", lambda: agents_dir)
    result = get_tool_permissions("ops")
    assert result["status"] == "success"
    import json

    assert json.loads(result["data"]) == {"read": "allow", "workflow": {"nightly": "allow"}}


def test_delete_workflow_removes_file_runs_commits_and_notifications(env, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import backend.routes.workflows as routes

    svc, write, query, tmp = env
    monkeypatch.setattr(routes, "workflow_service", svc)
    monkeypatch.setattr(routes, "get_workflows_dir", lambda: tmp / "workflows")
    _simple_flow(write, "borrable")
    _simple_flow(write, "queda")

    async def go():
        for name in ("borrable", "queda"):
            started = await svc.start_run(name)
            await started["task"]

    _run(go())
    assert len(query("select 1 from workflow_runs")) == 2

    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    client = TestClient(app)
    assert client.delete("/api/workflows/no-existe").status_code == 404
    assert client.delete("/api/workflows/..%2Fx").status_code in (400, 404)

    response = client.delete("/api/workflows/borrable")
    assert response.status_code == 200
    assert not (tmp / "workflows" / "borrable.yaml").exists()
    for table, column in (("workflows", "name"), ("workflow_runs", "workflow_name"),
                          ("notifications", "workflow_name"), ("workflow_usage", "workflow_name")):
        assert query(f"select 1 from {table} where {column}=?", ("borrable",)) == []
    assert query("select 1 from workflow_run_steps where run_id in (select id from workflow_runs where workflow_name='borrable')") == []
    # The other workflow keeps everything.
    assert (tmp / "workflows" / "queda.yaml").exists()
    assert len(query("select 1 from workflow_runs where workflow_name='queda'")) == 1
    assert len(query("select 1 from notifications where workflow_name='queda'")) == 1
    assert len(query("select 1 from workflow_run_steps")) == 3

