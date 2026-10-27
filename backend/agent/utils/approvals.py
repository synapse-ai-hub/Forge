"""Pending shell approvals: pause-and-ask gate for the agent loop.

Every ``shell`` call made by the agent loop requires explicit user
approval. The loop creates a pending approval, yields an
``approval_required`` SSE event (the frontend shows a modal), and waits
for the user's decision. On deny or timeout the turn is cut.

State lives in memory (per backend process): approvals are ephemeral
and never survive a restart, which is the safe default.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

logger = logging.getLogger(__name__)

APPROVAL_TIMEOUT_SECONDS = 300.0
"""Seconds the loop waits for the user before cutting the turn."""

_pending: dict[str, dict] = {}
"""approval_id -> {event, approved, session_id, command, created}."""


def create_approval(session_id: str, command: str) -> str:
    """Register a pending shell approval.

    Args:
        session_id: Chat session that triggered the command.
        command: The shell command awaiting approval.

    Returns:
        The approval id the frontend resolves.
    """
    approval_id = uuid.uuid4().hex
    _pending[approval_id] = {
        "event": asyncio.Event(),
        "approved": None,
        "session_id": session_id,
        "command": command,
        "created": time.time(),
    }
    return approval_id


async def wait_approval(
    approval_id: str,
    timeout: float = APPROVAL_TIMEOUT_SECONDS,
    cancel_event: asyncio.Event | None = None,
) -> bool:
    """Wait for the user's decision on a pending approval.

    Args:
        approval_id: Id returned by :func:`create_approval`.
        timeout: Maximum wait in seconds; expiry counts as denied.
        cancel_event: When set, the wait aborts early and counts as denied
            (e.g. the user pressed Stop while the modal was open).

    Returns:
        ``True`` only when the user explicitly approved.
    """
    entry = _pending.get(approval_id)
    if entry is None:
        return False
    try:
        if cancel_event is None:
            await asyncio.wait_for(entry["event"].wait(), timeout=timeout)
        else:
            done, _pending_tasks = await asyncio.wait(
                [
                    asyncio.create_task(entry["event"].wait()),
                    asyncio.create_task(cancel_event.wait()),
                ],
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in _pending_tasks:
                task.cancel()
            if not done:
                logger.info("Approval %s timed out after %ss.", approval_id, timeout)
                _pending.pop(approval_id, None)
                return False
    except asyncio.TimeoutError:
        logger.info("Approval %s timed out after %ss.", approval_id, timeout)
        _pending.pop(approval_id, None)
        return False
    # Cancel wins over a simultaneous approve: the user pressed Stop.
    if cancel_event is not None and cancel_event.is_set():
        _pending.pop(approval_id, None)
        return False
    approved = entry.get("approved") is True
    _pending.pop(approval_id, None)
    return approved


def resolve_approval(approval_id: str, approved: bool) -> bool:
    """Resolve a pending approval with the user's decision.

    Args:
        approval_id: Id returned by :func:`create_approval`.
        approved: The user's decision.

    Returns:
        ``True`` when the approval existed and was resolved.
    """
    entry = _pending.get(approval_id)
    if entry is None:
        return False
    entry["approved"] = bool(approved)
    entry["event"].set()
    return True


def pending_approvals(session_id: str | None = None) -> list[dict]:
    """List pending approvals, optionally filtered by session.

    Args:
        session_id: When given, only approvals of that session are listed.

    Returns:
        List of ``{approval_id, session_id, command, created}`` dicts.
    """
    return [
        {
            "approval_id": approval_id,
            "session_id": entry["session_id"],
            "command": entry["command"],
            "created": entry["created"],
        }
        for approval_id, entry in _pending.items()
        if session_id is None or entry["session_id"] == session_id
    ]
