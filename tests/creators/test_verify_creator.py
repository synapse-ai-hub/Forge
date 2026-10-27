"""On-demand verification of creator conversations (Verificar button).

Covers the validation paths of ``POST /api/create/{kind}/verify`` and the
no-model paths of ``verify_creator`` against an isolated SQLite database, so
the user's ``agent.db`` is never touched. Paths that need the decision model
or a live LLM are not covered here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.agent.utils.db as dbmod
import backend.instances as instances_mod
from backend.agent.creator_session import CreatorSessionManager
from backend.agent.utils import frontier_helpers
from backend.agent.utils.creators import add_row
from backend.agent.utils.decision import verify_creator
from backend.agent.utils.frontier_helpers import record_block_dispatch
from backend.routes.create import agent as agent_route
from backend.routes.create import skill as skill_route
from backend.routes.create import tool as tool_route
from backend.routes.create import workflow as workflow_route
from backend.routes.create.common import router as create_router

_KINDS = ("tool", "skill", "agent", "workflow")
_ROUTES = {
    "tool": tool_route,
    "skill": skill_route,
    "agent": agent_route,
    "workflow": workflow_route,
}


@pytest.fixture()
def managers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, CreatorSessionManager]]:
    """Point the shared DB and every creator manager at a temp file.

    Args:
        tmp_path: Temporary directory of the test.
        monkeypatch: Pytest monkeypatch fixture.

    Yields:
        The creator session manager of each kind, bound to the temp DB.
    """
    db_file = str(tmp_path / "agent.db")
    monkeypatch.setattr(dbmod, "DB_PATH", db_file)
    made: dict[str, CreatorSessionManager] = {}
    for kind, route in _ROUTES.items():
        manager = CreatorSessionManager(db_path=db_file, kind=kind)
        monkeypatch.setattr(route, "creator_sessions", manager)
        made[kind] = manager
    # Create the schema: add_row/record_block_dispatch use get_connection(),
    # which does not create tables by itself.
    made["tool"]._get_connection().close()
    yield made


def _client() -> TestClient:
    """Build a test client serving the creation routes.

    Returns:
        A ``TestClient`` with the ``/api/create`` router mounted.
    """
    app = FastAPI()
    app.include_router(create_router, prefix="/api")
    return TestClient(app)


def test_verify_rejects_invalid_id() -> None:
    """Verify rejects ids with path separators on every kind."""
    client = _client()
    for kind in _KINDS:
        response = client.post(
            "/api/create/" + kind + "/verify", json={"creator_id": "../x"})
        assert response.status_code == 400


def test_verify_rejects_unknown_conversation(
    managers: dict[str, CreatorSessionManager],
) -> None:
    """Verify rejects well-formed ids with no stored rows.

    Args:
        managers: Creator session managers bound to the temp DB.
    """
    client = _client()
    for kind in _KINDS:
        response = client.post(
            "/api/create/" + kind + "/verify", json={"creator_id": "noexiste1"})
        assert response.status_code == 400
        assert response.json()["status"] == "error"


def test_verify_without_messages_returns_not_done(
    managers: dict[str, CreatorSessionManager],
) -> None:
    """Verify with rows but no user/assistant messages returns not done.

    No model is called: the empty history short-circuits first.

    Args:
        managers: Creator session managers bound to the temp DB.
    """
    add_row("conv1", "tool", "result", action="created",
            item_name="mi-tool", status="success")
    assert managers["tool"].has_rows("conv1")
    response = _client().post(
        "/api/create/tool/verify", json={"creator_id": "conv1"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["data"] == {"done": False}
    assert isinstance(body["usage"], dict)


def test_verify_creator_without_model_reports_unavailable(
    managers: dict[str, CreatorSessionManager],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """verify_creator with full history but no agent reports it as an error.

    Args:
        managers: Creator session managers bound to the temp DB.
        monkeypatch: Pytest monkeypatch fixture.
    """
    monkeypatch.setattr(instances_mod, "agent", None)
    add_row("conv2", "skill", "user", content="crea una skill",
            turn_number=1)
    add_row("conv2", "skill", "assistant", content="listo",
            turn_number=1, step=0)
    result = asyncio.run(verify_creator(managers["skill"], "conv2"))
    assert result == {"done": False, "reason": "El agente no está disponible."}


def test_resume_reads_user_text_from_creators_table(
    managers: dict[str, CreatorSessionManager],
) -> None:
    """The resume block reads user text from creators, not messages.

    Args:
        managers: Creator session managers bound to the temp DB.
    """
    add_row("conv3", "tool", "user", content="creame una tool de ping",
            turn_number=1)
    record_block_dispatch(
        "conv3", 1, 0, [(0, "call-1", "write", {"file_path": "ping.py"})])
    block = frontier_helpers.build_resume_message("conv3", managers["tool"])
    assert block is not None
    assert "creame una tool de ping" in block
    chat_block = frontier_helpers.build_resume_message("conv3")
    assert chat_block is not None
    assert "creame una tool de ping" not in chat_block
