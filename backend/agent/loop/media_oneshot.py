"""Media one-shot runner (TTS / image models).

Audio-only and image-only models cannot chat: each turn is a single
direct SDK call with only the user's text — no history, no tools, no
system prompt, no decision agent, no iterations. This module runs that
turn outside the agent loop and yields the same SSE event shapes the
frontend already handles (``audio``/``image``, ``usage``,
``session_title``, ``[DONE]``).
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)

_AUDIO_TAG_RE = re.compile(
    r"""<audio\b[^>]*src\s*=\s*["']data:([^;]+);base64,([^"']+)["']""",
    re.IGNORECASE,
)
_IMG_TAG_RE = re.compile(
    r"""<img\b[^>]*src\s*=\s*["']data:([^;]+);base64,([^"']+)["']""",
    re.IGNORECASE,
)


def _extract_media(output: str) -> tuple[str, str, bytes] | None:
    """Extract the first generated media object from completion output.

    Args:
        output: Completion ``data`` (may contain ``<audio>``/``<img>`` tags).

    Returns:
        Tuple ``(kind, mime, raw_bytes)`` or ``None`` when no media found.
    """
    try:
        m = _AUDIO_TAG_RE.search(output or "")
        if m:
            return "audio", m.group(1), base64.b64decode(m.group(2))
        m = _IMG_TAG_RE.search(output or "")
        if m:
            return "image", m.group(1), base64.b64decode(m.group(2))
    except Exception:
        return None
    return None


def _friendly_message(error_text: str, exc: BaseException | None = None) -> str:
    """Build a user-friendly Spanish message for a one-shot failure.

    The technical detail stays in the DB log (``message`` field); the
    chat only shows this text (as a ``chunk`` event, which the frontend
    renders — ``error`` events are ignored by the UI).

    Args:
        error_text: Raw error text from the exception or result.
        exc: Optional exception object for category classification.

    Returns:
        User-friendly message string (markdown-italic, no technicalities).
    """
    from backend.agent.utils.rate_limit_handler import classify_error_category

    lowered = (error_text or "").lower()
    if "bidi" in lowered or "live api" in lowered:
        return (
            "*Este modelo solo funciona con la API en vivo (Live API) "
            "y no está soportado en el chat. Elegí otro modelo desde "
            "la configuración.*"
        )
    try:
        category = classify_error_category(exc if exc is not None else error_text)
    except Exception:
        category = "fatal"
    if category == "rate_limit":
        return (
            "*Se alcanzó el límite de peticiones del proveedor. "
            "Probá de nuevo en unos minutos o cambiá a otro modelo "
            "desde la configuración.*"
        )
    if category == "too_large":
        return (
            "*La solicitud es demasiado grande para este modelo. "
            "Probá con un texto más corto o cambiá de modelo.*"
        )
    return (
        "*Ocurrió un error al procesar la solicitud. "
        "Probá de nuevo en unos momentos.*"
    )


async def run_media_oneshot(
    session_id: str,
    user_message: str,
    turn_number: int,
    agent: Any,
    session_manager: Any,
    stream_cancel_event: asyncio.Event | None = None,
) -> AsyncGenerator[str, None]:
    """Run one media turn (TTS/image one-shot) without the agent loop.

    Single direct SDK call with only the user's text. Persists the user
    and assistant rows, the turn title (fallback, media models cannot
    produce text titles) and multimodal embeddings of the pair.

    Args:
        session_id: Unique session identifier.
        user_message: User message text (only input sent to the model).
        turn_number: Turn number inside the session.
        agent: ``Agent`` instance (model resolution + LLM clients).
        session_manager: ``SessionManager`` for SQLite.
        stream_cancel_event: Optional cancellation event.

    Yields:
        SSE-formatted strings (``audio``/``image``, ``usage``,
        ``session_title``, ``[DONE]``).
    """
    from backend.agent.llm.outputs import is_media_only_turn
    from backend.agent.utils.contract import zero_usage
    from backend.agent.utils.error_logger import log_error
    from backend.agent.utils.model_catalog import get_reasoning_options

    def _sse(payload: dict[str, Any]) -> str:
        """Format a payload dict as an SSE line."""
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    model = getattr(agent, "_resolved_model", None)
    provider = getattr(agent, "provider", None)
    if isinstance(provider, str):
        provider = provider.strip() or None

    try:
        caps = get_reasoning_options((provider or "").strip(), model)
        _, kind = is_media_only_turn((caps or {}).get("output_modalities"))
    except Exception:
        kind = "media"
    if kind not in ("audio", "image"):
        kind = "media"

    # --- Save user message (clean: text only, no attachments, no history) ---
    # Idempotent: retried requests must not duplicate the user row.
    try:
        _user_exists = False
        try:
            _user_exists = bool(session_manager.user_turn_exists(session_id, turn_number))
        except Exception:
            _user_exists = False
        if not _user_exists:
            session_manager.save_message(
                session_id, "user",
                content=user_message,
                turn_number=turn_number,
            )
    except Exception as exc:
        logger.warning("No se pudo guardar el mensaje del usuario: %s", exc)

    # --- Title on first turn: fallback (media models output no text) ---
    title: str | None = None
    if turn_number == 1:
        title = (user_message or "").strip()[:80]
        if title:
            try:
                session_manager.update_session_title(session_id, title)
            except Exception as exc:
                logger.warning("No se pudo guardar el título: %s", exc)
            try:
                session_manager.save_message(
                    session_id, "title",
                    content=f"Título generado: {title}",
                    model=model,
                    provider=provider,
                    turn_number=turn_number,
                    step=0,
                    status="success", message="title",
                    usage=zero_usage(),
                )
            except Exception:
                pass

    if stream_cancel_event is not None and stream_cancel_event.is_set():
        yield _sse({"type": "chunk", "content": "*Transmisión cancelada.*"})
        yield "data: [DONE]\n\n"
        return

    # Same as the loop: the frontend uses it to tag messages and feedback.
    yield _sse({"type": "turn", "content": turn_number})

    # --- Single direct SDK call: only the user's text, no tools ---
    # Bounded by a timeout: a hung provider call must fail cleanly
    # (error row + error event) instead of hanging the turn forever.
    # Defaults mirror the loop's media steps (temperature 0.0, top_p 0.5).
    _t0 = time.time()
    try:
        result = await asyncio.wait_for(
            agent.llm_process(
                model,
                messages=[{"role": "user", "content": user_message}],
                temperature=0.0,
                top_p=0.5,
                max_tokens=8192,
                reasoning=False,
                provider=provider,
                output=kind if kind in ("audio", "image") else None,
            ),
            timeout=300,
        )
    except asyncio.TimeoutError:
        log_error(
            f"One-shot de medios agotó el timeout (300s): {model} "
            f"sesión {session_id} turno {turn_number}",
            source="media_oneshot.py:timeout",
        )
        friendly = (
            "*El proveedor tardó demasiado en responder. "
            "Probá de nuevo en unos momentos.*"
        )
        try:
            session_manager.save_message(
                session_id, "assistant", content=friendly,
                model=model, provider=provider,
                turn_number=turn_number, step=0,
                status="error", message="timeout",
                usage=zero_usage(),
            )
        except Exception:
            pass
        yield _sse({"type": "chunk", "content": friendly})
        yield "data: [DONE]\n\n"
        return
    except Exception as exc:
        log_error(str(exc), source="media_oneshot.py:llm_process")
        logger.exception("Error en one-shot de medios: %s", exc)
        friendly = _friendly_message(str(exc), exc)
        try:
            session_manager.save_message(
                session_id, "assistant", content=friendly,
                model=model, provider=provider,
                turn_number=turn_number, step=0,
                status="error", message=str(exc)[:500],
                usage=zero_usage(),
            )
        except Exception:
            pass
        yield _sse({"type": "chunk", "content": friendly})
        yield "data: [DONE]\n\n"
        return

    if not isinstance(result, dict) or result.get("status") == "error":
        err = ""
        try:
            err = str((result or {}).get("message") or "")
        except Exception:
            pass
        friendly = _friendly_message(err)
        try:
            session_manager.save_message(
                session_id, "assistant", content=friendly,
                model=model, provider=provider,
                turn_number=turn_number, step=0,
                status="error", message=err[:500],
                usage=zero_usage(),
            )
        except Exception:
            pass
        yield _sse({"type": "chunk", "content": friendly})
        yield "data: [DONE]\n\n"
        return

    output = result.get("data") or ""
    usage = result.get("usage") if isinstance(result.get("usage"), dict) else None

    found = _extract_media(output)
    if found is None:
        friendly = "*El modelo no devolvió audio ni imagen. Probá de nuevo.*"
        try:
            session_manager.save_message(
                session_id, "assistant", content=friendly,
                model=model, provider=provider,
                turn_number=turn_number, step=0,
                status="error", message="empty_media_response",
                usage=usage or zero_usage(),
            )
        except Exception:
            pass
        yield _sse({"type": "chunk", "content": friendly})
        yield "data: [DONE]\n\n"
        return

    media_kind, mime, raw = found
    b64 = base64.b64encode(bytes(raw)).decode("ascii")

    # --- Persist assistant message (same shape as the loop) ---
    try:
        session_manager.save_message(
            session_id, "assistant", content=output,
            model=model, provider=provider,
            turn_number=turn_number, step=0,
            status="success", message="media_oneshot",
            usage=usage or zero_usage(),
        )
    except Exception as exc:
        logger.warning("No se pudo guardar la respuesta: %s", exc)

    # --- Multimodal embeddings of the user/assistant pair (never breaks) ---
    try:
        from backend.agent.utils.rag_helpers import index_media_turn

        await asyncio.to_thread(
            index_media_turn,
            session_id, turn_number, user_message, output,
            [(bytes(raw), mime)],
        )
    except Exception as exc:
        logger.warning("No se pudo indexar el turno de medios: %s", exc)

    # --- Multimodal spend (same as the loop's media steps) ---
    try:
        from backend.agent.utils.spend_handler import record_multimodal_spend

        record_multimodal_spend(
            (provider or "").strip(), model, media_kind, 1.0
        )
    except Exception:
        pass

    if media_kind == "image":
        payload = {"b64": b64, "url": None, "mime": mime, "model": model}
    else:
        payload = {"b64": b64, "mime": mime, "model": model}
    yield _sse({"type": media_kind, "content": payload})
    if usage:
        try:
            usage = dict(usage)
            usage.setdefault("total_time", round(time.time() - _t0, 2))
        except Exception:
            pass
        yield _sse({"type": "usage", "content": usage})
    if title:
        yield _sse({"type": "session_title", "content": title})
    yield "data: [DONE]\n\n"
