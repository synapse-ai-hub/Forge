"""Creator conversations: everything a creator does is stored in ``creators`` and can be reopened.

Runs the real ``track_creator_run`` wrapper, the real ``record_creator_call``, the history
endpoints and the real ``POST /api/create/agent`` route (through ``TestClient``) against an
isolated SQLite database in a temp folder, so the user's ``agent.db`` is never touched. The
creator streams are stand-ins that emit the same SSE events the creators emit; the route test
ends before any LLM call.
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
from backend.agent.utils import creators
from backend.agent.utils.spend_handler import record_creator_call
from backend.instances import session_manager
from backend.routes.create import agent as agent_route
from backend.routes.create.common import router as create_router
from pathlib import Path
from collections.abc import Awaitable, Callable, Coroutine, Iterator, AsyncIterator


class _Req:
    """Minimal creator request."""

    def __init__(
        self,
        descripcion: str = "un agente",
        name: str = None,
        iterate: bool = False,
        creator_id: str | None = None,
        mensajes: list[dict[str, str]] | None = None,
    ) -> None:
        """Store the fields a creator request has.

        Args:
            descripcion: Description the user wrote.
            name: Name of the item, when the user chose one.
            iterate: Whether an existing item is modified.
            creator_id: Conversation of the creator, if any.
            mensajes: Conversation so far, if any.
        """
        self.descripcion = descripcion
        self.name = name
        self.iterate = iterate
        self.model = None
        self.provider = None
        self.creator_id = creator_id
        self.mensajes = mensajes


def _sse(event: dict) -> str:
    """Format an event the way the creators stream it.

    Args:
        event: Event to send.

    Returns:
        The ``data: ...`` server-sent event text.
    """
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@pytest.fixture()
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., list[dict]]]:
    """Isolate the database with every table.

    Args:
        tmp_path: Temporary directory of the test.
        monkeypatch: Pytest monkeypatch fixture.

    Yields:
        A function that queries the temporary database.
    """
    db_file = str(tmp_path / "agent.db")
    monkeypatch.setattr(dbmod, "DB_PATH", db_file)
    monkeypatch.setattr(error_logger, "_DB_PATH", db_file)
    monkeypatch.setattr(error_logger, "_conn", None)
    monkeypatch.setattr(session_manager, "db_path", db_file)
    session_manager._get_connection().close()

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

    yield query

    if error_logger._conn is not None:
        try:
            error_logger._conn.close()
        except Exception:
            pass
        error_logger._conn = None


async def _drain(kind: str, req: _Req, events: list) -> list[str]:
    """Run a fake creator stream through the tracker and collect what it forwards.

    Args:
        kind: Kind of creator.
        req: The creator request.
        events: Events the fake creator emits; ``{"type": "_call", "usage": {...}}`` stores an LLM call.

    Returns:
        The chunks the tracker forwarded.
    """

    async def stream() -> AsyncIterator[str]:
        """Emit the fake events of the creator.

        Yields:
            The events as server-sent event text; the ``_call`` events only store an LLM call.
        """
        for event in events:
            if event.get("type") == "_call":
                record_creator_call("creator:generate", "OPENAI", "gpt-test", event["usage"])
            else:
                yield _sse(event)

    return [chunk async for chunk in creators.track_creator_run(kind, req, stream())]


def test_request_is_stored_like_messages_and_forwarded_untouched(db: Callable[..., list[dict]]) -> None:
    """Request is stored like messages and forwarded untouched.

    Args:
        db: Function that queries the temporary database.
    """
    events = [
        {"type": "reasoning", "content": "pienso"},
        {"type": "chunk", "content": "Voy a crear "},
        {"type": "chunk", "content": "el agente."},
        {"type": "tool_call", "content": {"name": "write", "args": {"file_path": "a.md"}}},
        {"type": "tool_result", "content": {"name": "write", "result": {"status": "success"}}},
        {"type": "agent_action", "content": {"action": "creating"}},
        {"type": "agent_result_final", "content": {
            "status": "success", "message": "Agente creado", "data": {"exist": "No", "agent": "revisor"}}},
    ]
    forwarded = asyncio.run(_drain("agent", _Req(name="revisor", creator_id="conv1"), events))
    assert len(forwarded) == len(events), "the stream is forwarded untouched"

    rows = db("select role,content,reasoning,tool_name,status,action,item_name,message from creators order by id")
    assert [r["role"] for r in rows] == ["user", "assistant", "tool", "result"]
    assert rows[0]["content"] == "un agente"
    assert (rows[1]["content"], rows[1]["reasoning"]) == ("Voy a crear el agente.", "pienso")
    assert rows[2]["tool_name"] == "write"
    assert (rows[3]["status"], rows[3]["action"], rows[3]["item_name"], rows[3]["message"]) == (
        "success", "create", "revisor", "Agente creado")


def test_conversation_is_rebuilt_the_way_the_page_showed_it(db: Callable[..., list[dict]]) -> None:
    """Conversation is rebuilt the way the page showed it.

    Args:
        db: Function that queries the temporary database.
    """
    first = [
        {"type": "chunk", "content": "¿Qué modelo querés?"},
        {"type": "agent_action", "content": {"action": "question"}},
    ]
    second = [
        {"type": "chunk", "content": "Listo."},
        {"type": "agent_result_final", "content": {
            "status": "success", "message": "ok", "data": {"exist": "No", "agent": "revisor"}}},
    ]
    asyncio.run(_drain("agent", _Req(creator_id="conv2"), first))
    asyncio.run(_drain("agent", _Req(creator_id="conv2", mensajes=[
        {"role": "user", "content": "un agente"}, {"role": "assistant", "content": "¿Qué modelo querés?"},
        {"role": "user", "content": "el rápido"}]), second))

    conversation = creators.get_conversation("conv2")
    assert [m["type"] for m in conversation["messages"]] == ["user", "assistant", "user", "assistant"]
    assert conversation["messages"][2]["content"] == "el rápido"
    assert conversation["historial"] == [
        {"role": "user", "content": "un agente"},
        {"role": "assistant", "content": "¿Qué modelo querés?"},
        {"role": "user", "content": "el rápido"},
        {"role": "assistant", "content": "Listo."},
    ]
    assert conversation["result"]["item_name"] == "revisor" and conversation["result"]["status"] == "success"
    assert conversation["setup"]["descripcion"] == "un agente"
    assert creators.get_conversation("no-existe") is None

    listed = creators.list_conversations("agent")
    assert [(c["creator_id"], c["item_name"], c["first_message"]) for c in listed] == [
        ("conv2", "revisor", "un agente")]
    assert creators.list_conversations("tool") == []
    assert creators.delete_conversation("conv2") and creators.get_conversation("conv2") is None


def test_the_tool_calls_of_the_tool_creator_are_not_its_result(db: Callable[..., list[dict]]) -> None:
    """The tool calls of the tool creator are not its result.

    Args:
        db: Function that queries the temporary database.
    """
    asyncio.run(_drain("tool", _Req(creator_id="conv3"), [
        {"type": "tool_call", "content": {"name": "write", "args": {}}},
        {"type": "tool_result", "content": {"name": "write", "result": "ok"}},
        {"type": "tool_action", "content": {"action": "question"}},
    ]))
    result = db("select status,action from creators where role = 'result'")[0]
    assert (result["status"], result["action"]) == ("success", "question")


def test_question_iterate_exists_and_error_actions(db: Callable[..., list[dict]]) -> None:
    """Question iterate exists and error actions.

    Args:
        db: Function that queries the temporary database.
    """
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

    rows = db("select kind,action,item_name,status from creators where role = 'result' order by id")
    assert [(r["kind"], r["action"], r["item_name"], r["status"]) for r in rows] == [
        ("tool", "question", None, "success"),
        ("skill", "iterate", "mi-skill", "success"),
        ("workflow", "exists", "ya-existe", "success"),
        ("agent", None, None, "error"),
        ("agent", "question", None, "success"),
    ]


def test_client_leaving_mid_stream_is_recorded_as_aborted(db: Callable[..., list[dict]]) -> None:
    """Client leaving mid stream is recorded as aborted.

    Args:
        db: Function that queries the temporary database.
    """
    async def go() -> None:
        """Read one chunk and close the tracked stream, like a client that leaves."""
        async def stream() -> AsyncIterator[str]:
            """Emit two chunks.

            Yields:
                The two chunk events as server-sent event text.
            """
            yield _sse({"type": "chunk", "content": "a"})
            yield _sse({"type": "chunk", "content": "b"})

        gen = creators.track_creator_run("agent", _Req(), stream())
        await gen.__anext__()
        await gen.aclose()

    asyncio.run(go())
    assert db("select status from creators where role = 'result'")[0]["status"] == "aborted"


def test_llm_calls_are_stored_under_their_conversation(db: Callable[..., list[dict]]) -> None:
    """Llm calls are stored under their conversation.

    Args:
        db: Function that queries the temporary database.
    """
    asyncio.run(_drain("agent", _Req(creator_id="conv4"), [
        {"type": "_call", "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}},
        {"type": "_call", "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}},
        {"type": "chunk", "content": "hola"},
    ]))
    calls = db("select creator_id,kind,caller,sum(prompt_tokens) p,count(*) n from creators where role = 'call'")[0]
    assert (calls["creator_id"], calls["kind"], calls["n"], calls["p"]) == ("conv4", "agent", 2, 120)
    assert all(m["type"] != "call" for m in creators.get_conversation("conv4")["messages"])


def test_a_call_outside_a_conversation_has_no_creator_id(db: Callable[..., list[dict]]) -> None:
    """A call outside a conversation has no creator id.

    Args:
        db: Function that queries the temporary database.
    """
    record_creator_call("agenda:craft-prompt", "OPENAI", "gpt-test", {"prompt_tokens": 5})
    row = db("select creator_id,kind,role from creators")[0]
    assert (row["creator_id"], row["kind"], row["role"]) == (None, "other", "call")


def test_invalid_conversation_id_gets_a_new_one(db: Callable[..., list[dict]]) -> None:
    """Invalid conversation id gets a new one.

    Args:
        db: Function that queries the temporary database.
    """
    asyncio.run(_drain("agent", _Req(creator_id="../x"), [{"type": "chunk", "content": "hola"}]))
    stored = db("select distinct creator_id from creators")[0]["creator_id"]
    assert stored != "../x" and creators.is_valid_id(stored)


def test_agent_route_stores_the_request_and_the_history_endpoints_reopen_it(
    db: Callable[..., list[dict]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Agent route stores the request and the history endpoints reopen it.

    Args:
        db: Function that queries the temporary database.
        tmp_path: Temporary directory of the test.
        monkeypatch: Pytest monkeypatch fixture.
    """
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "revisor.md").write_text("---\nname: revisor\ndescription: d\n---\nbody\n", encoding="utf-8")
    monkeypatch.setattr(agent_route, "_AGENTS_DIR", agents_dir)

    app = FastAPI()
    app.include_router(create_router, prefix="/api")
    client = TestClient(app)
    response = client.post(
        "/api/create/agent", json={"descripcion": "un revisor", "name": "revisor", "creator_id": "conv5"})
    assert response.status_code == 200
    assert "agent_result_final" in response.text

    result = db("select kind,action,item_name,status from creators where role = 'result'")[0]
    assert (result["kind"], result["action"], result["item_name"], result["status"]) == (
        "agent", "exists", "revisor", "success")

    listed = client.get("/api/create/history", params={"kind": "agent"}).json()["conversations"]
    assert [c["creator_id"] for c in listed] == ["conv5"]
    assert client.get("/api/create/history", params={"kind": "nada"}).status_code == 400
    detail = client.get("/api/create/history/conv5").json()["conversation"]
    assert detail["setup"]["name"] == "revisor" and detail["result"]["item_name"] == "revisor"
    assert client.get("/api/create/history/no-existe").status_code == 404
    assert client.delete("/api/create/history/conv5").status_code == 200
    assert client.delete("/api/create/history/conv5").status_code == 404
