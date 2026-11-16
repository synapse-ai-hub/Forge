"""Trigger slug validation against the real backend router.

Covers the ``_valid_slug`` helper and the 422 validation paths of
``POST /triggers``. No test writes to the database: invalid payloads
are rejected before any storage access, and the 404 probes use slugs
that do not exist (read-only).
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes.triggers import _valid_slug
from backend.routes import triggers

app = FastAPI()
app.include_router(triggers.router, prefix="/api")
client = TestClient(app)

DEAD_SLUG = f"dead-slug-{uuid.uuid4().hex[:8]}"
"""Slug that does not exist, used for read-only 404 probes."""


def test_accepts_simple_slug() -> None:
    """Lowercase letters and digits are valid."""
    assert _valid_slug("mi-trigger-123") is True


def test_accepts_underscores_and_single_char() -> None:
    """Underscores and single-character slugs are valid."""
    assert _valid_slug("mi_trigger") is True
    assert _valid_slug("a") is True
    assert _valid_slug("0") is True


def test_accepts_max_length() -> None:
    """A 100-character slug is valid."""
    assert _valid_slug("a" * 100) is True


def test_rejects_empty_slug() -> None:
    """Empty and whitespace-only slugs are invalid."""
    assert _valid_slug("") is False
    assert _valid_slug("   ") is False


def test_rejects_uppercase_and_spaces() -> None:
    """Uppercase letters and spaces are invalid."""
    assert _valid_slug("Mi-Trigger") is False
    assert _valid_slug("mi trigger") is False


def test_rejects_leading_separator() -> None:
    """Slugs starting with a separator are invalid."""
    assert _valid_slug("-abc") is False
    assert _valid_slug("_abc") is False


def test_rejects_special_chars() -> None:
    """Special characters and non-ASCII text are invalid."""
    assert _valid_slug("a/b") is False
    assert _valid_slug("a@b!") is False
    assert _valid_slug("triggeñ") is False


def test_rejects_overlong_slug() -> None:
    """A 101-character slug is invalid."""
    assert _valid_slug("a" * 101) is False


def test_create_rejects_empty_slug() -> None:
    """Empty slug returns 422 with the error contract."""
    res = client.post("/api/triggers", json={"slug": "", "workflow_name": "x"})
    assert res.status_code == 422
    body = res.json()
    assert body["status"] == "error"
    assert body["message"] == "Falta el slug."


def test_create_rejects_blank_slug() -> None:
    """Whitespace-only slug is stripped and rejected as empty."""
    res = client.post("/api/triggers", json={"slug": "   ", "workflow_name": "x"})
    assert res.status_code == 422
    assert res.json()["message"] == "Falta el slug."


def test_create_rejects_invalid_slug() -> None:
    """Malformed slug returns 422 with the error contract."""
    res = client.post(
        "/api/triggers", json={"slug": "Mayúsculas!", "workflow_name": "x"}
    )
    assert res.status_code == 422
    body = res.json()
    assert body["status"] == "error"
    assert body["message"] == "Slug inválido."


def test_create_rejects_missing_workflow() -> None:
    """Valid slug without workflow returns 422 before touching storage."""
    res = client.post(
        "/api/triggers", json={"slug": "slug-valido", "workflow_name": ""}
    )
    assert res.status_code == 422
    assert res.json()["message"] == "Workflow no disponible."


def test_delete_unknown_returns_404() -> None:
    """Delete on an unknown slug returns 404 without writing anything."""
    res = client.delete(f"/api/triggers/{DEAD_SLUG}?confirm=true")
    assert res.status_code == 404
    assert res.json()["status"] == "error"


def test_patch_unknown_returns_404() -> None:
    """Patch on an unknown slug returns 404 without writing anything."""
    res = client.patch(f"/api/triggers/{DEAD_SLUG}", json={"enabled": False})
    assert res.status_code == 404
    assert res.json()["status"] == "error"
