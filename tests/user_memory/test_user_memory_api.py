"""User memory endpoints against the real backend.

Uses the real ``user_memory`` router with the real ChromaDB collection and
the real Gemini embeddings — no mocks. Requires a Google API key configured
(the knowledge base stays disabled without one, and the add/update calls
fail). Each test removes the preferences it creates.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import user_memory

app = FastAPI()
app.include_router(user_memory.router, prefix="/api")
client = TestClient(app)

MARKER = f"TESTMEM-{uuid.uuid4().hex[:8]}"
"""Unique marker so test documents never collide with real preferences."""


def _add(text: str) -> dict:
    """Create a preference and return its ``data`` payload.

    Args:
        text: Preference text to store.

    Returns:
        The ``data`` dict (``{id, text}``) of the success contract.
    """
    res = client.post("/api/user-memory", json={"text": text})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "success", body
    return body["data"]


def _remove(doc_id: str) -> dict:
    """Delete a preference and return the full contract body.

    Args:
        doc_id: Document id to delete.

    Returns:
        The contract body of the DELETE response.
    """
    res = client.delete(f"/api/user-memory/{doc_id}")
    assert res.status_code == 200, res.text
    return res.json()


def _list() -> list[dict]:
    """Return every stored preference.

    Returns:
        The ``data.preferences`` list of the GET response.
    """
    res = client.get("/api/user-memory")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "success", body
    return body["data"]["preferences"]


def test_add_list_delete_roundtrip() -> None:
    """Add, list (found by id) and delete a preference."""
    created = _add(f"{MARKER} prefiere respuestas cortas")
    try:
        assert created["text"] == f"{MARKER} prefiere respuestas cortas"
        prefs = _list()
        assert any(p["id"] == created["id"] for p in prefs)
    finally:
        assert _remove(created["id"])["status"] == "success"
    assert all(p["id"] != created["id"] for p in _list())


def test_rejects_empty_text() -> None:
    """Empty text is rejected with 422 by the request model."""
    res = client.post("/api/user-memory", json={"text": ""})
    assert res.status_code == 422


def test_whitespace_only_returns_error_contract() -> None:
    """Blank text passes the model but returns the error contract."""
    res = client.post("/api/user-memory", json={"text": "   "})
    assert res.status_code == 200
    assert res.json()["status"] == "error"


def test_rejects_overlong_text() -> None:
    """Text over 500 chars is rejected with 422 by the request model."""
    res = client.post("/api/user-memory", json={"text": f"{MARKER} " + "x" * 493})
    assert res.status_code == 422


def test_unicode_text_roundtrip() -> None:
    """Accented text and emoji survive the add/delete cycle."""
    created = _add(f"{MARKER} prefiere té ☕ y eñes: niño")
    try:
        assert created["text"] == f"{MARKER} prefiere té ☕ y eñes: niño"
    finally:
        assert _remove(created["id"])["status"] == "success"


def test_update_revectorizes() -> None:
    """PUT changes the text and the listing shows the new one."""
    created = _add(f"{MARKER} texto original")
    try:
        res = client.put(
            f"/api/user-memory/{created['id']}",
            json={"text": f"{MARKER} texto editado"},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "success", body
        assert body["data"]["text"] == f"{MARKER} texto editado"
        prefs = _list()
        match = [p for p in prefs if p["id"] == created["id"]]
        assert len(match) == 1 and match[0]["text"] == f"{MARKER} texto editado"
    finally:
        assert _remove(created["id"])["status"] == "success"


def test_update_nonexistent_returns_error() -> None:
    """PUT on an unknown id returns the error contract."""
    res = client.put(
        "/api/user-memory/pref_inexistente_test",
        json={"text": f"{MARKER} no se guarda"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "error"


def test_delete_nonexistent_returns_error() -> None:
    """DELETE on an unknown id returns the error contract."""
    assert _remove("pref_inexistente_test")["status"] == "error"


def test_double_delete_second_fails() -> None:
    """Deleting twice: first success, second error contract."""
    created = _add(f"{MARKER} borrado doble")
    assert _remove(created["id"])["status"] == "success"
    assert _remove(created["id"])["status"] == "error"
