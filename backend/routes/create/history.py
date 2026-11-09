"""History of the creators: the conversations each creator lists in its sidebar.

Endpoints:
- ``GET /api/create/history?kind=tool``: conversations of one kind of creator, newest first.
- ``GET /api/create/history/{creator_id}``: one conversation, rebuilt the way the page showed it.
- ``DELETE /api/create/history/{creator_id}``: delete a conversation.
- ``GET /api/create/history/{creator_id}/attachments/{file_name}``: download a file attached to the conversation.
"""

from __future__ import annotations

from fastapi.responses import JSONResponse

from backend.agent.utils import creators
from backend.routes.create.common import router


@router.get("/history")
async def list_creator_history(kind: str, limit: int = 50) -> JSONResponse:
    """List the conversations of one kind of creator, newest first.

    Args:
        kind: ``agent``, ``skill``, ``tool`` or ``workflow``.
        limit: Maximum number of conversations (1..200).

    Returns:
        JSON response with the conversations, or 400 when the kind is unknown.
    """
    if kind not in creators.KINDS:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "Tipo de creador inválido."},
        )
    return JSONResponse(
        status_code=200,
        content={"status": "success", "conversations": creators.list_conversations(kind, max(1, min(limit, 200)))},
    )


@router.get("/history/{creator_id}")
async def get_creator_history(creator_id: str) -> JSONResponse:
    """Return one conversation, rebuilt the way the creator page showed it.

    Args:
        creator_id: Conversation id.

    Returns:
        JSON response with the conversation, or 404 when it does not exist.
    """
    conversation = creators.get_conversation(creator_id) if creators.is_valid_id(creator_id) else None
    if conversation is None:
        return JSONResponse(
            status_code=404, content={"status": "error", "message": "La conversación no existe."},
        )
    return JSONResponse(status_code=200, content={"status": "success", "conversation": conversation})


@router.delete("/history/{creator_id}")
async def delete_creator_history(creator_id: str) -> JSONResponse:
    """Delete a conversation with its LLM calls.

    Args:
        creator_id: Conversation id.

    Returns:
        JSON response with the result, or 404 when it does not exist.
    """
    if not creators.is_valid_id(creator_id) or not creators.delete_conversation(creator_id):
        return JSONResponse(
            status_code=404, content={"status": "error", "message": "La conversación no existe."},
        )
    return JSONResponse(status_code=200, content={"status": "success"})


@router.get("/history/{creator_id}/attachments/{file_name}")
async def download_creator_attachment(creator_id: str, file_name: str):
    """Download the binary of a file attached to a creator conversation.

    Attachments are stored with ``session_id = creator_id`` in the shared
    ``attachments`` table (no FK, creators have no row in ``sessions``).

    Args:
        creator_id: Creator conversation id.
        file_name: Original file name.

    Returns:
        The file bytes with a download header, or an error contract.
    """
    import logging
    import mimetypes

    from fastapi.responses import JSONResponse, Response

    from backend.agent.utils.contract import make_error_response, validate_response, zero_usage
    from backend.agent.utils.db import get_connection
    from backend.agent.utils.error_logger import log_error

    logger = logging.getLogger(__name__)
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT file_name, content FROM attachments WHERE session_id = ? AND file_name = ? ORDER BY id DESC LIMIT 1",
                (creator_id, file_name),
            ).fetchone()
        if row is None or row["content"] is None:
            return JSONResponse(
                status_code=404,
                content=validate_response(make_error_response(message="Archivo no encontrado.", usage=zero_usage())),
            )
        data = bytes(row["content"])
        name = (row["file_name"] or "archivo").replace('"', "").replace("\r", "").replace("\n", "")
        media, _ = mimetypes.guess_type(name)
        return Response(
            content=data,
            media_type=media or "application/octet-stream",
            headers={"Content-Disposition": f'inline; filename="{name}"'},
        )
    except Exception as exc:
        log_error(str(exc), source="create/history.py:download_creator_attachment")
        logger.exception("Error downloading creator attachment %s: %s", file_name, exc)
        return JSONResponse(
            status_code=500,
            content=validate_response(make_error_response(message="Error al descargar el archivo.", usage=zero_usage())),
        )
