"""History of the creators: the conversations each creator lists in its sidebar.

Endpoints:
- ``GET /api/create/history?kind=tool``: conversations of one kind of creator, newest first.
- ``GET /api/create/history/{creator_id}``: one conversation, rebuilt the way the page showed it.
- ``DELETE /api/create/history/{creator_id}``: delete a conversation.
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
