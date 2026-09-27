"""Chat SSE streaming endpoint for the <nombre>nombre_proyecto</nombre>."""

from __future__ import annotations

import asyncio
import json
import logging
import time as _time
import os
import sys
import uuid
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

# ---------------------------------------------------------------------------
# Ensure the project root is in sys.path so absolute imports (backend.*)
# resolve correctly regardless of how the file is invoked.
# chat.py is at backend/routes/ -> need 3 dirname() calls to reach root.
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.loop import AgentLoop
from backend.agent.utils.error_logger import log_error, set_error_context, reset_error_context
from backend.utils.db import db_transaction, get_connection
from backend.instances import agent, session_manager
from backend.routes.file_text_extractor import (
    ExtractionResult,
    extract_text_from_bytes,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# Limits for attachments
MAX_ATTACHMENTS = 3
MAX_TOTAL_SIZE_MB = 25
MAX_TOTAL_SIZE_BYTES = MAX_TOTAL_SIZE_MB * 1024 * 1024


def _save_attachments(session_id: str, turn_number: int, files_data: list[tuple[str, bytes, str]]) -> None:
    """Save file attachments to the database.

    Args:
        session_id: The session identifier.
        turn_number: The turn number for this conversation turn.
        files_data: List of (filename, binary_content, extracted_text) tuples.
    """
    if not files_data:
        return
    try:
        with db_transaction() as conn:
            now = datetime.now().isoformat()
            for filename, binary_content, _extracted_text in files_data:
                conn.execute(
                    "INSERT INTO attachments (session_id, turn_number, file_name, size, content, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (session_id, turn_number, filename, len(binary_content), binary_content, now),
                )
    except Exception as exc:
        log_error(str(exc), source="backend/routes/chat.py:_save_attachments")
        logger.warning("Failed to save attachments: %s", exc)


def _get_last_assistant_text(session_id: str, turn_number: int) -> str:
    """Return the content of the last assistant message of the given turn.

    Reads from the DB (single source of truth) so the Telegram reply matches
    exactly what was persisted, avoiding intermediate tool-calling content
    that the raw SSE ``chunk`` events would include.

    Args:
        session_id: The session identifier.
        turn_number: The turn number to look for.

    Returns:
        The last assistant message content of that turn, or ``""`` if none.
    """
    try:
        msg = session_manager.get_last_assistant_message(session_id, turn_number)
        if msg:
            return (msg.get("content") or "").strip()
    except Exception as exc:
        log_error(str(exc), source="backend/routes/chat.py:_get_last_assistant_text")
        logger.warning("Failed to load last assistant message: %s", exc)

    return ""


@router.post("/chat")
async def chat_endpoint(
    request: Request,
    message: str = Form(...),
    session_id: str | None = Form(None),
    stream_id: str | None = Form(None),
    telegram_chat_id: str | None = Form(None),
    files: Optional[list[UploadFile]] = File(None),
):
    """Stream a conversation turn via Server-Sent Events.

    Accepts the user's message as ``FormData``, optionally with attached
    files, and returns a ``StreamingResponse`` with ``text/event-stream``
    content type.
    """
    # Ensure session_id exists (generate one if not provided)
    if session_id is None or not session_id.strip():
        session_id = uuid.uuid4().hex

    # Process uploaded files with limits: max 3 files, max 25 MB total
    file_contents: list[tuple[str, str]] = []  # (filename, extracted_text) for the loop
    files_data: list[tuple[str, bytes, str]] = []  # (filename, binary_content, extracted_text) for DB
    total_size = 0
    if files:
        if len(files) > MAX_ATTACHMENTS:
            logger.warning("Too many files: %d (max %d)", len(files), MAX_ATTACHMENTS)
            # Only process first MAX_ATTACHMENTS files
            files = files[:MAX_ATTACHMENTS]
        for i, file in enumerate(files):
            filename = file.filename or f"archivo_{i + 1}"
            try:
                content = await file.read()
            except Exception as exc:
                log_error(str(exc), source="backend/routes/chat.py:file_read")
                logger.warning("Error reading file %s: %s", filename, exc)
                content = b""
            
            # Check total size limit
            total_size += len(content)
            if total_size > MAX_TOTAL_SIZE_BYTES:
                logger.warning("Total size exceeds %d MB limit", MAX_TOTAL_SIZE_MB)
                break
            
            result: ExtractionResult = extract_text_from_bytes(filename, content)
            if not result.success:
                if result.error_code in ("file_too_large", "unsupported_type", "missing_dependency"):
                    logger.warning(
                        "Skipping file %s (error_code=%s): %s",
                        filename,
                        result.error_code,
                        result.error_detail or "unknown",
                    )
                    total_size -= len(content)  # don't count skipped files
                    continue
                file_contents.append((filename, result.text or f"[Error al procesar {filename}]"))
                files_data.append((filename, content, result.text or f"[Error al procesar {filename}]"))
                continue
            text = (result.text or "").strip()
            if not text:
                file_contents.append(
                    (filename, f"[Error al procesar {filename}: no se encontró texto legible en el archivo.]")
                )
                files_data.append((filename, content, f"[Error al procesar {filename}: no se encontró texto legible en el archivo.]"))
                continue
            file_contents.append((filename, text))
            files_data.append((filename, content, text))

    # Get the next turn number and save attachments
    turn_number = session_manager.get_last_turn_number(session_id) + 1
    if files_data:
        _save_attachments(session_id, turn_number, files_data)


    logger.info("Processing chat request for session_id=%s, turn_number=%d", session_id, turn_number)

    # Create a cancellation event tied to the client disconnection
    stream_cancel_event = asyncio.Event()

    async def event_stream():
        _t0 = _time.time()
        # # logger.info("[DEBUG_TIEMPO_SSE] event_stream() started — t=%.3f", _t0)
        # Set error context for this request (inside event_stream so set/reset share same async context)
        error_ctx_token = set_error_context(session_id=session_id, turn_number=turn_number)
        try:
            # Fase 3: si hay workflow seleccionado y válido, corre el
            # WorkflowRunner determinista. Si falla la carga, fallback a
            # smart con aviso. Mismos eventos SSE y Telegram.
            selected_workflow = "smart"
            try:
                raw_selection = session_manager.get_config("selected_workflow")
                if raw_selection and raw_selection.strip():
                    selected_workflow = raw_selection.strip()
            except Exception as exc:
                log_error(str(exc), source="backend/routes/chat.py:selected_workflow")
                selected_workflow = "smart"
            workflow_data = None
            if selected_workflow != "smart":
                try:
                    from backend.agent.utils.workflow_loader import load_workflow

                    loaded = load_workflow(selected_workflow)
                    if isinstance(loaded, dict) and loaded.get("status") == "success":
                        workflow_data = loaded.get("data")
                    else:
                        logger.warning("Workflow '%s' inválido, fallback a smart", selected_workflow)
                        yield f"data: {json.dumps({'type': 'chunk', 'content': f'_Workflow {selected_workflow} inválido, usando flujo smart._'}, ensure_ascii=False)}\n\n"
                        workflow_data = None
                except Exception as exc:
                    log_error(str(exc), source="backend/routes/chat.py:load_workflow")
                    yield f"data: {json.dumps({'type': 'chunk', 'content': f'_Workflow {selected_workflow} no disponible, usando flujo smart._'}, ensure_ascii=False)}\n\n"
                    workflow_data = None
            # Fase 6: fuente única de eventos. Workflow válido usa el runner
            # determinista, si no el flujo smart. Ambos pasan por el mismo
            # consumo y el mismo envío a Telegram.
            if workflow_data is not None:
                from backend.agent.utils.workflow_runner import WorkflowRunner

                runner = WorkflowRunner(agent=agent, session_manager=session_manager)
                event_source = runner.run(
                    session_id=session_id,
                    user_message=message,
                    workflow=workflow_data,
                    turn_number=turn_number,
                    stream_cancel_event=stream_cancel_event,
                )
            else:
                agent_loop = AgentLoop(
                    agent=agent,
                    session_manager=session_manager,
                )
                event_source = agent_loop.run(
                    session_id=session_id,
                    user_message=message,
                    file_contents=file_contents,
                    stream_cancel_event=stream_cancel_event,
                )
            async for sse_event in event_source:
                # If client disconnected, signal cancellation but let generator finish naturally
                # (loop.py will handle aborted event, save partial response, and yield [DONE])
                if await request.is_disconnected():
                    stream_cancel_event.set()
                yield sse_event
            # Stream finished: deliver the final answer to Telegram if requested.
            # Read the final assistant message from the DB (single source of truth)
            # instead of accumulating raw chunk events, which can include
            # intermediate tool-calling content (ghost responses).
            if telegram_chat_id:
                try:
                    from backend.telegram.instance import telegram_bot

                    if stream_cancel_event.is_set():
                        # The client aborted the stream: notify Telegram with the
                        # same message the frontend shows, instead of the partial
                        # response that was persisted to the DB.

                        await telegram_bot.send_message(
                            int(telegram_chat_id), "*Transmisión cancelada.*"
                        )
                    else:
                        final_text = _get_last_assistant_text(session_id, turn_number)

                        if final_text:
                            await telegram_bot.send_message(int(telegram_chat_id), final_text)
                        else:
                            # The agent finished without producing output (e.g. it
                            # failed silently). Notify Telegram so the user knows,
                            # even if they are not looking at the frontend.
                            await telegram_bot.send_message(
                                int(telegram_chat_id),
                                "La solicitud no pudo completarse. Revisá la aplicación para más detalles.",
                            )
                except Exception as exc:
                    log_error(str(exc), source="backend/routes/chat.py:telegram_reply")
                    logger.warning("Failed to send final answer to Telegram: %s", exc)
        except Exception as exc:
            log_error(str(exc), source="backend/routes/chat.py")
            logger.exception("[DEBUG_TIEMPO_SSE] Error in agent loop stream: %s", exc)
            # Yield a terminal error event so the client sees something
            yield f"data: {json.dumps({'type': 'chunk', 'content': 'En este momento no se puede ejecutar la solicitud. Por favor, intentá más tarde.'})}\n\n"
            yield "data: [DONE]\n\n"
            # Notify Telegram so the user knows even if they are not watching
            # the frontend.
            if telegram_chat_id:
                try:
                    from backend.telegram.instance import telegram_bot
                    await telegram_bot.send_message(
                        int(telegram_chat_id),
                        "La solicitud no pudo completarse. Revisá la aplicación para más detalles.",
                    )
                except Exception as exc2:
                    log_error(str(exc2), source="backend/routes/chat.py:telegram_error_notify")
                    logger.warning("Failed to send Telegram error notification: %s", exc2)
        finally:
            _t_fin = _time.time()
            # # logger.info("[DEBUG_TIEMPO_SSE] event_stream() finished — t=%.3f, total=%.3f", _t_fin, _t_fin - _t0)
            reset_error_context(error_ctx_token)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
