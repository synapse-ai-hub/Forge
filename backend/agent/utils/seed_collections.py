"""Seed of the internal ``help`` collection.

The documentation is shipped already vectorized in ``backend/agent/seeds/help.json``
(one document per section, with its embedding), so loading it needs no API key
and no embedding call. It runs from ``synapseForge init`` / ``update`` and at
backend startup, and only fills the collection when it is empty: documents the
user later changes with the collection methods are never overwritten.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import chromadb

from backend.agent.utils.config_dir import get_knowledge_dir
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.rag_helpers import HELP_COLLECTION
from backend.agent.utils.vector_db import GeminiEmbeddingFunction, _DEFAULT_MODEL

logger = logging.getLogger(__name__)

_HELP_SEED = Path(__file__).resolve().parents[1] / "seeds" / "help.json"


def seed_help_collection() -> int:
    """Create the ``help`` collection from the shipped seed if it is empty.

    Mirrors ``VectorDB.get_or_create_collection`` (same metadata and
    embedding function class); the placeholder key is never used because the
    vectors are precomputed.

    Returns:
        Number of documents added (0 when the collection already has content
        or the seed is missing). Never raises.
    """
    try:
        if not _HELP_SEED.is_file():
            logger.warning("No se encontró el seed de help: %s", _HELP_SEED)
            return 0
        seed = json.loads(_HELP_SEED.read_text(encoding="utf-8"))

        knowledge_dir = get_knowledge_dir()
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(knowledge_dir))
        collection = client.get_or_create_collection(
            name=HELP_COLLECTION,
            embedding_function=GeminiEmbeddingFunction(api_key="seed-precomputed"),
            metadata={"embedding_model": _DEFAULT_MODEL, "hnsw:space": "cosine"},
        )
        if collection.count() > 0:
            return 0
        if seed.get("embedding_model") != _DEFAULT_MODEL:
            logger.warning(
                "El seed de help usa '%s' y el RAG usa '%s': no se carga.",
                seed.get("embedding_model"), _DEFAULT_MODEL,
            )
            return 0
        collection.add(
            ids=seed["ids"],
            documents=seed["documents"],
            metadatas=seed["metadatas"],
            embeddings=seed["embeddings"],
        )
        logger.info("Colección '%s' cargada desde el seed: %d secciones.", HELP_COLLECTION, len(seed["ids"]))
        return len(seed["ids"])
    except Exception as exc:
        log_error(str(exc), source="seed_collections.py:seed_help_collection")
        logger.warning("No se pudo cargar el seed de help: %s", exc)
        return 0
