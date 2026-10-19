"""Creator runs: one row per run of a creator, with its result, tokens and cost.

Runs the real ``track_creator_run`` wrapper, the real ``record_creator_call``
and the real ``POST /api/create/agent`` route (through ``TestClient``) against
an isolated SQLite database in a temp folder, so the user's ``agent.db`` is
never touched. The creator streams are stand-ins that emit the same SSE events
the creators emit; the route test ends before any LLM call.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.agent.utils.db as dbmod
import backend.agent.utils.error_logger as error_logger
from backend.agent.utils import creator_runs
from backend.agent.utils.spend_handler import record_creator_call
from backend.instances import session_manager
from backend.routes.create import agent as agent_route
from backend.routes.create.common import router as create_router


class _Req:
    """Minimal creator request."""

    def __init__(self, descripcion="un agente", name=None, iterate=False):
        self.descripcion = descripcion
        self.name = name
        self.iterate = iterate
        self.model = None
        self.provider = None


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """Isolated DB with every table; returns a query helper."""
    db_file = str(tmp_path / "agent.db")
    monkeypatch.setattr(dbmod, "DB_PATH", db_file)
    monkeypatch.setattr(error_logger, "_DB_PATH", db_file)
    monkeypatch.setattr(error_logger, "_conn", None)
    monkeypatch.setattr(session_manager, "db_path", db_file)
    session_manager._get_connection().close()

    def query(sql: str, args: tuple = ()) -> list[dict]:
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]
        finally:
            conn.close()

    yield query

    if error_logger._conn is not None:
        try:
            error_logger._conn.close()
        except Exception:
            pass
        error_logger._conn = None


async def _drain(kind: str, req, events: list, calls: list[dict] | None = None) -> list[str]:
    """Run a fake creator stream through the tracker and collect what it forwards."""

    async def stream():
        for event in events:
            for usage in (calls or []) if event.get("type") == "_calls" else []:
                record_creator_call("creator:generate", "OPENAI", "gpt-test", usage)
            if event.get("type") != "_calls":
                yield _sse(event)

    return [chunk async for chunk in creator_runs.track_creator_run(kind, req, stream())]


def test_created_item_is_recorded_with_its_tokens_and_cost(db):
    events = [
        {"type": "_calls"},
        {"type": "agent_action", "content": {"action": "creating"}},
        {"type": "agent_result_final", "content": {
            "status": "success", "message": "ok",
            "data": {"exist": "No", "agent": "revisor"}}},
    ]
    usages = [
        {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150, "total_time": 1.0},
        {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30, "total_time": 0.5},
    ]
    forwarded = asyncio.run(_drain("agent", _Req(name="revisor"), events, usages))
    assert len(forwarded) == 2, "the stream is forwarded untouched"

    run = db("select * from creator_runs")[0]
    assert (run["kind"], run["action"], run["item_name"], run["status"]) == ("agent", "create", "revisor", "success")
    assert run["description"] == "un agente"
    assert run["llm_calls"] == 2 and run["prompt_tokens"] == 120 and run["completion_tokens"] == 60
    assert run["total_tokens"] == 180
    assert run["created_at"] and run["finished_at"] and run["duration"] is not None
    # The per-call detail stays in creator_calls and adds up to the run.
    calls = db("select sum(prompt_tokens) p, sum(cost_total) c, count(*) n from creator_calls")[0]
    assert calls["n"] == 2 and calls["p"] == 120
    assert run["cost_total"] == pytest.approx(calls["c"])


def test_question_iterate_exists_and_error_actions(db):
    asyncio.run(_drain("tool", _Req(), [
        {"type": "tool_action", "content": {"action": "question", "question": "¿cuál?"}}]))
    asyncio.run(_drain("skill", _Req(name="mi-skill", iterate=True), [
        {"type": "skill_action", "content": {"action": "iterating"}},
        {"type": "skill_result", "content": {
            "status": "success", "data": {"exist": "Sí", "skill": "mi-skill"}}}]))
    asyncio.run(_drain("workflow", _Req(), [
        {"type": "workflow_result_final", "content": {
            "status": "success", "data": {"exist": "Sí", "workflow": "ya-existe"}}}]))
    asyncio.run(_drain("agent", _Req(), [{"type": "error", "content": "falló"}]))
    asyncio.run(_drain("agent", _Req(), [{"type": "chunk", "content": "hola"}]))

    rows = db("select kind,action,item_name,status from creator_runs order by id")
    assert [(r["kind"], r["action"], r["item_name"], r["status"]) for r in rows] == [
        ("tool", "question", None, "success"),
        ("skill", "iterate", "mi-skill", "success"),
        ("workflow", "exists", "ya-existe", "success"),
        ("agent", None, None, "error"),
        ("agent", "question", None, "success"),
    ]


def test_client_leaving_mid_stream_is_recorded_as_aborted(db):
    async def go():
        async def stream():
            yield _sse({"type": "chunk", "content": "a"})
            yield _sse({"type": "chunk", "content": "b"})

        gen = creator_runs.track_creator_run("agent", _Req(), stream())
        await gen.__anext__()
        await gen.aclose()

    asyncio.run(go())
    assert db("select status from creator_runs")[0]["status"] == "aborted"


def test_a_call_outside_a_run_only_goes_to_creator_calls(db):
    record_creator_call("agenda:craft-prompt", "OPENAI", "gpt-test", {"prompt_tokens": 5})
    assert db("select count(*) n from creator_calls")[0]["n"] == 1
    assert db("select count(*) n from creator_runs")[0]["n"] == 0


def test_agent_route_records_the_run_without_calling_the_llm(db, tmp_path, monkeypatch):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "revisor.md").write_text("---\nname: revisor\ndescription: d\n---\nbody\n", encoding="utf-8")
    monkeypatch.setattr(agent_route, "_AGENTS_DIR", agents_dir)

    app = FastAPI()
    app.include_router(create_router, prefix="/api")
    client = TestClient(app)
    response = client.post("/api/create/agent", json={"descripcion": "un revisor", "name": "revisor"})
    assert response.status_code == 200
    assert "agent_result_final" in response.text

    run = db("select kind,action,item_name,status,description from creator_runs")[0]
    assert (run["kind"], run["action"], run["item_name"], run["status"]) == ("agent", "exists", "revisor", "success")
    assert run["description"] == "un revisor"


def test_usage_reaches_the_run_through_a_real_streaming_response(db):
    from fastapi.responses import StreamingResponse

    async def stream():
        yield _sse({"type": "tool_action", "content": {"action": "creating"}})
        await asyncio.sleep(0)
        record_creator_call("creator:generate", "OPENAI", "gpt-test", {"prompt_tokens": 7, "completion_tokens": 3})
        yield _sse({"type": "tool_result_final", "content": {
            "status": "success", "data": {"exist": "No", "tool": "mi_tool"}}})

    app = FastAPI()

    @app.post("/run")
    async def run():
        return StreamingResponse(
            creator_runs.track_creator_run("tool", _Req(name="mi_tool"), stream()),
            media_type="text/event-stream",
        )

    assert TestClient(app).post("/run").status_code == 200
    row = db("select action,item_name,llm_calls,prompt_tokens,completion_tokens from creator_runs")[0]
    assert (row["action"], row["item_name"], row["llm_calls"]) == ("create", "mi_tool", 1)
    assert (row["prompt_tokens"], row["completion_tokens"]) == (7, 3)
