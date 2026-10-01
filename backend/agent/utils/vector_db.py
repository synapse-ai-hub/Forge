"""Wrapper for the vector database (ChromaDB).

Abstracts ChromaDB operations behind a simple interface. If the engine is
switched later (e.g. pgvector), only this file needs to change.

The embedding model runs on Gemini Embedding 2 (``gemini-embedding-2``)
through the ``google-genai`` SDK, so no local model is downloaded or kept
in memory. The same function is used to index documents and to embed queries
(Chroma calls it in both paths). The Gemini API key is resolved from the
encrypted DB storage (``provider_keys``) — without it the VectorDB cannot be
instantiated and RAG stays disabled.

Typical usage::

    from backend.agent.utils.vector_db import VectorDB

    db = VectorDB()
    db.create_collection("manual-producto")
    db.add_documents("manual-producto", ids=["c1"], documents=["texto..."], metadatas=[{"source": "doc.pdf"}])
    results = db.query("manual-producto", "¿cómo se instala?")
"""

from __future__ import annotations

import logging


import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings

from backend.agent.utils import provider_keys
from backend.agent.utils.config_dir import get_knowledge_dir
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-embedding-2"
_BATCH_SIZE = 32  # texts per embeddings request


class GeminiEmbeddingFunction(EmbeddingFunction[Documents]):
    """Chroma embedding function backed by the Gemini Embedding 2 API.

    Sends texts in batches to ``client.models.embed_content`` using the
    ``google-genai`` SDK and returns the resulting vectors.

    Attributes:
        model_name: Gemini embedding model identifier.
        batch_size: Maximum number of texts sent per request.
    """

    def __init__(self, api_key: str, model_name: str = _DEFAULT_MODEL) -> None:
        """Initialize the embedding function.

        Args:
            api_key: Gemini API key (resolved from the encrypted DB).
            model_name: Gemini embedding model identifier.
        """
        from google import genai
        self.api_key = api_key
        self.model_name = model_name
        self.client = genai.Client(api_key=api_key)

    def __call__(self, input: Documents) -> Embeddings:
        """Embed a batch of documents.

        Args:
            input: List of texts to embed.

        Returns:
            A list of embedding vectors (one per input text).

        Raises:
            RuntimeError: If the Gemini API call fails.
        """
        vectors: list[list[float]] = []
        try:
            for start in range(0, len(input), _BATCH_SIZE):
                batch = list(input[start:start + _BATCH_SIZE])
                resp = self.client.models.embed_content(
                    model=self.model_name,
                    contents=batch,
                )
                embeddings = resp.embeddings or []
                if len(embeddings) != len(batch):
                    raise RuntimeError(
                        f"Gemini devolvió {len(embeddings)} embeddings para "
                        f"{len(batch)} textos."
                    )
                vectors.extend([e.values for e in embeddings])
        except Exception as e:
            logger.error("Error llamando a Gemini embeddings: %s", e)
            raise RuntimeError(f"No se pudieron generar los embeddings: {e}") from e
        return vectors

    def count_tokens(self, input: Documents) -> int:
        """Count tokens with the server-side tokenizer.

        Calls ``client.models.count_tokens`` so the count uses Google's
        own tokenizer for the embedding model. Never raises: returns 0
        when the call fails.

        Args:
            input: List of texts to count.

        Returns:
            Total token count (0 on failure).
        """
        try:
            if not input:
                return 0
            resp = self.client.models.count_tokens(
                model=self.model_name,
                contents=list(input),
            )
            return int(resp.total_tokens or 0)
        except Exception as e:
            logger.warning("No se pudieron contar tokens: %s", e)
            return 0


class VectorDB:
    """ChromaDB vector operations wrapper.

    Attributes:
        chroma_path: Absolute path to the persistent Chroma directory.
        embed_func: Embedding function (Gemini Embedding 2 API), created once at init.
        _client: ``chromadb.PersistentClient`` instance.
    """

    def __init__(self, collection_name: str | None = None) -> None:
        """Initialize the persistent ChromaDB client and the embedding function.

        Args:
            collection_name: If provided, creates/gets that collection and
                stores it as ``self.collection``.

        Raises:
            ValueError: If no Gemini API key is stored in the DB (RAG
                requires it to generate embeddings).
        """
        self.chroma_path = get_knowledge_dir()
        self.chroma_path.mkdir(parents=True, exist_ok=True)

        api_key = provider_keys.get_key("GOOGLE")
        if not api_key:
            raise ValueError(
                "No hay una API key de Gemini configurada. Cargala en "
                "Configuración → Providers: es necesaria para la fuente de "
                "conocimiento."
            )
        self.embed_func = GeminiEmbeddingFunction(api_key=api_key)

        self._client = chromadb.PersistentClient(path=str(self.chroma_path))

        self.collection = None
        if collection_name:
            self.collection = self._client.get_or_create_collection(
                name=collection_name,
                embedding_function=self.embed_func,
                metadata={"embedding_model": _DEFAULT_MODEL, "hnsw:space": "cosine"},
            )

        logger.info(
            "VectorDB listo en %s (modelo: %s)",
            self.chroma_path,
            _DEFAULT_MODEL,
        )

    # ── Collection management ────────────────────────────────────────────

    def create_collection(
        self,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> chromadb.Collection:
        """Create a new vector collection.

        Args:
            name: Unique collection name.
            metadata: Optional metadata (embedding_model, description, etc.).

        Returns:
            The created collection instance.

        Raises:
            ValueError: If the collection already exists.
        """
        meta = metadata or {}
        meta.setdefault("embedding_model", _DEFAULT_MODEL)
        meta.setdefault("hnsw:space", "cosine")

        try:
            col = self._client.create_collection(
                name=name,
                embedding_function=self.embed_func,
                metadata=meta,
            )
            logger.info("Colección '%s' creada.", name)
            return col
        except ValueError:
            logger.warning("Colección '%s' ya existe.", name)
            raise

    def get_collection(self, name: str) -> chromadb.Collection:
        """Get an existing collection.

        Args:
            name: Name of the collection.

        Returns:
            The collection.

        Raises:
            ValueError: If the collection does not exist.
        """
        return self._client.get_collection(
            name=name,
            embedding_function=self.embed_func,
        )

    def get_or_create_collection(
        self,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> chromadb.Collection:
        """Get or create a collection (idempotent).

        Args:
            name: Name of the collection.
            metadata: Metadata used only if the collection is created.

        Returns:
            The collection.
        """
        meta = metadata or {}
        meta.setdefault("embedding_model", _DEFAULT_MODEL)
        meta.setdefault("hnsw:space", "cosine")

        col = self._client.get_or_create_collection(
            name=name,
            embedding_function=self.embed_func,
            metadata=meta,
        )
        logger.info("Colección '%s' lista.", name)
        return col

    def list_collections(self) -> list[dict[str, Any]]:
        """List all available collections.

        Returns:
            List of dicts with ``name`` and ``metadata`` per collection.
        """
        collections = self._client.list_collections()
        return [
            {"name": c.name, "metadata": c.metadata}
            for c in collections
        ]

    def get_embedding_compatibility(self) -> list[dict[str, Any]]:
        """Classify every collection by embedding-model compatibility.

        A collection is **compatible** when its ``embedding_model`` metadata
        equals :data:`_DEFAULT_MODEL`. Collections created with an older
        local embedding model (or missing metadata) hold vectors that are
        incompatible with the current embedding function and must be
        reindexed before they can be searched reliably.

        Returns:
            List of dicts with ``name``, ``embedding_model``, ``compatible``
            and ``documents`` (chunk count, ``None`` when unreadable).
        """
        result: list[dict[str, Any]] = []
        for entry in self.list_collections():
            name = entry["name"]
            meta = entry.get("metadata") or {}
            model = meta.get("embedding_model")
            count: int | None = None
            try:
                count = self._client.get_collection(name=name).count()
            except Exception as e:
                logger.warning("No se pudo contar '%s': %s", name, e)
                log_error(str(e), source="vector_db.py:get_embedding_compatibility")
            result.append(
                {
                    "name": name,
                    "embedding_model": model,
                    "compatible": model == _DEFAULT_MODEL,
                    "documents": count,
                }
            )
        return result

    def delete_collection(self, name: str) -> None:
        """Delete a collection and all its data.

        Args:
            name: Name of the collection to delete.
        """
        try:
            self._client.delete_collection(name)
            logger.info("Colección '%s' eliminada.", name)
        except (ValueError, chromadb.errors.NotFoundError):
            logger.warning("Colección '%s' no existe.", name)

    def get_collection_info(self, name: str) -> dict[str, Any]:
        """Get detailed info of a collection.

        Args:
            name: Name of the collection.

        Returns:
            Dict with ``name``, ``metadata`` and ``count`` (docs count).
        """
        col = self.get_collection(name)
        count = col.count()
        return {
            "name": col.name,
            "metadata": col.metadata,
            "count": count,
        }

    # ── CRUD operations ─────────────────────────────────────────────────

    def add_documents(
        self,
        collection_name: str,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
        embeddings: list[list[float]] | None = None,
    ) -> None:
        """Add documents to a collection.

        Args:
            collection_name: Target collection.
            ids: List of unique IDs (strings).
            documents: List of texts to index.
            metadatas: Optional metadata per document.
            embeddings: Optional precomputed vectors. When provided, no
                embedding API call is made (used by the reindex flow, which
                embeds everything up front before touching the collection).
        """
        col = self.get_collection(collection_name)
        col.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        logger.info(
            "%d documento(s) agregados a '%s'.",
            len(ids),
            collection_name,
        )

    def update_documents(
        self,
        collection_name: str,
        ids: list[str],
        documents: list[str] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        """Update existing documents.

        Args:
            collection_name: Collection.
            ids: IDs to update.
            documents: New texts (None = keep).
            metadatas: New metadata (None = keep).
        """
        col = self.get_collection(collection_name)
        col.update(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )
        logger.info(
            "%d documento(s) actualizados en '%s'.",
            len(ids),
            collection_name,
        )

    def delete_documents(
        self,
        collection_name: str,
        ids: list[str],
    ) -> None:
        """Delete documents by ID.

        Args:
            collection_name: Collection.
            ids: IDs to delete.
        """
        col = self.get_collection(collection_name)
        col.delete(ids=ids)
        logger.info(
            "%d documento(s) eliminados de '%s'.",
            len(ids),
            collection_name,
        )

    def get_documents(
        self,
        collection_name: str,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> dict[str, Any]:
        """Get documents by ID or filter.

        Args:
            collection_name: Collection.
            ids: Optional list of IDs.
            where: Optional metadata filter.
            limit: Maximum results.
            offset: Offset.

        Returns:
            Dict with ``ids``, ``documents``, ``metadatas``.
        """
        col = self.get_collection(collection_name)
        return col.get(
            ids=ids,
            where=where,
            limit=limit,
            offset=offset,
        )

    # ── Search ──────────────────────────────────────────────────────────

    def query(
        self,
        collection_name: str,
        query_text: str,
        n_results: int = 10,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Find the most similar chunks to a text.

        Args:
            collection_name: Collection to search.
            query_text: Natural language query.
            n_results: Number of results to return (default 10).
            where: Optional metadata filter.

        Returns:
            Dict with ``ids``, ``documents``, ``metadatas``, ``distances``.
        """
        col = self.get_collection(collection_name)
        return col.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

    def query_by_embedding(
        self,
        collection_name: str,
        embedding: list[float],
        n_results: int = 10,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Search directly by an embedding vector.

        Args:
            collection_name: Collection.
            embedding: Precomputed vector.
            n_results: Number of results.
            where: Optional filter.

        Returns:
            Dict with ``ids``, ``documents``, ``metadatas``, ``distances``.
        """
        col = self.get_collection(collection_name)
        return col.query(
            query_embeddings=[embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )


_db_singleton: VectorDB | None = None


def get_vector_db() -> VectorDB:
    """Return the process-wide shared VectorDB instance.

    The embedding function (Gemini Embedding 2 API) is created once and shared by
    every consumer (RAG routes, the ``rag`` tool and the AgentInfo listing).
    It is never killed, so repeated RAG calls reuse the same client. Raises
    ``ValueError`` if no Gemini API key is configured — callers should
    surface that message to the user.

    Returns:
        The shared VectorDB instance.
    """
    global _db_singleton
    if _db_singleton is None:
        _db_singleton = VectorDB()
    return _db_singleton
