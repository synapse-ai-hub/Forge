"""Session listing and retrieval endpoints for the chat.

Provides REST endpoints to list chat sessions, load the full message
history of a session, and delete a session. These back the frontend
sidebar that shows the conversation history.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys

from backend.agent.utils.error_logger import log_error
from backend.agent.utils.db import db_transaction, get_connection
from backend.agent.utils.queries import load_query

from fastapi import APIRouter

# ---------------------------------------------------------------------------
# Ensure the project root is in sys.path so absolute imports (backend.*)
# resolve correctly regardless of how the file is invoked.
# sessions.py is at backend/routes/ -> need 3 dirname() calls to reach root.
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.instances import session_manager
from backend.agent.utils.contract import (
    make_error_response,
    make_success_response,
    validate_response,
    zero_usage,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sessions"])


def _fetch_attachments(session_id: str) -> dict[int, list[dict]]:
    """Fetch attachment file names and sizes grouped by turn_number for a session.

    Returns:
        Dict mapping turn_number -> list of {"name": str, "size": int} dicts.
    """
    try:
        with get_connection() as conn:
            rows = conn.execute(
                load_query("attachments/list_for_session.sql"),
                (session_id,),
            ).fetchall()

        attachments: dict[int, list[dict]] = {}
        for row in rows:
            tn = row["turn_number"]
            attachments.setdefault(tn, []).append({"name": row["file_name"], "size": row["size"]})
        return attachments
    except Exception as exc:
        log_error(str(exc), source="sessions.py:_fetch_attachments")
        logger.warning("Failed to fetch attachments for session %s: %s", session_id, exc)
        return {}


@router.get("/sessions/titles")
async def list_titles():
    """Return all existing session titles.

    Returns:
        A contract response with ``data`` containing the list of titles.
    """
    if session_manager is None:
        return make_error_response(message="Session manager no disponible")
    try:
        titles = session_manager.get_all_titles()
        return validate_response(
            make_success_response(
                message="Títulos obtenidos",
                data=titles,
                usage=zero_usage(),
            )
        )
    except Exception as exc:
        log_error(str(exc), source="sessions.py:list_titles")
        logger.exception("Error listing titles: %s", exc)
        return make_error_response(message="Error al obtener los títulos")


@router.get("/sessions")
async def list_sessions():
    """Return all chat sessions ordered by most recent activity.

    Returns:
        A contract response with ``data`` containing the list of sessions.
    """
    if session_manager is None:
        return make_error_response(message="Session manager no disponible")
    try:
        sessions = session_manager.list_sessions()
        return validate_response(
            make_success_response(
                message="Sesiones obtenidas",
                data=sessions,
                usage=zero_usage(),
            )
        )
    except Exception as exc:
        log_error(str(exc), source="sessions.py:list_sessions")
        logger.exception("Error listing sessions: %s", exc)
        return make_error_response(message="Error al obtener las sesiones")


def _build_blocks(messages: list[dict]) -> list[dict] | None:
    """Build ordered blocks from assistant + tool messages in one turn.

    Each step produces a text block (if the LLM wrote something) followed
    by one tool block per tool call.  The tool result is matched to its
    tool block by iterating in reverse and looking for the last unmatched
    block with the same tool name.

    Args:
        messages: All messages in a turn, ordered by ``(turn_number, step, id)``.

    Returns:
        A list of ``{"type","content"}`` / ``{"type","name","args","result"}``
        dicts, or ``None`` if the list is empty.
    """
    blocks: list[dict] = []
    for msg in messages:
        role = msg.get("role")
        if role == "assistant":
            # Reasoning block (si existe) — va ANTES del texto/tools porque en streaming
            # el LLM razona antes de responder
            reasoning = msg.get("reasoning")
            if reasoning:
                blocks.append({"type": "reasoning", "content": reasoning})
            content = msg.get("content") or ""
            if content:
                blocks.append({"type": "text", "content": content})
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    name = tc.get("name", "")
                    args = tc.get("args", tc.get("function", {}).get("arguments", {}))
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except (json.JSONDecodeError, TypeError):
                            args = {"raw": args}
                    if not isinstance(args, dict):
                        args = {"raw": str(args)}
                    blocks.append({
                        "type": "tool",
                        "name": name,
                        "args": args,
                        "result": None,
                    })
        elif role == "tool":
            tool_name = msg.get("tool_name", "")
            raw_content = msg.get("content") or ""
            parsed: str | dict = raw_content
            try:
                parsed = json.loads(raw_content) if raw_content else ""
            except (json.JSONDecodeError, TypeError):
                parsed = raw_content
            # Match to last unmatched tool block with same name
            for i in range(len(blocks) - 1, -1, -1):
                b = blocks[i]
                if b["type"] == "tool" and b["name"] == tool_name and b.get("result") is None:
                    b["result"] = parsed
                    break

    # Fallback: fill remaining None results from assistant's tool_results
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_results"):
            trs = msg["tool_results"]
            idx = 0
            for b in blocks:
                if b["type"] == "tool" and b.get("result") is None and idx < len(trs):
                    b["result"] = trs[idx].get("result", "")
                    idx += 1

    return blocks if blocks else None


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Return the full message history of a session.

    Messages are grouped by turn. Each **assistant turn** is collapsed
    into a single message with an ordered ``blocks`` array that preserves
    the exact order of text and tool invocations.

    Args:
        session_id: The session identifier.

    Returns:
        A contract response with ``data`` containing the session id and
        the list of messages.
    """
    if session_manager is None:
        return make_error_response(message="Session manager no disponible")
    try:
        raw_messages = session_manager.load_messages(session_id)
        # "Tokens used" = the current prompt size (the last assistant message's
        # prompt_tokens), which is what fills the context window. Summing would
        # double-count the conversation history across turns.
        prompt_tokens = max(
            (int(m.get("prompt_tokens") or 0) for m in raw_messages),
            default=0,
        )
        total_tokens = max(
            (int(m.get("total_tokens") or 0) for m in raw_messages),
            default=0,
        )
        cw_str = session_manager.get_config("selected_model_context_window")
        context_window = int(cw_str) if cw_str else None
        percent = round((prompt_tokens / context_window) * 100, 2) if context_window else None
        # Fetch attachments for this session
        attachments = _fetch_attachments(session_id)
        # Group by turn_number
        turns: dict[int, list[dict]] = {}
        for msg in raw_messages:
            tn = msg.get("turn_number") or 0
            turns.setdefault(tn, []).append(msg)

        mapped: list[dict] = []
        for tn in sorted(turns.keys()):
            turn_msgs = turns[tn]

            user_msgs = [m for m in turn_msgs if m.get("role") == "user"]
            non_user = [m for m in turn_msgs if m.get("role") != "user"]

            for um in user_msgs:
                mapped.append({
                    "id": f"msg-{um.get('id')}",
                    "type": "user",
                    "content": um.get("content") or "",
                    "turn_number": tn,
                    "files": [{"name": fname} for fname in attachments.get(tn, [])],
                })

            if non_user:
                blocks = _build_blocks(non_user)
                if blocks:
                    # Acumular reasoning de todos los mensajes assistant del turno
                    # (puede haber reasoning en step de tool_calls y en step final)
                    reasoning_parts = [
                        m["reasoning"] for m in non_user
                        if m.get("role") == "assistant" and m.get("reasoning")
                    ]
                    turn_reasoning = "\n\n".join(reasoning_parts) if reasoning_parts else None
                    mapped.append({
                        "id": f"turn-{tn}",
                        "type": "assistant",
                        "content": "",  # blocks replace flat content
                        "blocks": blocks,
                        "reasoning": turn_reasoning,
                        "turn_number": tn,
                    })

        return validate_response(
            make_success_response(
                message="Mensajes obtenidos",
                data={
                    "session_id": session_id,
                    "messages": mapped,
                    "context": {
                        "context_window": context_window,
                        "prompt_tokens": prompt_tokens,
                        "total_tokens": total_tokens,
                        "percent": percent,
                    },
                },
                usage=zero_usage(),
            )
        )
    except Exception as exc:
        log_error(str(exc), source="sessions.py:get_session")
        logger.exception("Error loading session %s: %s", session_id, exc)
        return make_error_response(message="Error al obtener la sesión")


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and all its messages.

    Args:
        session_id: The session identifier to remove.

    Returns:
        A contract response indicating success or failure.
    """
    if session_manager is None:
        return make_error_response(message="Session manager no disponible")
    try:
        result = session_manager.delete_session(session_id)
        return validate_response(result)
    except Exception as exc:
        log_error(str(exc), source="sessions.py:delete_session")
        logger.exception("Error deleting session %s: %s", session_id, exc)
        return make_error_response(message="Error al eliminar la sesión")


