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
from pathlib import Path
from collections.abc import Awaitable, Callable, Coroutine, Iterator, AsyncIterator
from typing import Any

PY = sys.executable.replace("\\", "/")

WorkflowEnv = tuple[WorkflowService, Callable[[str, str], None], Callable[..., list[dict]], Path]
"""Fixture ``env``: service, workflow writer, database query function and temporary directory."""


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[WorkflowEnv]:
    """Isolate the database and the workflows folder.

    Args:
        tmp_path: Temporary directory of the test.
        monkeypatch: Pytest monkeypatch fixture.

    Yields:
        ``(service, write, query, tmp_path)``: the workflow service, a function that writes a
        workflow YAML, a function that queries the temporary database, and the directory.
    """
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
        """Write a workflow YAML in the temporary workflows folder.

        Args:
            name: Workflow name.
            text: YAML text.
        """
        (wf_dir / f"{name}.yaml").write_text(text, encoding="utf-8")

    def query(sql: str, args: tuple = ()) -> list[dict]:
        """Run a query on the temporary database.

        Args:
            sql: SQL to run.
            args: Query parameters.

        Returns:
            One dict per row.
        """
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


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run a coroutine to completion.

    Args:
        coro: Coroutine to run.

    Returns:
        Its result.
    """
    return asyncio.run(coro)


def _simple_flow(write: Callable[[str, str], None], name: str = "ok-flow") -> None:
    """Write a workflow with two parallel nodes and a final one.

    Args:
        write: Function that writes a workflow YAML.
        name: Workflow name.
    """
    write(name, f"""
name: {name}
description: dos nodos en paralelo y uno final
nodes:
- {{id: a, type: run, step: 1, run: 'echo A'}}
- {{id: b, type: run, step: 1, run: 'echo B'}}
- {{id: fin, type: run, step: 2, final: true, run: 'echo FIN'}}
""")


def test_success_persists_run_and_notification_without_a_session(env: WorkflowEnv) -> None:
    """Success persists the run and its notification, and never opens a session nor writes in messages.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
    svc, write, query, _ = env
    _simple_flow(write)

    async def go() -> tuple[dict, dict]:
        """Start ``ok-flow`` and wait for it.

        Returns:
            ``(started, outcome)``.
        """
        started = await svc.start_run("ok-flow")
        assert started["ok"], started
        return started, await started["task"]

    started, outcome = _run(go())
    assert outcome["status"] == "success"
    assert "FIN" in outcome["result"]

    run = query("select * from workflow_runs where run_id=? and kind='run'", (started["run_id"],))[0]
    assert run["status"] == "success" and run["attempt"] == 1 and run["source"] == "play"
    # What ended well is deleted: a finished run keeps no node commits.
    assert query("select node_id,state from workflow_run_steps where run_id=?", (started["run_id"],)) == []
    # Every node keeps its own row in workflow_runs, with the substep of its position inside the step.
    nodes = query(
        "select node_id,step,substep,status from workflow_runs where run_id=? and kind='node' order by id",
        (started["run_id"],),
    )
    assert sorted((n["node_id"], n["step"], n["substep"], n["status"]) for n in nodes) == [
        ("a", 1, 0, "success"), ("b", 1, 1, "success"), ("fin", 2, 0, "success"),
    ]
    assert query("select name from workflows") == [{"name": "ok-flow"}]

    assert query("select session_id from sessions") == [], "a run never opens a session"
    assert query("select id from messages") == [], "a run never writes in messages"

    notifications = notifications_helpers.list_notifications()
    assert len(notifications) == 1
    assert notifications[0]["status"] == "success" and notifications[0]["read"] is False
    assert notifications[0]["workflow_name"] == "ok-flow" and notifications[0]["run_id"] == started["run_id"]


def test_failing_node_retries_resuming_from_the_failed_node(env: WorkflowEnv) -> None:
    """Failing node retries resuming from the failed node.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
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

    async def go() -> tuple[dict, dict]:
        """Start ``retry-flow`` and wait for it.

        Returns:
            ``(started, outcome)``.
        """
        started = await svc.start_run("retry-flow")
        return started, await started["task"]

    started, outcome = _run(go())
    assert outcome["status"] == "success"
    assert (tmp / "counter.txt").read_text() == "x", "the committed node must not run again"
    steps = query("select node_id,state,attempt from workflow_run_steps where run_id=? order by id", (started["run_id"],))
    assert [(s["node_id"], s["state"], s["attempt"]) for s in steps] == [
        ("a", "done", 1), ("b", "failed", 1), ("b", "done", 2),
    ]
    assert query("select attempt from workflow_runs where run_id=? and kind='run'", (started["run_id"],))[0]["attempt"] == 2


def test_definitive_failure_uses_three_attempts_logs_and_notifies(env: WorkflowEnv) -> None:
    """Definitive failure uses three attempts logs and notifies.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
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

    async def go() -> tuple[dict, dict]:
        """Start ``fail-flow`` and wait for it.

        Returns:
            ``(started, outcome)``.
        """
        started = await svc.start_run("fail-flow")
        return started, await started["task"]

    started, outcome = _run(go())
    assert outcome["status"] == "error"
    assert outcome["error_text"], "the user gets an explanation (generic when no LLM is available)"
    run = query("select * from workflow_runs where run_id=? and kind='run'", (started["run_id"],))[0]
    assert run["status"] == "error" and run["attempt"] == 3 and run["error_text"]
    assert [s["state"] for s in query("select state from workflow_run_steps where run_id=? order by id", (started["run_id"],))] == ["failed"] * 3
    logged = query("select exception from error_log where source like 'workflow_service%'")
    assert any("código 5" in row["exception"] for row in logged), "the technical error goes to error_log"
    notification = notifications_helpers.list_notifications()[0]
    assert notification["status"] == "error" and notification["message"] == outcome["error_text"]


def test_cancel_is_persisted_without_notification_and_blocks_a_second_play(env: WorkflowEnv) -> None:
    """Cancel is persisted without notification and blocks a second play.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
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

    async def go() -> tuple[dict, dict, dict]:
        """Start ``slow-flow`` twice, cancel the first run and wait for it.

        Returns:
            ``(started, second, outcome)``.
        """
        started = await svc.start_run("slow-flow")
        second = await svc.start_run("slow-flow")
        await asyncio.sleep(1.5)
        assert await svc.cancel(started["run_id"])
        return started, second, await started["task"]

    started, second, outcome = _run(go())
    assert second["ok"] is False and second["code"] == "conflict"
    assert outcome["status"] == "cancelled"
    assert query("select status from workflow_runs where run_id=? and kind='run'", (started["run_id"],))[0]["status"] == "cancelled"
    assert notifications_helpers.list_notifications() == []


def test_missing_reference_does_not_create_a_run(env: WorkflowEnv) -> None:
    """Missing reference does not create a run.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
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


def test_interrupted_run_resumes_from_the_last_committed_node(env: WorkflowEnv) -> None:
    """Interrupted run resumes from the last committed node.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
    svc, write, query, _ = env
    _simple_flow(write)
    run_id = workflow_db.create_run("ok-flow", None, "play")
    first = workflow_db.open_step(run_id, 1, 1, 0, "a", "run", {})
    workflow_db.commit_step(first, '"A"')
    workflow_db.open_step(run_id, 1, 1, 1, "b", "run", {})  # in flight when the backend died

    async def go() -> int:
        """Resume the interrupted runs and wait until none is active.

        Returns:
            What ``resume_interrupted`` returned.
        """
        resumed = await svc.resume_interrupted()
        for _ in range(100):
            if not svc._active:
                break
            await asyncio.sleep(0.2)
        return resumed

    assert _run(go()) == 1
    run = query("select status,attempt from workflow_runs where run_id=? and kind='run'", (run_id,))[0]
    assert run["status"] == "success" and run["attempt"] == 2
    steps = query("select node_id,state,attempt from workflow_run_steps where run_id=? order by id", (run_id,))
    assert [(s["node_id"], s["state"], s["attempt"]) for s in steps] == [
        ("a", "done", 1), ("b", "failed", 1), ("b", "done", 2), ("fin", "done", 2),
    ]


def test_workflow_tool_respects_permissions_and_keeps_the_caller(env: WorkflowEnv) -> None:
    """Workflow tool respects permissions and keeps the caller session in the run, without opening one.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
    svc, write, query, _ = env
    _simple_flow(write)
    _simple_flow(write, "other-flow")

    async def go() -> tuple[Any, Any]:
        """Call the workflow tool from an agent that may run ``ok-flow`` only.

        Returns:
            ``(allowed, denied)``: the result of ``ok-flow`` and of ``other-flow``.
        """
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
    assert query("select session_id from sessions") == [{"session_id": "caller-1"}], "a run never opens a session"
    run = query("select parent_session_id from workflow_runs where kind='run' and workflow_name='ok-flow'")
    assert run == [{"parent_session_id": "caller-1"}], "the run keeps the session of the caller"
    assert notifications_helpers.list_notifications() == [], "runs called by an agent do not notify"


def test_workflows_permission_block_and_enum() -> None:
    """Workflows permission block and enum."""
    perms = {"workflow": {"nightly": "allow", "other": "deny"}, "read": "allow"}
    assert is_tool_allowed(perms, "workflow", {"name": "nightly"}) is True
    assert is_tool_allowed(perms, "workflow", {"name": "other"}) is False
    assert is_tool_allowed(perms, "workflow", {"name": "missing"}) is False

    registry = agent.tools.tools_registry(perms)
    tool = next(t for t in registry if t["function"]["name"] == "workflow")
    assert tool["function"]["parameters"]["properties"]["name"]["enum"] == ["nightly"]
    assert filter_tools(agent.tools._tools_registry, {"read": "allow"}) != []
    assert all(t["function"]["name"] != "workflow" for t in filter_tools(agent.tools._tools_registry, {"read": "allow"}))


def test_notifications_read_delete_and_clear(env: WorkflowEnv) -> None:
    """Notifications read delete and clear.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
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


def test_notification_requires_exactly_one_origin(env: WorkflowEnv) -> None:
    """Notification requires exactly one origin.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
    """
    _, _, _, _ = env
    assert notifications_helpers.add_notification("workflow", "x", "success", "m") is None
    assert notifications_helpers.add_notification(
        "workflow", "x", "success", "m", workflow_name="not-registered") is None


def test_agent_frontmatter_workflows_block_becomes_the_workflow_permission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Agent frontmatter workflows block becomes the workflow permission.

    Args:
        tmp_path: Temporary directory of the test.
        monkeypatch: Pytest monkeypatch fixture.
    """
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


def test_delete_workflow_removes_file_runs_commits_and_notifications(
    env: WorkflowEnv,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete workflow removes file runs commits and notifications.

    Args:
        env: Workflow service, workflow writer, database query function and temporary directory.
        monkeypatch: Pytest monkeypatch fixture.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import backend.routes.workflows as routes

    svc, write, query, tmp = env
    monkeypatch.setattr(routes, "workflow_service", svc)
    monkeypatch.setattr(routes, "get_workflows_dir", lambda: tmp / "workflows")
    _simple_flow(write, "borrable")
    _simple_flow(write, "queda")

    async def go() -> None:
        """Run the ``borrable`` and ``queda`` workflows to completion."""
        for name in ("borrable", "queda"):
            started = await svc.start_run(name)
            await started["task"]

    _run(go())
    assert len(query("select 1 from workflow_runs where kind='run'")) == 2

    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    client = TestClient(app)
    assert client.delete("/api/workflows/no-existe").status_code == 404
    assert client.delete("/api/workflows/..%2Fx").status_code in (400, 404)

    response = client.delete("/api/workflows/borrable")
    assert response.status_code == 200
    assert not (tmp / "workflows" / "borrable.yaml").exists()
    for table, column in (("workflows", "name"), ("workflow_runs", "workflow_name"),
                          ("notifications", "workflow_name")):
        assert query(f"select 1 from {table} where {column}=?", ("borrable",)) == []
    assert query("select 1 from workflow_run_steps where run_id in (select run_id from workflow_runs where workflow_name='borrable')") == []
    # The other workflow keeps everything.
    assert (tmp / "workflows" / "queda.yaml").exists()
    assert len(query("select 1 from workflow_runs where workflow_name='queda' and kind='run'")) == 1
    assert len(query("select 1 from notifications where workflow_name='queda'")) == 1
    assert query("select 1 from workflow_run_steps") == []  # a run that ended well keeps no commits

