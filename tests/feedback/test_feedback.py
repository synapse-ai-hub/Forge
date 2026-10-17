"""Thumbs up / down on answers: the real routes, tables and the ``turn`` event.

Runs the real ``backend.routes.feedback`` router (through ``TestClient``), the
real ``SessionManager`` and the real ``AgentLoop.run`` against an isolated
SQLite database in a temp folder, so the user's ``agent.db`` is never touched.
The only stand-ins are the module-level handles the router uses to reach that
database (``db_transaction`` and ``session_manager``).
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.agent.loop import AgentLoop
from backend.agent.loop import agent_loop as agent_loop_module
from backend.agent.session import SessionManager
from backend.instances import agent
from backend.routes import feedback as feedback_routes

SESSION = "s1"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Isolated DB with one session holding one answered turn."""
    db_path = str(tmp_path / "agent.db")
    sm = SessionManager(db_path)
    sm.create_session(SESSION)
    sm.save_message(SESSION, "user", content="hola", turn_number=1)
    sm.save_message(
        SESSION, "assistant", content="chau", turn_number=1,
        model="model-a", provider="provider-a", status="success",
    )

    @contextmanager
    def _db_transaction():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    monkeypatch.setattr(feedback_routes, "db_transaction", _db_transaction)
    monkeypatch.setattr(feedback_routes, "session_manager", sm)

    app = FastAPI()
    app.include_router(feedback_routes.router, prefix="/api")
    return TestClient(app), db_path, sm


def _rows(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM message_feedback")]
    finally:
        conn.close()


def test_save_read_change_and_remove_feedback(env):
    client, db_path, _ = env
    assert client.get(f"/api/feedback/{SESSION}").json()["data"] == {}

    assert client.put(f"/api/feedback/{SESSION}/1", json={"feedback_type": "up"}).json()["status"] == "success"
    assert client.get(f"/api/feedback/{SESSION}").json()["data"] == {"1": "up"}

    client.put(f"/api/feedback/{SESSION}/1", json={"feedback_type": "down"})
    assert client.get(f"/api/feedback/{SESSION}").json()["data"] == {"1": "down"}
    assert len(_rows(db_path)) == 1  # changed in place, not duplicated

    assert client.delete(f"/api/feedback/{SESSION}/1").json()["status"] == "success"
    assert client.get(f"/api/feedback/{SESSION}").json()["data"] == {}


def test_feedback_keeps_the_model_that_answered(env):
    client, db_path, _ = env
    client.put(f"/api/feedback/{SESSION}/1", json={"feedback_type": "down"})
    row = _rows(db_path)[0]
    assert (row["model"], row["provider"], row["feedback_type"]) == ("model-a", "provider-a", "down")


def test_invalid_requests_are_rejected_and_save_nothing(env):
    client, db_path, _ = env
    assert client.put(f"/api/feedback/{SESSION}/1", json={"feedback_type": "meh"}).json()["status"] == "error"
    assert client.put("/api/feedback/nope/1", json={"feedback_type": "up"}).json()["status"] == "error"
    assert client.put(f"/api/feedback/{SESSION}/9", json={"feedback_type": "up"}).json()["status"] == "error"
    assert _rows(db_path) == []


def test_deleting_the_session_deletes_its_feedback(env):
    client, db_path, sm = env
    client.put(f"/api/feedback/{SESSION}/1", json={"feedback_type": "up"})
    assert len(_rows(db_path)) == 1
    assert sm.delete_session(SESSION)["status"] == "success"
    assert _rows(db_path) == []


def test_the_loop_announces_the_turn_before_anything_else(env, monkeypatch):
    """The frontend ties the streamed answer to its feedback with this event."""
    _, _, sm = env
    # run() reaches the database through this module-level handle
    monkeypatch.setattr(agent_loop_module, "session_manager", sm)

    async def first_event():
        loop = AgentLoop(agent=agent, session_manager=sm)
        gen = loop.run(session_id=SESSION, user_message="otra pregunta")
        try:
            return await gen.__anext__()
        finally:
            await gen.aclose()

    event = asyncio.run(first_event())
    assert json.loads(event[len("data: "):]) == {"type": "turn", "content": 2}
