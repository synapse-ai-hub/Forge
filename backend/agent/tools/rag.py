"""RagMixin — native tool rag."""

import logging
import time

from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage

logger = logging.getLogger(__name__)


class RagMixin:
    """Native tool ``rag``: query a knowledge base (RAG) collection."""
    async def rag(self, collection: str, query: str) -> dict:
            """Query a knowledge base (RAG) collection.

            Finds the chunks most similar to the query inside the given
            collection and returns the results with their metadata. The agent can
            only query the collections allowed in its frontmatter
            (``permission.rag``), just like ``task`` restricts sub-agents.

            Args:
                collection: Name of the collection to query.
                query: Natural language query.

            Returns:
                dict with ``{status, message, data, usage}``. ``data`` contains
                the search results (ids, documents, metadatas, distances).
            """
            try:
                from backend.agent.utils.vector_db import get_vector_db

                if not query or not query.strip():
                    return make_error_response(
                        message="La consulta no puede estar vacía.",
                        usage=zero_usage(),
                    )

                # Shared instance (pre-loaded at app startup): the embedding model
                # and the Chroma client are loaded once and never killed.
                db = get_vector_db()

                try:
                    db.get_collection(collection)
                except ValueError:
                    return make_error_response(
                        message=f"La colección '{collection}' no existe.",
                        usage=zero_usage(),
                    )

                _rag_t0 = time.time()
                results = db.query(collection, query, n_results=5)
                _rag_duration = round(time.time() - _rag_t0, 2)
                # Never send raw HTML to the LLM: documents are already
                # chunked (500 chars), metadata keeps only source/url info.
                try:
                    clean_metas: list[dict] = []
                    for meta in (results.get("metadatas") or [[]])[0] or []:
                        if not isinstance(meta, dict):
                            clean_metas.append({})
                            continue
                        clean_metas.append({k: v for k, v in meta.items() if k != "html"})
                    if results.get("metadatas"):
                        results["metadatas"] = [clean_metas]
                except Exception:
                    pass
                prompt_tokens = db.embed_func.count_tokens([query])
                # Track the query-embedding call in SQLite. Never breaks the flow.
                try:
                    from backend.agent.utils.spend_handler import record_external_usage

                    record_external_usage(
                        "embedding", "google", db.embed_func.model_name, 1,
                        duration=_rag_duration,
                        prompt_tokens=prompt_tokens,
                    )
                except Exception:
                    pass
                usage = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": 0,
                    "total_tokens": prompt_tokens,
                    "total_time": _rag_duration,
                }
                return make_success_response(
                    message=f"Resultados de '{collection}'.",
                    data=results,
                    usage=usage,
                )
            except Exception as e:
                logger.exception("Error in rag: %s", e)
                return make_error_response(
                    message="Error consultando la colección.",
                    usage=zero_usage(),
                )
