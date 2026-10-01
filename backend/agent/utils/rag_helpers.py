"""RAG helpers — low-level logic for the knowledge base endpoints.

This module centralises the non-endpoint logic used by
``backend/routes/rag.py``: collection-name validation, file size limits and
the SSRF-protected URL fetching (DNS pinning, private-IP blocking, redirect
handling and response size caps).

It also hosts the long-term conversation memory helpers: indexing of completed
turns into the dedicated ``agent_conversations`` Chroma collection (one
document per turn = user message + final assistant answer, with session/date
metadata), fire-and-forget so an indexing failure can never break the chat
stream.

Keeping this logic in ``utils`` (instead of inline in the route) follows the
project convention of separating helpers from endpoints.

Imported by ``backend/routes/rag.py`` and ``backend/agent/loop.py``.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import re
import socket
import sys
import time
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import httpcore
import httpx

from backend.agent.utils.contract import (
    make_error_response,
    make_success_response,
    zero_usage,
)
from backend.agent.utils.error_logger import log_error

# ---------------------------------------------------------------------------
# Ensure the project root is in sys.path for absolute imports
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(_current_dir)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

logger = logging.getLogger(__name__)

# Per-file size limit (50 MB, same as context_files).
MAX_BYTES = 50 * 1024 * 1024
# Maximum files per request (avoids resource exhaustion).
MAX_FILES = 20
# Maximum redirects when fetching a URL.
MAX_REDIRECTS = 5
# Maximum response size when fetching a URL (avoids memory DoS).
MAX_RESPONSE_BYTES = 5 * 1024 * 1024

# ---------------------------------------------------------------------------
# Long-term conversation memory (feat/memoria-largo-plazo)
# ---------------------------------------------------------------------------

# Dedicated Chroma collection holding one document per conversation turn.
MEMORY_COLLECTION = "agent_conversations"

# Turns are usually short, so a turn is a single document. Only when the
# document exceeds this size is the existing chunking helper applied.
MAX_TURN_DOC_CHARS = 4000

# Chunk size used when a turn document must be split (chars).
TURN_CHUNK_SIZE_CHARS = 2000

# Strong references to fire-and-forget indexing tasks (prevents garbage
# collection of tasks still running after the loop returns).
_background_index_tasks: set[asyncio.Task] = set()

# Private / loopback / link-local / metadata networks blocked for SSRF.
_PRIVATE_NETS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


# ---------------------------------------------------------------------------
# DNS pinning transport (mitigates DNS rebinding / TOCTOU)
# ---------------------------------------------------------------------------


class _PinnedIPBackend(httpcore.AsyncNetworkBackend):
    """Network backend that pins TCP connections to pre-validated IPs.

    The host->IP map is shared and mutable so redirects to new hosts can be
    pinned as they are followed. TLS SNI still uses the original hostname
    because only the TCP connection target is overridden.
    """

    def __init__(
        self,
        pins: dict[str, str],
        backend: httpcore.AsyncNetworkBackend,
    ) -> None:
        """Initialize the pinned backend.

        Args:
            pins: Mutable mapping ``hostname -> ip`` used to override the
                connection target.
            backend: Underlying network backend used for the real connection.
        """
        self._pins = pins
        self._backend = backend

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> Any:
        """Connect to the pinned IP for ``host`` when available.

        Args:
            host: Hostname to connect to.
            port: Remote port.
            timeout: Connection timeout.
            local_address: Optional local bind address.
            socket_options: Optional socket options.

        Returns:
            The network stream from the underlying backend.
        """
        pinned = self._pins.get(host, host)
        return await self._backend.connect_tcp(
            pinned, port, timeout, local_address, socket_options
        )

    def connect_unix_socket(self, path: str, timeout: float | None = None, socket_options: Any = None) -> Any:
        """Connect to a Unix socket via the underlying backend.

        Args:
            path: Socket path.
            timeout: Connection timeout.
            socket_options: Optional socket options.

        Returns:
            The network stream from the underlying backend.
        """
        return self._backend.connect_unix_socket(path, timeout, socket_options)

    async def sleep(self, seconds: float) -> None:
        """Delegate sleep to the underlying backend.

        Args:
            seconds: Seconds to sleep.
        """
        return await self._backend.sleep(seconds)


class _PinnedIPTransport(httpx.AsyncHTTPTransport):
    """Async HTTP transport whose connections are pinned to validated IPs."""

    def __init__(self, pins: dict[str, str], **kwargs: Any) -> None:
        """Initialize the transport with a shared pin map.

        Args:
            pins: Mutable mapping ``hostname -> ip`` used to override the
                connection target.
            **kwargs: Extra arguments forwarded to ``AsyncHTTPTransport``.
        """
        super().__init__(**kwargs)
        self._pool._network_backend = _PinnedIPBackend(pins, self._pool._network_backend)


def validar_nombre_coleccion(name: str) -> str | None:
    """Validate a collection name.

    Args:
        name: Name to validate.

    Returns:
        An error message, or ``None`` if the name is valid.
    """
    if not name:
        return "El nombre de la colección es obligatorio."
    if " " in name:
        return "El nombre de la colección no debe contener espacios."
    if name != name.lower():
        return "El nombre de la colección debe estar todo en minúscula."
    if not re.match(r"^[a-z0-9-]+$", name):
        return "Solo se permiten minúsculas, números y guiones."
    if len(name) < 3:
        return "El nombre de la colección debe tener al menos 3 caracteres."
    if name.startswith(("-", ".")) or name.endswith(("-", ".")):
        return "El nombre de la colección no puede empezar ni terminar con guión o punto."
    return None


def _is_private_ip(ip_str: str) -> bool:
    """Return ``True`` if an IP is private/loopback/link-local/metadata.

    Args:
        ip_str: IP address (IPv4 or IPv6).

    Returns:
        ``True`` if the IP belongs to a blocked network.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    # Normalize IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1) to IPv4 to avoid
    # an SSRF bypass.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return any(ip in net for net in _PRIVATE_NETS)


def _validate_url(url: str) -> str:
    """Validate a URL scheme and hostname presence.

    Args:
        url: URL to validate.

    Returns:
        The normalized URL.

    Raises:
        ValueError: If the scheme is not http/https or the hostname is missing.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Solo se permiten URLs http/https.")
    if not parsed.hostname:
        raise ValueError("La URL es inválida.")
    return url


def _pin_host(url: str, pins: dict[str, str]) -> str:
    """Resolve a URL host, block private IPs and pin it in the map.

    Args:
        url: URL whose host must be resolved and pinned.
        pins: Mutable mapping ``hostname -> ip`` updated in place.

    Returns:
        The same URL.

    Raises:
        ValueError: If the host cannot be resolved or resolves to a private IP.
    """
    hostname = urlparse(url).hostname or ""
    infos = socket.getaddrinfo(hostname, None)
    public_ips: list[str] = []
    for info in infos:
        ip = info[4][0]
        if _is_private_ip(ip):
            raise ValueError("No se permiten URLs a direcciones internas.")
        public_ips.append(ip)
    if not public_ips:
        raise ValueError("No se pudo resolver el host de la URL.")
    pins[hostname] = public_ips[0]
    return url


async def fetch_url_content(url: str) -> tuple[str, str]:
    """Fetch a URL and return ``(text, html)`` with SSRF protection.

    Resolves and validates the initial URL and every redirect, blocking
    private addresses, and pins each connection to the validated IP to
    mitigate DNS rebinding.

    Args:
        url: URL to fetch.

    Returns:
        A tuple with the markdown text and the raw HTML.

    Raises:
        ValueError: If the URL is invalid, internal, too large or has too many
            redirects.
        httpx.HTTPError: If the fetch fails.
    """
    current = _validate_url(url)
    pins: dict[str, str] = {}
    transport = _PinnedIPTransport(pins)
    async with httpx.AsyncClient(
        timeout=30, follow_redirects=False, transport=transport
    ) as client:
        for _ in range(MAX_REDIRECTS):
            _pin_host(current, pins)
            resp = await client.get(
                current, headers={"User-Agent": "Mozilla/5.0"}
            )
            if resp.status_code in (301, 302, 303, 307, 308) and "location" in resp.headers:
                # Resolve the redirect (it may be relative) and re-validate.
                current = _validate_url(urljoin(current, str(resp.headers["location"])))
                continue
            resp.raise_for_status()
            # Read the response with a size limit to avoid memory DoS.
            content = b""
            async for chunk in resp.aiter_bytes():
                content += chunk
                if len(content) > MAX_RESPONSE_BYTES:
                    raise ValueError("La respuesta de la URL es demasiado grande.")
            html = content.decode("utf-8", errors="replace")
            break
        else:
            raise ValueError("Demasiadas redirecciones al fetchear la URL.")

    try:
        import html2text

        converter = html2text.HTML2Text()
        converter.body_width = 0
        text = converter.handle(html)
    except ImportError:
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()

    return text, html


# ---------------------------------------------------------------------------
# Reindexing of collections created with an incompatible embedding model
# ---------------------------------------------------------------------------

# Transient markers (case-insensitive) that justify an embedding retry.
_EMBED_TRANSIENT_MARKERS = (
    "429",
    "rate limit",
    "too many requests",
    "timeout",
    "timed out",
    "connection",
)


def _embed_with_retry(embed_func, texts: list[str], max_retries: int = 3) -> list[list[float]]:
    """Embed texts with a simple retry for transient (rate-limit) failures.

    Args:
        embed_func: Callable (Chroma embedding function) that maps texts to
            vectors.
        texts: Texts to embed.
        max_retries: Maximum retries after the first attempt fails with a
            transient error. Waits grow exponentially (2s, 4s, 8s).

    Returns:
        The embedding vectors (one per input text).

    Raises:
        RuntimeError: Propagated from ``embed_func`` when the failure is not
            transient or retries are exhausted.
    """
    import time as _time

    delay = 2.0
    for attempt in range(max_retries + 1):
        try:
            return embed_func(texts)
        except Exception as exc:
            message = str(exc).lower()
            transient = any(marker in message for marker in _EMBED_TRANSIENT_MARKERS)
            if not transient or attempt == max_retries:
                raise
            logger.warning(
                "Embedding fallo (intento %d/%d), reintentando en %.0fs: %s",
                attempt + 1,
                max_retries,
                delay,
                exc,
            )
            log_error(str(exc), source="rag_helpers.py:_embed_with_retry")
            _time.sleep(delay)
            delay *= 2
    raise RuntimeError("Unreachable: embedding retry loop exhausted.")


def reindex_collection(db, name: str) -> dict:
    """Reindex a collection with the current embedding model.

    Reads every stored chunk (documents + metadatas) from the existing
    collection — the chunk texts are the recoverable source — embeds them
    ALL up front (so an embedding failure aborts before anything is
    deleted), then recreates the collection and re-inserts everything.
    Vectors are never converted; they are regenerated from the texts.

    Args:
        db: Shared ``VectorDB`` instance (current embedding function).
        name: Name of the collection to reindex.

    Returns:
        Dict report: ``{"name", "reindexed", "documents", "failed_batches",
        "sanity_ok"}``.

    Raises:
        ValueError: If the collection does not exist or is already
            compatible with the current embedding model.
        RuntimeError: If the upfront embedding fails (the original
            collection is left untouched).
    """
    try:
        old = db.get_collection(name)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"No se pudo acceder a la colección '{name}'.") from exc

    meta = getattr(old, "metadata", None) or {}
    from backend.agent.utils.vector_db import _DEFAULT_MODEL

    if meta.get("embedding_model") == _DEFAULT_MODEL:
        raise ValueError(
            f"La colección '{name}' ya usa el modelo de embeddings actual."
        )

    # 1. Read every stored chunk (paginated via col.get offset/limit).
    all_ids: list[str] = []
    all_documents: list[str] = []
    all_metadatas: list[dict] = []
    batch_size = 256
    offset = 0
    while True:
        page = old.get(limit=batch_size, offset=offset)
        ids = page.get("ids") or []
        if not ids:
            break
        all_ids.extend(ids)
        all_documents.extend(page.get("documents") or [])
        all_metadatas.extend(page.get("metadatas") or [])
        if len(ids) < batch_size:
            break
        offset += batch_size

    if not all_documents:
        # Nothing to re-embed: just recreate with the current model metadata.
        db.delete_collection(name)
        db.create_collection(name, metadata=dict(meta))
        return {
            "name": name,
            "reindexed": 0,
            "documents": 0,
            "failed_batches": [],
            "sanity_ok": True,
        }

    # 2. Embed EVERYTHING up front. If this fails, the original collection
    #    is untouched (no data loss).
    logger.info(
        "Reindexando '%s': embebiendo %d chunk(s) con el modelo actual...",
        name,
        len(all_documents),
    )
    _embed_t0 = time.time()
    vectors = _embed_with_retry(db.embed_func, all_documents)
    _embed_duration = round(time.time() - _embed_t0, 2)
    # Track the embedding-model call in SQLite (one row with the embedded
    # chunk count). Never breaks the reindex flow.
    try:
        from backend.agent.utils.spend_handler import record_external_usage

        record_external_usage(
            "embedding", "google", db.embed_func.model_name, len(all_documents),
            duration=_embed_duration,
            prompt_tokens=db.embed_func.count_tokens(all_documents),
        )
    except Exception:
        pass

    # 3. Recreate the collection with the current embedding model.
    db.delete_collection(name)
    db.create_collection(name, metadata={"description": meta.get("description")})

    # 4. Re-insert in batches using the precomputed vectors (no further API
    #    calls, so this step cannot fail for rate-limit reasons).
    insert_batch = 128
    failed_batches: list[dict] = []
    for start in range(0, len(all_ids), insert_batch):
        end = start + insert_batch
        try:
            db.add_documents(
                name,
                ids=all_ids[start:end],
                documents=all_documents[start:end],
                metadatas=all_metadatas[start:end],
                embeddings=vectors[start:end],
            )
        except Exception as exc:
            logger.exception("Batch de reinsert falló en '%s'", name)
            log_error(str(exc), source=f"rag_helpers.py:reindex_collection({name})")
            failed_batches.append({"from": start, "to": min(end, len(all_ids))})

    # 5. Sanity query: retrieve one known document as top result.
    sanity_ok = False
    try:
        sample = all_documents[0][:500]
        _sanity_t0 = time.time()
        results = db.query(name, sample, n_results=1)
        _sanity_duration = round(time.time() - _sanity_t0, 2)
        # Track the query-embedding call in SQLite. Never breaks the flow.
        try:
            from backend.agent.utils.spend_handler import record_external_usage

            record_external_usage(
                "embedding", "google", db.embed_func.model_name, 1,
                duration=_sanity_duration,
                prompt_tokens=db.embed_func.count_tokens([sample]),
            )
        except Exception:
            pass
        sanity_ok = bool((results.get("ids") or [[]])[0])
    except Exception as exc:
        logger.warning("Query de sanidad falló para '%s': %s", name, exc)
        log_error(str(exc), source=f"rag_helpers.py:reindex_collection(sanity:{name})")

    return {
        "name": name,
        "reindexed": len(all_ids) - sum(b["to"] - b["from"] for b in failed_batches),
        "documents": len(all_ids),
        "failed_batches": failed_batches,
        "sanity_ok": sanity_ok,
    }


# ---------------------------------------------------------------------------
# Long-term conversation memory — indexing (pattern from ProspectingAgent)
# ---------------------------------------------------------------------------


def build_turn_document(user_message: str, assistant_message: str) -> str:
    """Build the indexable document for one conversation turn.

    Follows the ProspectingAgent pattern: a single document containing the
    user message and the final assistant answer.

    Args:
        user_message: The user message of the turn.
        assistant_message: The final assistant response of the turn.

    Returns:
        The document text.
    """
    return (
        f"**Usuario**:\n\n{(user_message or '').strip()}\n\n"
        f"**Asistente**:\n\n{(assistant_message or '').strip()}"
    )


def _turn_metadata(
    session_id: str,
    session_title: str,
    turn_number: int,
) -> dict[str, Any]:
    """Build the metadata dict stored with every indexed turn.

    Args:
        session_id: Identifier of the session the turn belongs to.
        session_title: Human-readable title of the session.
        turn_number: Turn number inside the session.

    Returns:
        Metadata dict with ``session_id``, ``session_title``, ``turn_number``,
        ``role``, ``created_at`` (ISO) and ``date`` (human-readable).
    """
    now = datetime.now()
    return {
        "session_id": session_id,
        "session_title": session_title or "",
        "turn_number": int(turn_number),
        "role": "turn",
        "created_at": now.isoformat(timespec="seconds"),
        "date": now.strftime("%d/%m/%Y %H:%M"),
    }


def _index_turn_sync(
    session_id: str,
    turn_number: int,
    user_message: str,
    assistant_message: str,
) -> dict:
    """Index one completed conversation turn into Chroma (blocking).

    Resolves the session title from SQLite, builds the turn document and
    stores it in the ``agent_conversations`` collection using the shared
        VectorDB (Gemini Embedding 2). If the document exceeds
    ``MAX_TURN_DOC_CHARS`` it is split with the existing chunking helper.

    Args:
        session_id: Session identifier.
        turn_number: Turn number inside the session.
        user_message: User message of the turn.
        assistant_message: Final assistant response of the turn.

    Returns:
        Contract response dict (``{status, message, data, usage}``).
    """
    try:
        if not (user_message or "").strip() and not (assistant_message or "").strip():
            return make_success_response(
                message="Turno vacío: nada que indexar.",
                data=None,
                usage=zero_usage(),
            )

        # Lazy imports avoid circular dependencies at module load time.
        from backend.instances import session_manager
        from backend.agent.utils.vector_db import get_vector_db

        session_title = session_manager.get_session_title(session_id)
        document = build_turn_document(user_message, assistant_message)
        metadata = _turn_metadata(session_id, session_title, turn_number)
        doc_id = f"{session_id}__turn_{turn_number}"

        db = get_vector_db()
        db.get_or_create_collection(MEMORY_COLLECTION)

        if len(document) <= MAX_TURN_DOC_CHARS:
            _mem_t0 = time.time()
            db.add_documents(
                MEMORY_COLLECTION,
                ids=[doc_id],
                documents=[document],
                metadatas=[metadata],
            )
            _mem_duration = round(time.time() - _mem_t0, 2)
            indexed = 1
            # Track the embedding-model call in SQLite. Never breaks the flow.
            try:
                from backend.agent.utils.spend_handler import record_external_usage

                record_external_usage(
                    "embedding", "google", db.embed_func.model_name, 1,
                    duration=_mem_duration,
                    prompt_tokens=db.embed_func.count_tokens([document]),
                )
            except Exception:
                pass
        else:
            from backend.agent.utils.chunking import chunk_file_content

            chunks = chunk_file_content(
                f"{doc_id}.md",
                document,
                chunk_size_chars=TURN_CHUNK_SIZE_CHARS,
            )
            ids = [f"{doc_id}_c{c['chunk_number']}" for c in chunks]
            documents = [c["chunk_text"] for c in chunks]
            metadatas = [dict(metadata, chunk=f"{i + 1}/{len(chunks)}") for i in range(len(chunks))]
            _mem_t0 = time.time()
            db.add_documents(
                MEMORY_COLLECTION,
                ids=ids,
                documents=documents,
                metadatas=metadatas,
            )
            _mem_duration = round(time.time() - _mem_t0, 2)
            indexed = len(chunks)
            # Track the embedding-model call in SQLite (one row with the
            # embedded chunk count). Never breaks the flow.
            try:
                from backend.agent.utils.spend_handler import record_external_usage

                record_external_usage(
                    "embedding", "google", db.embed_func.model_name, len(documents),
                    duration=_mem_duration,
                    prompt_tokens=db.embed_func.count_tokens(documents),
                )
            except Exception:
                pass

        return make_success_response(
            message=f"Turno {turn_number} indexado en '{MEMORY_COLLECTION}'.",
            data={"indexed_documents": indexed},
            usage=zero_usage(),
        )
    except Exception as e:
        log_error(str(e), source="rag_helpers.py:_index_turn_sync")
        logger.warning("Could not index turn %s#%s: %s", session_id, turn_number, e)
        return make_error_response(
            message=f"No se pudo indexar el turno: {e}",
            usage=zero_usage(),
        )


async def index_turn_async(
    session_id: str,
    turn_number: int,
    user_message: str,
    assistant_message: str,
) -> dict:
    """Index one completed turn without blocking the event loop.

    Runs the blocking Chroma/embedding work in a worker thread. Never
    raises: any failure is logged via ``log_error`` and returned as an
    error contract response.

    Args:
        session_id: Session identifier.
        turn_number: Turn number inside the session.
        user_message: User message of the turn.
        assistant_message: Final assistant response of the turn.

    Returns:
        Contract response dict (``{status, message, data, usage}``).
    """
    try:
        return await asyncio.to_thread(
            _index_turn_sync,
            session_id,
            turn_number,
            user_message,
            assistant_message,
        )
    except Exception as e:
        log_error(str(e), source="rag_helpers.py:index_turn_async")
        return make_error_response(
            message=f"Error indexando la conversación: {e}",
            usage=zero_usage(),
        )


def index_turn_fire_and_forget(
    session_id: str,
    turn_number: int,
    user_message: str,
    assistant_message: str,
) -> None:
    """Schedule background indexing of a completed turn (never raises).

    Called by the agent loop right after persisting the final assistant
    message. The task runs independently of the SSE stream: failures are
    only logged. A strong reference is kept so the task is not garbage
    collected mid-flight.

    Args:
        session_id: Session identifier.
        turn_number: Turn number inside the session.
        user_message: User message of the turn.
        assistant_message: Final assistant response of the turn.
    """
    try:
        task = asyncio.create_task(
            index_turn_async(session_id, turn_number, user_message, assistant_message)
        )
        _background_index_tasks.add(task)
        task.add_done_callback(_background_index_tasks.discard)
    except Exception as e:
        log_error(str(e), source="rag_helpers.py:index_turn_fire_and_forget")
