"""Context files endpoints for the agent loop.

Provides endpoints to upload, list, and delete context files.
Context files are stored in SQLite and their content is injected
into the system prompt for both the main agent and sub-agents.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, UploadFile

# ---------------------------------------------------------------------------
# Ensure the project root is in sys.path so absolute imports (backend.*)
# resolve correctly regardless of how the file is invoked.
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.utils.contract import (
    make_error_response,
    make_success_response,
    validate_response,
    zero_usage,
)
from backend.routes.file_text_extractor import (
    ExtractionResult,
    extract_text_from_bytes,
)
from backend.utils.db import db_transaction, get_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/context-files", tags=["context-files"])


@router.post("")
async def upload_context_file(
    file: UploadFile = File(...),
):
    """Upload a context file, extract its text, and store it in SQLite.

    The endpoint receives an uploaded file, extracts its text content
    using ``extract_text_from_bytes``, and stores it in the ``context_files``
    table.

    Args:
        file: The uploaded file object.

    Returns:
        A contract response with ``data`` containing ``id`` and ``filename``.
    """
    try:
        filename = file.filename or "sin_nombre"
        content_bytes = await file.read()

        # Validate size (50 MB limit)
        max_bytes = 50 * 1024 * 1024
        if len(content_bytes) > max_bytes:
            return make_error_response(
                message=f"{filename} excede el tamaño máximo de 50 MB.",
            )

        result: ExtractionResult = extract_text_from_bytes(filename, content_bytes)
        if not result.success:
            detail = result.error_detail or f"No se pudo procesar {filename}."
            return make_error_response(message=detail)

        text = (result.text or "").strip()
        if not text:
            return make_error_response(
                message=f"No se encontró texto legible en {filename}.",
            )

        now = datetime.now().isoformat()
        with db_transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO context_files (filename, content, created_at) VALUES (?, ?, ?)",
                (filename, text, now),
            )
            file_id = cursor.lastrowid

        return validate_response(
            make_success_response(
                message="Archivo subido exitosamente",
                data={"id": file_id, "filename": filename},
                usage=zero_usage(),
            )
        )
    except Exception as exc:
        logger.exception("Error subiendo archivo de contexto")
        return make_error_response(message=str(exc))


@router.get("")
async def list_context_files():
    """List all uploaded context files.

    Returns basic info (id, filename, created_at) without the full content
    to keep the response lightweight.

    Returns:
        A contract response with ``data`` containing a ``files`` array.
    """
    try:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, filename, created_at FROM context_files ORDER BY created_at DESC"
            ).fetchall()

        files = [
            {
                "id": row["id"],
                "filename": row["filename"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

        return validate_response(
            make_success_response(
                message="Archivos listados",
                data={"files": files},
                usage=zero_usage(),
            )
        )
    except Exception as exc:
        logger.exception("Error listando archivos de contexto")
        return make_error_response(message=str(exc))


@router.delete("/{file_id}")
async def delete_context_file(file_id: int):
    """Delete a context file from SQLite.

    Args:
        file_id: The ID of the file to delete.

    Returns:
        A contract response confirming deletion.
    """
    try:
        with db_transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM context_files WHERE id = ?", (file_id,)
            )
            deleted = cursor.rowcount

        if deleted == 0:
            return make_error_response(
                message=f"Archivo con id {file_id} no encontrado.",
            )

        return validate_response(
            make_success_response(
                message="Archivo eliminado",
                data={"id": file_id},
                usage=zero_usage(),
            )
        )
    except Exception as exc:
        logger.exception("Error eliminando archivo de contexto")
        return make_error_response(message=str(exc))
