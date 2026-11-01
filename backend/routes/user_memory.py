"""Router for user preferences (user_memory) endpoints.

Endpoints:
- ``GET /api/user-memory`` — List preferences.
- ``POST /api/user-memory`` — Add a preference.
- ``DELETE /api/user-memory/{doc_id}`` — Delete a preference.

The collection is internal (never listed as RAG) and holds one document
per preference. All responses follow the unified contract.
"""

from __future__ import annotations

import os
import sys

from fastapi import APIRouter
from pydantic import BaseModel, Field

_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.rag_helpers import USER_MEMORY_COLLECTION, add_user_memory, delete_user_memory

router = APIRouter(prefix="/user-memory", tags=["user-memory"])


class AddPreferenceRequest(BaseModel):
    """Request to add a preference."""

    text: str = Field(min_length=1, max_length=500)


@router.get("")
async def list_preferences() -> dict:
    """List all user preferences.

    Returns:
        Contract dict with ``data.preferences`` list of ``{id, text, metadata}``.
    """
    try:
        from backend.agent.utils.vector_db import get_vector_db

        db = get_vector_db()
        try:
            col = db.get_collection(USER_MEMORY_COLLECTION)
        except ValueError:
            return make_success_response(
                message="Sin preferencias.",
                data={"preferences": []},
                usage=zero_usage(),
            )
        stored = col.get()
        ids = stored.get("ids") or []
        documents = stored.get("documents") or []
        metadatas = stored.get("metadatas") or []
        preferences = []
        for idx, doc_id in enumerate(ids):
            text = documents[idx] if idx < len(documents) else ""
            meta = metadatas[idx] if idx < len(metadatas) else {}
            preferences.append({"id": doc_id, "text": text, "metadata": meta or {}})
        return make_success_response(
            message=f"{len(preferences)} preferencia(s).",
            data={"preferences": preferences},
            usage=zero_usage(),
        )
    except Exception as e:
        log_error(str(e), source="user_memory.py:list")
        return make_error_response(
            message="Error listando preferencias.",
            usage=zero_usage(),
        )


@router.post("")
async def add_preference(payload: AddPreferenceRequest) -> dict:
    """Add a user preference.

    Args:
        payload: Request with ``text``.

    Returns:
        Contract dict with the created preference.
    """
    try:
        return add_user_memory(payload.text, origin="ui")
    except Exception as e:
        log_error(str(e), source="user_memory.py:add")
        return make_error_response(
            message="Error guardando preferencia.",
            usage=zero_usage(),
        )


@router.delete("/{doc_id}")
async def remove_preference(doc_id: str) -> dict:
    """Delete a user preference by id.

    Args:
        doc_id: Document id.

    Returns:
        Contract dict.
    """
    try:
        return delete_user_memory(doc_id)
    except Exception as e:
        log_error(str(e), source="user_memory.py:delete")
        return make_error_response(
            message="Error eliminando preferencia.",
            usage=zero_usage(),
        )
