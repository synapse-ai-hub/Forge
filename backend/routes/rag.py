"""Router for the knowledge base (RAG) endpoints.

Endpoints:
- ``POST /api/rag/collections`` — Create a collection.
- ``GET /api/rag/collections`` — List collections.
- ``GET /api/rag/collections/embedding-compatibility`` — Classify collections by embedding-model compatibility.
- ``POST /api/rag/collections/{name}/reindex`` — Reindex a collection with the current embedding model.
- ``DELETE /api/rag/collections/{name}`` — Delete a collection.
- ``POST /api/rag/collections/{name}/files`` — Upload files (extract text, chunk and store).
- ``POST /api/rag/collections/{name}/urls`` — Add a web page (fetch, chunk, store and keep URL+HTML in metadata).

All responses follow the unified contract (``contract.py``).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from typing import Any

import httpx
from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Ensure project root for absolute imports
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.utils.chunking import chunk_file_content
from backend.agent.utils.contract import (
    make_error_response,
    make_success_response,
    validate_response,
    zero_usage,
)
from backend.agent.utils.rag_helpers import (
    MAX_BYTES,
    MAX_FILES,
    fetch_url_content,
    reindex_collection,
    validar_nombre_coleccion,
)
from backend.agent.utils.vector_db import VectorDB, get_vector_db
from backend.routes.file_text_extractor import (
    ExtractionResult,
    extract_text_from_bytes,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["rag"])

# ── Request models ────────────────────────────────────────────────────────


class CreateCollectionRequest(BaseModel):
    """Request to create a collection."""

    name: str
    description: str | None = None


class AddUrlRequest(BaseModel):
    """Request to add a web page to a collection."""

    url: str


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.post("/collections")
async def create_collection(req: CreateCollectionRequest):
    """Create a new vector collection.

    Args:
        req: Body with ``name`` (required) and ``description`` (optional).

    Returns:
        Contract with the created collection data.
    """
    try:
        error = validar_nombre_coleccion(req.name)
        if error:
            return make_error_response(message=error)

        db = get_vector_db()
        metadata = {}
        if req.description:
            metadata["description"] = req.description

        db.create_collection(req.name, metadata=metadata)
        info = db.get_collection_info(req.name)
        return validate_response(
            make_success_response(
                message=f"Colección '{req.name}' creada.",
                data=info,
                usage=zero_usage(),
            )
        )
    except ValueError:
        return make_error_response(
            message=f"La colección '{req.name}' ya existe."
        )
    except Exception:
        logger.exception("Error creando colección")
        return make_error_response(message="No se pudo crear la colección.")


@router.get("/collections")
async def list_collections():
    """List all available collections.

    Returns:
        Contract with the list of collections (name, metadata, count).
        Excludes internal collections like agent_conversations.
    """
    try:
        from backend.agent.utils.rag_helpers import MEMORY_COLLECTION

        db = get_vector_db()
        collections = db.list_collections()
        result = []
        for c in collections:
            # Skip internal collections
            if c["name"] == MEMORY_COLLECTION:
                continue
            try:
                info = db.get_collection_info(c["name"])
                result.append(info)
            except Exception:
                result.append(c)
        return validate_response(
            make_success_response(
                message="Colecciones listadas.",
                data={"collections": result},
                usage=zero_usage(),
            )
        )
    except Exception:
        logger.exception("Error listando colecciones")
        return make_error_response(message="No se pudieron listar las colecciones.")


@router.get("/collections/embedding-compatibility")
async def get_embedding_compatibility():
    """Classify collections by embedding-model compatibility.

    Collections created with an older embedding model hold vectors
    incompatible with the current Gemini Embedding 2 function and must be
    reindexed (``POST /api/rag/collections/{name}/reindex``).

    Returns:
        Contract with the per-collection classification.
    """
    try:
        db = get_vector_db()
        return validate_response(
            make_success_response(
                message="Compatibilidad de embeddings obtenida.",
                data={"collections": db.get_embedding_compatibility()},
                usage=zero_usage(),
            )
        )
    except Exception:
        logger.exception("Error clasificando compatibilidad de embeddings")
        return make_error_response(
            message="No se pudo obtener la compatibilidad de embeddings."
        )


@router.post("/collections/{name}/reindex")
async def reindex_collection_endpoint(name: str):
    """Reindex a collection with the current embedding model.

    Reads every stored chunk, embeds everything up front (an embedding
    failure aborts before anything is deleted), recreates the collection
    and re-inserts the chunks. Vectors are regenerated from the texts,
    never converted.

    Args:
        name: Name of the collection to reindex.

    Returns:
        Contract with the reindex report.
    """
    try:
        error = validar_nombre_coleccion(name)
        if error:
            return make_error_response(message=error)

        db = get_vector_db()
        report = await asyncio.to_thread(reindex_collection, db, name)
        message = (
            f"Colección '{name}' reindexada con el modelo actual "
            f"({report['reindexed']}/{report['documents']} chunk(s))."
        )
        if report["failed_batches"]:
            message += " Algunos lotes fallaron: revisá los logs o volvé a subir las fuentes."
        return validate_response(
            make_success_response(
                message=message,
                data=report,
                usage=zero_usage(),
            )
        )
    except ValueError as exc:
        return make_error_response(message=str(exc))
    except Exception:
        logger.exception("Error reindexando colección")
        return make_error_response(message="No se pudo reindexar la colección.")


@router.delete("/collections/{name}")
async def delete_collection(name: str):
    """Delete a collection and all its data.

    Args:
        name: Name of the collection to delete.

    Returns:
        Contract confirming the deletion.
    """
    try:
        error = validar_nombre_coleccion(name)
        if error:
            return make_error_response(message=error)

        db = get_vector_db()
        try:
            db.get_collection(name)
        except ValueError:
            return make_error_response(
                message=f"La colección '{name}' no existe."
            )
        db.delete_collection(name)
        return validate_response(
            make_success_response(
                message=f"Colección '{name}' eliminada.",
                data={"name": name},
                usage=zero_usage(),
            )
        )
    except Exception:
        logger.exception("Error eliminando colección")
        return make_error_response(message="No se pudo eliminar la colección.")


@router.post("/collections/{name}/files")
async def upload_files(name: str, files: list[UploadFile] = File(...)):
    """Upload files to a collection: extract text, chunk and store.

    Args:
        name: Target collection name.
        files: List of files to process.

    Returns:
        Contract with the processing details per file.
    """
    try:
        error = validar_nombre_coleccion(name)
        if error:
            return make_error_response(message=error)

        if len(files) > MAX_FILES:
            return make_error_response(
                message=f"Máximo {MAX_FILES} archivos por request."
            )

        db = get_vector_db()
        try:
            db.get_collection(name)
        except ValueError:
            return make_error_response(
                message=f"La colección '{name}' no existe."
            )

        resultados = []
        errores = []

        for file in files:
            filename = file.filename or "sin_nombre"

            # Read in capped chunks so huge files are not fully materialized.
            content_bytes = b""
            too_large = False
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                content_bytes += chunk
                if len(content_bytes) > MAX_BYTES:
                    too_large = True
                    break

            if too_large:
                errores.append(
                    {"filename": filename, "error": "Excede el tamaño máximo de 50 MB."}
                )
                continue

            result: ExtractionResult = extract_text_from_bytes(filename, content_bytes)
            if not result.success:
                errores.append(
                    {"filename": filename, "error": result.error_detail or "No se pudo procesar."}
                )
                continue

            text = (result.text or "").strip()
            if not text:
                errores.append(
                    {"filename": filename, "error": "No se encontró texto legible."}
                )
                continue

            chunks = chunk_file_content(filename, text)
            if not chunks:
                errores.append(
                    {"filename": filename, "error": "No se generaron chunks."}
                )
                continue

            ids = [c["chunk_id"] for c in chunks]
            documents = [c["chunk_text"] for c in chunks]
            metadatas = [
                {
                    "source": "file",
                    "filename": filename,
                    "chunk_number": c["chunk_number"],
                    "byte_size": c["byte_size"],
                }
                for c in chunks
            ]

            _upload_t0 = time.time()
            db.add_documents(name, ids=ids, documents=documents, metadatas=metadatas)
            _upload_duration = round(time.time() - _upload_t0, 2)
            # Track the embedding-model call in SQLite (one row with the
            # embedded chunk count). Never breaks the upload flow.
            try:
                from backend.agent.utils.spend_handler import record_external_usage

                record_external_usage(
                    "embedding", "google", db.embed_func.model_name, len(documents),
                    duration=_upload_duration,
                    prompt_tokens=db.embed_func.count_tokens(documents),
                )
            except Exception:
                pass
            resultados.append(
                {"filename": filename, "chunks": len(chunks)}
            )

        return validate_response(
            make_success_response(
                message=f"{len(resultados)} archivo(s) procesado(s) en '{name}'.",
                data={"processed": resultados, "errors": errores},
                usage=zero_usage(),
            )
        )
    except Exception:
        logger.exception("Error subiendo archivos a colección")
        return make_error_response(message="No se pudieron subir los archivos.")


@router.post("/collections/{name}/urls")
async def add_url(name: str, req: AddUrlRequest):
    """Add a web page to a collection.

    Fetches the content, chunks it and stores it. The URL is stored in the
    metadata of every chunk and the raw HTML in the first chunk.

    Args:
        name: Target collection name.
        req: Body with ``url``.

    Returns:
        Contract with the details of the added page.
    """
    try:
        error = validar_nombre_coleccion(name)
        if error:
            return make_error_response(message=error)

        url = (req.url or "").strip()
        if not url:
            return make_error_response(message="La URL es obligatoria.")

        db = get_vector_db()
        try:
            db.get_collection(name)
        except ValueError:
            return make_error_response(
                message=f"La colección '{name}' no existe."
            )

        try:
            text, html = await fetch_url_content(url)
        except ValueError as exc:
            return make_error_response(message=str(exc))
        except httpx.HTTPError:
            logger.exception("Error fetcheando URL %s", url)
            return make_error_response(
                message="No se pudo obtener el contenido de la URL."
            )

        if not text.strip():
            return make_error_response(
                message="No se pudo extraer contenido de la URL."
            )

        chunks = chunk_file_content(url, text)
        if not chunks:
            return make_error_response(
                message="No se generaron chunks para la URL."
            )

        ids = [c["chunk_id"] for c in chunks]
        documents = [c["chunk_text"] for c in chunks]
        metadatas = []
        for i, c in enumerate(chunks):
            meta: dict[str, Any] = {
                "source": "url",
                "url": url,
                "chunk_number": c["chunk_number"],
                "byte_size": c["byte_size"],
            }
            # Store the raw HTML only in the first chunk to avoid duplicating
            # it N times and hitting Chroma metadata limits.
            if i == 0:
                meta["html"] = html
            metadatas.append(meta)

        _url_t0 = time.time()
        db.add_documents(name, ids=ids, documents=documents, metadatas=metadatas)
        _url_duration = round(time.time() - _url_t0, 2)
        # Track the embedding-model call in SQLite (one row with the
        # embedded chunk count). Never breaks the flow.
        try:
            from backend.agent.utils.spend_handler import record_external_usage

            record_external_usage(
                "embedding", "google", db.embed_func.model_name, len(documents),
                duration=_url_duration,
                prompt_tokens=db.embed_func.count_tokens(documents),
            )
        except Exception:
            pass

        return validate_response(
            make_success_response(
                message=f"Página web agregada a '{name}'.",
                data={"url": url, "chunks": len(chunks)},
                usage=zero_usage(),
            )
        )
    except Exception:
        logger.exception("Error agregando URL a colección")
        return make_error_response(message="No se pudo agregar la página web.")