"""Persistence helpers for triggers: registry with mapped workflow and secret hash.

Tables: ``triggers`` (slug is the id, mapped to ``workflows(name)`` with a
secret hash that is only shown once at creation and rotation).

Every function manages its own connection, never raises and logs failures
to ``error_log`` via ``log_error``. All timestamps are local time
(``datetime.now()``), never UTC.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from typing import Any

from backend.agent.utils.db import db_transaction, get_connection
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.queries import load_query


def _now() -> str:
    """Return the current local time.

    Returns:
        The time in ISO format.
    """
    return datetime.now().isoformat()


def _hash_secret(secret: str) -> str:
    """Hash a trigger secret for storage.

    The hash is also the HMAC key for inbound verification:
    the caller computes ``sha256(secret)`` then
    ``HMAC(hash, timestamp.body)``.

    Args:
        secret: Plain secret shown once to the user.

    Returns:
        Hex digest of the secret.
    """
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def workflow_exists(workflow_name: str) -> bool:
    """Tell whether a workflow exists for mapping a trigger.

    Args:
        workflow_name: Workflow name to validate.

    Returns:
        ``True`` when the workflow exists.
    """
    try:
        with get_connection() as conn:
            row = conn.execute(
                load_query("triggers/workflow_exists.sql"), (workflow_name,)
            ).fetchone()
            return row is not None
    except Exception as exc:
        log_error(str(exc), source="trigger_db.py:workflow_exists")
        return False


def create_trigger(slug: str, workflow_name: str) -> dict[str, Any] | None:
    """Create a trigger mapped to a workflow with a new secret.

    Args:
        slug: Trigger identifier (unique).
        workflow_name: Workflow the trigger launches.

    Returns:
        Dict with ``slug``, ``workflow_name`` and plain ``secret`` shown
        once, ``{"error": "workflow_not_found"}`` when the workflow does
        not exist, ``{"error": "duplicate"}`` when the slug already
        exists, or ``None`` on storage failure so the service can map
        422, 409 and 500.
    """
    try:
        if not workflow_exists(workflow_name):
            return {"error": "workflow_not_found"}
        if get_trigger(slug) is not None:
            return {"error": "duplicate"}
        secret = secrets.token_urlsafe(32)
        secret_hash = _hash_secret(secret)
        now = _now()
        with db_transaction() as conn:
            conn.execute(
                load_query("triggers/upsert_trigger.sql"),
                (slug, workflow_name, secret_hash, now, now),
            )
        return {"slug": slug, "workflow_name": workflow_name, "secret": secret}
    except Exception as exc:
        message = str(exc).lower()
        if "unique" in message or "duplicate" in message or "already exists" in message:
            return {"error": "duplicate"}
        log_error(str(exc), source="trigger_db.py:create_trigger")
        return None


def get_trigger(slug: str) -> dict[str, Any] | None:
    """Fetch one trigger without its secret.

    Args:
        slug: Trigger identifier.

    Returns:
        The trigger as a dict, or ``None`` when it does not exist.
    """
    try:
        with get_connection() as conn:
            row = conn.execute(
                load_query("triggers/get_trigger.sql"), (slug,)
            ).fetchone()
            return dict(row) if row else None
    except Exception as exc:
        log_error(str(exc), source="trigger_db.py:get_trigger")
        return None


def get_trigger_secret(slug: str) -> str | None:
    """Fetch the secret hash of a trigger for inbound verification.

    Backend only, never exposed to the user.

    Args:
        slug: Trigger identifier.

    Returns:
        The stored secret hash, or ``None`` when it does not exist.
    """
    try:
        with get_connection() as conn:
            row = conn.execute(
                load_query("triggers/get_trigger_secret.sql"), (slug,)
            ).fetchone()
            return str(row["secret_hash"]) if row else None
    except Exception as exc:
        log_error(str(exc), source="trigger_db.py:get_trigger_secret")
        return None


def list_triggers(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    """List triggers paginated by slug, without secrets.

    Args:
        limit: Maximum number of triggers.
        offset: Number of triggers to skip.

    Returns:
        One dict per trigger.
    """
    try:
        with get_connection() as conn:
            rows = conn.execute(
                load_query("triggers/list_triggers.sql"),
                (int(limit), int(offset)),
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        log_error(str(exc), source="trigger_db.py:list_triggers")
        return []


def set_enabled(slug: str, enabled: bool) -> bool:
    """Enable or disable a trigger without deleting its history.

    Args:
        slug: Trigger identifier.
        enabled: ``True`` to accept events, ``False`` to reject them.

    Returns:
        ``True`` when the trigger was updated.
    """
    try:
        with db_transaction() as conn:
            cur = conn.execute(
                load_query("triggers/set_enabled.sql"),
                (1 if enabled else 0, _now(), slug),
            )
            return cur.rowcount > 0
    except Exception as exc:
        log_error(str(exc), source="trigger_db.py:set_enabled")
        return False


def rotate_secret(slug: str) -> dict[str, Any] | None:
    """Rotate the secret of a trigger, invalidating the previous one.

    Args:
        slug: Trigger identifier.

    Returns:
        Dict with ``slug`` and new plain ``secret`` shown once,
        or ``None`` when it could not be rotated.
    """
    try:
        with get_connection() as conn:
            row = conn.execute(
                load_query("triggers/get_trigger.sql"), (slug,)
            ).fetchone()
            if row is None:
                return None
        secret = secrets.token_urlsafe(32)
        secret_hash = _hash_secret(secret)
        with db_transaction() as conn:
            cur = conn.execute(
                load_query("triggers/rotate_secret.sql"),
                (secret_hash, _now(), slug),
            )
            if cur.rowcount == 0:
                return None
        return {"slug": slug, "secret": secret}
    except Exception as exc:
        log_error(str(exc), source="trigger_db.py:rotate_secret")
        return None


def delete_trigger(slug: str) -> bool:
    """Delete a trigger keeping its runs for audit.

    Args:
        slug: Trigger identifier.

    Returns:
        ``True`` when the trigger was deleted.
    """
    try:
        with db_transaction() as conn:
            cur = conn.execute(
                load_query("triggers/delete_trigger.sql"), (slug,)
            )
            return cur.rowcount > 0
    except Exception as exc:
        log_error(str(exc), source="trigger_db.py:delete_trigger")
        return False
