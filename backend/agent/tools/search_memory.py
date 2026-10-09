"""SearchMemoryMixin — native tool search_memory."""

import logging
import time

from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)


class SearchMemoryMixin:
    async def search_memory(self, query: str, limit: int = 5) -> dict:
            """Search the user's past conversations (long-term memory).

            Use it when the user asks about previous conversations or mentions
            information that is not in the current session.

            Queries the ``agent_conversations`` ChromaDB collection (indexed
            automatically at the end of every turn) and returns the most relevant
            fragments with their metadata (session, title, date, turn). The current
            session is always excluded from the results so it never searches
            itself.

            Args:
                query: Natural language query describing what to look for in past
                    conversations.
                limit: Maximum number of results to return (default 5).

            Returns:
                dict with ``{status, message, data, usage}``. ``data`` contains a
                list of results with ``document``, ``session_id``,
                ``session_title``, ``turn_number``, ``date`` and ``distance``.
            """
            try:
                from backend.agent.utils.vector_db import get_vector_db
                from backend.agent.utils.rag_helpers import MEMORY_COLLECTION

                if not query or not query.strip():
                    return make_error_response(
                        message="La consulta no puede estar vacía.",
                        usage=zero_usage(),
                    )

                # Shared instance (pre-loaded at app startup): the embedding model
                # and the Chroma client are loaded once and never killed.
                db = get_vector_db()

                try:
                    db.get_collection(MEMORY_COLLECTION)
                except ValueError:
                    return make_success_response(
                        message="Todavía no hay conversaciones indexadas.",
                        data=[],
                        usage=zero_usage(),
                    )

                # Exclude the current session so it never retrieves itself.
                current_session_id = getattr(self, "_current_session_id", None)
                where = (
                    {"session_id": {"$ne": current_session_id}}
                    if current_session_id
                    else None
                )

                _mem_t0 = time.time()
                results = db.query(
                    MEMORY_COLLECTION,
                    query,
                    n_results=max(1, int(limit)),
                    where=where,
                )
                _mem_duration = round(time.time() - _mem_t0, 2)
                prompt_tokens = db.embed_func.count_tokens([query])
                # Track the query-embedding call in SQLite. Never breaks the flow.
                try:
                    from backend.agent.utils.spend_handler import record_external_usage

                    record_external_usage(
                        "embedding", "google", db.embed_func.model_name, 1,
                        duration=_mem_duration,
                        prompt_tokens=prompt_tokens,
                    )
                except Exception:
                    pass
                usage = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": 0,
                    "total_tokens": prompt_tokens,
                    "total_time": _mem_duration,
                }

                documents = (results.get("documents") or [[]])[0]
                metadatas = (results.get("metadatas") or [[]])[0]
                distances = (results.get("distances") or [[]])[0]

                formatted: list[dict] = []
                for doc, meta, dist in zip(documents, metadatas, distances):
                    formatted.append({
                        "document": doc,
                        "session_id": (meta or {}).get("session_id", ""),
                        "session_title": (meta or {}).get("session_title", ""),
                        "turn_number": (meta or {}).get("turn_number"),
                        "date": (meta or {}).get("date", ""),
                        "distance": dist,
                    })

                if not formatted:
                    return make_success_response(
                        message="No se encontraron conversaciones relacionadas.",
                        data=[],
                        usage=usage,
                    )

                return make_success_response(
                    message=f"{len(formatted)} fragmento(s) encontrado(s) en conversaciones anteriores.",
                    data=formatted,
                    usage=usage,
                )
            except Exception as e:
                logger.exception("Error in search_memory: %s", e)
                log_error(str(e), source="tools.py:search_memory")
                return make_error_response(
                    message="Error buscando en conversaciones anteriores.",
                    usage=zero_usage(),
                )
