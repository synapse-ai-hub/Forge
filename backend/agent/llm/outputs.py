"""Multimodal output helpers — image, audio/TTS and video via provider SDKs.

This module centralizes non-chat generation calls. Chat (text/JSON)
stays in ``completion.py`` / ``streaming.py``. Image, speech and video
use dedicated SDK endpoints per provider family:

- OpenAI-compatible providers: ``client.images.generate``,
  ``client.audio.speech.create`` and ``client.videos``.
- Google Gemini: ``GenerateContentConfig`` with ``response_modalities``,
  ``image_config`` and ``speech_config``.
- Ollama (LOCAL): ``generate`` with ``width``/``height``/``steps`` for
  image-capable models (opportunistic).

All public functions use Google-style docstrings in English, typed
signatures and explicit error handling.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)

OUTPUT_MODALITIES: tuple[str, ...] = ("text", "json", "image", "audio", "video", "auto")
"""Valid output modality values persisted as ``param_output``."""

_DEFAULT_TTS_VOICE = "Aoede"
"""Default prebuilt voice for Gemini TTS when no voice is configured."""


def resolve_gemini_response_modalities(
    output_modalities: list[str] | tuple[str, ...] | None,
    stream_format: str | None = None,
) -> list[str] | None:
    """Derive Gemini ``response_modalities`` from the model catalog entry.

    Mapping (verified against ``google-genai`` SDK docs and live 400s):

    - ``["audio"]`` only (TTS/speech) → ``["AUDIO"]``. Requesting ``TEXT``
      on these models fails with ``400 INVALID_ARGUMENT``.
    - ``image`` present → ``["TEXT", "IMAGE"]`` (unless JSON requested,
      in which case ``None`` so ``response_mime_type`` rules).
    - ``audio`` + ``text`` → ``["TEXT", "AUDIO"]``.
    - text-only or unknown → ``None`` (SDK default ``TEXT``).

    Args:
        output_modalities: Raw ``modalities_output`` from the catalog.
        stream_format: Current format (``"json"`` suppresses modalities).

    Returns:
        A ``response_modalities`` list or ``None`` for SDK default.
    """
    try:
        mods = [str(m).lower() for m in (output_modalities or [])]
    except Exception:
        return None
    if not mods:
        return None
    if stream_format == "json":
        return None
    has_image = "image" in mods
    has_audio = "audio" in mods
    has_text = "text" in mods
    if has_audio and not has_text and not has_image:
        return ["AUDIO"]
    if has_image:
        return ["TEXT", "IMAGE"]
    if has_audio and has_text:
        return ["TEXT", "AUDIO"]
    return None


def gemini_needs_speech_config(
    output_modalities: list[str] | tuple[str, ...] | None,
) -> bool:
    """Check whether a Gemini model needs ``speech_config`` with a voice.

    Args:
        output_modalities: Raw ``modalities_output`` from the catalog.

    Returns:
        ``True`` for audio-output models (TTS/speech).
    """
    try:
        mods = [str(m).lower() for m in (output_modalities or [])]
    except Exception:
        return False
    return "audio" in mods


def build_gemini_speech_config(voice_name: str | None = None) -> Any:
    """Build a ``SpeechConfig`` with a prebuilt voice for Gemini TTS.

    Args:
        voice_name: Prebuilt voice name. When omitted, the persisted
            ``param_voice`` setting is used, falling back to
            ``_DEFAULT_TTS_VOICE``.

    Returns:
        A ``types.SpeechConfig`` instance.

    Raises:
        RuntimeError: If the ``google.genai`` package is unavailable.
    """
    try:
        from google.genai import types as _types
    except Exception as exc:
        raise RuntimeError(f"google-genai SDK not available: {exc}")
    resolved = (voice_name or "").strip()
    if not resolved:
        try:
            from backend.agent.session import SessionManager

            stored = SessionManager().get_config("param_voice")
            stored = (stored or "").strip()
            if stored.lower() not in ("", "null", "default"):
                resolved = stored
        except Exception:
            resolved = ""
    return _types.SpeechConfig(
        voice_config=_types.VoiceConfig(
            prebuilt_voice_config=_types.PrebuiltVoiceConfig(
                voice_name=resolved or _DEFAULT_TTS_VOICE
            )
        )
    )


def is_media_only_turn(output_modalities: list[str] | tuple[str, ...] | None) -> tuple[bool, str]:
    """Check whether a model turn is a media-only one-shot (no text output).

    TTS-only (``["audio"]``) and image-only (``["image"]``) models cannot
    chat: each turn is a single direct SDK call with only the user's text,
    outside the agent loop. Models that also output ``"text"`` stay in the
    loop (they are conversational).

    Args:
        output_modalities: Raw ``modalities_output`` from the catalog.

    Returns:
        Tuple ``(is_media_only, kind)`` where ``kind`` is ``"audio"``,
        ``"image"`` or ``"media"`` (mixed non-text outputs).
    """
    try:
        mods = [str(m or "").strip().lower() for m in (output_modalities or [])]
    except Exception:
        return False, ""
    mods = [m for m in mods if m]
    if not mods or "text" in mods:
        return False, ""
    # Video-only models have no one-shot path (video is generated via the
    # loop's generate_video step), so they stay out of the one-shot route.
    if "video" in mods and "audio" not in mods and "image" not in mods:
        return False, ""
    if all(m == "audio" for m in mods):
        return True, "audio"
    if all(m == "image" for m in mods):
        return True, "image"
    return True, "media"


def merge_audio_chunks(parts: list[tuple[str, str]]) -> tuple[str, str]:
    """Merge streamed TTS audio chunks into a single base64 payload.

    Gemini streams TTS audio as many small ``audio/l16`` chunks. The
    UI must show ONE player (batch), not one per chunk, so the
    backend concatenates the raw PCM bytes and returns a single
    event. The caller wraps the result with :func:`build_wav_data_url`
    (or embeds it) at persist time.

    Args:
        parts: List of ``(b64, mime)`` tuples in stream order.

    Returns:
        Tuple ``(merged_b64, mime)`` with concatenated PCM and the
        first chunk's mime type. Empty input returns ``("", "")``.
    """
    import base64 as _b64

    if not parts:
        return "", ""
    mime = parts[0][1] if len(parts[0]) > 1 else ""
    raw = b"".join(
        _b64.b64decode(p[0]) if isinstance(p[0], str) else bytes(p[0] or b"")
        for p in parts
        if p and p[0]
    )
    return _b64.b64encode(raw).decode("ascii"), mime


def build_wav_data_url(pcm: bytes, sample_rate: int = 24000) -> str:
    """Wrap headerless 16-bit mono PCM in a WAV container as a data URL.

    Gemini streaming TTS returns raw ``audio/l16`` chunks (no RIFF
    header), which browsers cannot play inside ``<audio>``. This
    helper prepends a minimal 44-byte WAV header so the persisted
    message plays back directly.

    Args:
        pcm: Raw little-endian signed 16-bit mono PCM samples.
        sample_rate: Sample rate in Hz (Gemini streams at 24000).

    Returns:
        HTML ``<audio>`` tag with an ``audio/wav`` base64 data URL.
    """
    import base64
    import struct

    data_len = len(pcm or b"")
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_len,
        b"WAVE",
        b"fmt ",
        16,
        1,  # PCM
        1,  # mono
        sample_rate,
        sample_rate * 2,  # byte rate
        2,  # block align
        16,  # bits per sample
        b"data",
        data_len,
    )
    b64 = base64.b64encode(header + (pcm or b"")).decode("ascii")
    return (
        '\n<audio controls src="data:audio/wav;base64,'
        + b64
        + '" style="width:100%;"></audio>\n'
    )

_OUTPUT_DIRNAME = "outputs"
"""Directory name (under the project store) for generated binary files."""


def resolve_output(
    frontmatter_output: str | None = None,
    override_output: str | None = None,
    response_format: str | None = None,
) -> str:
    """Resolve the effective output modality for the current turn.

    Precedence: explicit global override (persisted via
    ``POST /api/config/models/select``) → agent frontmatter
    (``parameters.output``) → legacy ``response_format`` (``json`` maps
    to ``json`` output) → ``"auto"`` free mode (the model decides per
    turn; for text-only models this behaves as ``"text"``).

    ``"auto"`` means free work: text for questions and tool calls,
    image/audio when the user requests it. Explicit ``"image"``,
    ``"audio"`` or ``"video"`` forces that modality every turn.

    Args:
        frontmatter_output: Output from the agent frontmatter, if any.
        override_output: Global override from ``config_kv`` (``param_output``).
        response_format: Legacy structured-output mode (``"json"``/``"text"``).

    Returns:
        One of ``"text"``, ``"json"``, ``"image"``, ``"audio"``, ``"video"``,
        ``"auto"``.
    """
    try:
        if override_output is not None:
            value = str(override_output).strip().lower()
            if value in OUTPUT_MODALITIES:
                return value
        if frontmatter_output is not None:
            value = str(frontmatter_output).strip().lower()
            if value in OUTPUT_MODALITIES:
                return value
        if response_format is not None and str(response_format).strip().lower() == "json":
            return "json"
        return "auto"
    except Exception as e:
        log_error(str(e), source="outputs.py:resolve_output")
        return "auto"


def get_output_storage_dir(session_id: str) -> Path:
    """Return the legacy storage directory (deprecated, DB is canonical).

    Generated binaries are persisted in the ``attachments`` table, not on
    disk. This helper is kept for backward compatibility only.

    Args:
        session_id: Session identifier.

    Returns:
        Legacy directory path (not created).
    """
    try:
        import re as _re

        safe_session = _re.sub(r"[^A-Za-z0-9_-]", "", str(session_id)) or "unknown"
        base = Path("store") / _OUTPUT_DIRNAME / safe_session
        return base
    except Exception as e:
        log_error(str(e), source="outputs.py:get_output_storage_dir")
        return Path("store") / _OUTPUT_DIRNAME / "unknown"


def save_output_bytes(
    data: bytes,
    session_id: str,
    turn_number: int,
    extension: str,
    prefix: str = "output",
) -> str:
    """Persist generated binary bytes in the ``attachments`` table (DB).

    The whole app persists files in DB (``attachments.content`` BLOB),
    never on disk. Returns the stored file name so callers can reference
    it; the bytes stay in DB for Telegram resend and history.

    Args:
        data: Raw file bytes to persist.
        session_id: Session identifier used as subdirectory.
        turn_number: Turn number used in the file name.
        extension: File extension without dot (e.g. ``"png"``, ``"mp3"``).
        prefix: File name prefix (default ``"output"``).

    Returns:
        Stored file name (e.g. ``"image-3.png"``). Empty string on failure.
    """
    try:
        import re as _re
        from datetime import datetime as _dt

        if data is not None and len(data) > 25 * 1024 * 1024:
            log_error("Output bytes exceed 25MB limit.", source="outputs.py:save_output_bytes")
            return ""
        allowed_ext = {"png", "jpg", "jpeg", "webp", "mp3", "wav", "opus", "pcm", "mp4", "bin"}
        safe_ext = "".join(c for c in str(extension).lower() if c.isalnum()) or "bin"
        if safe_ext not in allowed_ext:
            safe_ext = "bin"
        allowed_prefix = {"image", "audio", "video", "output"}
        safe_prefix = str(prefix).lower() if str(prefix).lower() in allowed_prefix else "output"
        filename = f"{safe_prefix}-{int(turn_number)}.{safe_ext}"
        try:
            from backend.agent.utils.db import db_transaction as _db_tx
            from backend.agent.utils.queries import load_query as _load_q

            now = _dt.now().isoformat()
            with _db_tx() as conn:
                conn.execute(
                    _load_q("attachments/insert.sql"),
                    (str(session_id), int(turn_number), filename, len(data), bytes(data), now),
                )
        except Exception as e:
            log_error(str(e), source="outputs.py:save_output_bytes(db)")
            return ""
        return filename
    except Exception as e:
        log_error(str(e), source="outputs.py:save_output_bytes")
        return ""


def load_output_bytes(session_id: str, turn_number: int, file_name: str) -> bytes:
    """Load generated binary bytes from the ``attachments`` table.

    Args:
        session_id: Session identifier.
        turn_number: Turn number.
        file_name: Stored file name.

    Returns:
        File bytes, or empty bytes when not found.
    """
    try:
        from backend.agent.utils.db import get_connection as _get_conn

        with _get_conn() as conn:
            row = conn.execute(
                "SELECT content FROM attachments WHERE session_id = ? AND turn_number = ? AND file_name = ? ORDER BY id DESC LIMIT 1",
                (str(session_id), int(turn_number), str(file_name)),
            ).fetchone()
        if row is None:
            return b""
        content = row["content"] if isinstance(row, dict) else row[0]
        return bytes(content) if content is not None else b""
    except Exception as e:
        log_error(str(e), source="outputs.py:load_output_bytes")
        return b""


async def generate_image_openai(
    client: Any,
    model: str,
    prompt: str,
    size: str | None = None,
    n: int = 1,
) -> dict[str, Any]:
    """Generate an image via an OpenAI-compatible ``images.generate`` endpoint.

    Args:
        client: Authenticated ``AsyncOpenAI`` client for the provider.
        model: Image model identifier.
        prompt: Text prompt describing the image.
        size: Optional image size (e.g. ``"1024x1024"``). ``None`` uses default.
        n: Number of images (default 1).

    Returns:
        Dict with ``status``, ``b64`` (base64 payload) or ``url``,
        ``mime`` and ``model``. Error dict on failure.
    """
    try:
        kwargs: dict[str, Any] = {"model": model, "prompt": prompt, "n": n}
        if size:
            kwargs["size"] = size
        try:
            kwargs["response_format"] = "b64_json"
            response = await client.images.generate(**kwargs)
        except Exception:
            kwargs.pop("response_format", None)
            response = await client.images.generate(**kwargs)
        data = getattr(response, "data", None) or []
        if not data:
            return {"status": "error", "message": "Empty image response."}
        first = data[0]
        b64 = getattr(first, "b64_json", None)
        url = getattr(first, "url", None)
        if b64:
            return {"status": "success", "b64": b64, "mime": "image/png", "model": model}
        if url:
            return {"status": "success", "url": url, "mime": "image/png", "model": model}
        revised = getattr(first, "revised_prompt", None)
        return {"status": "error", "message": f"Unsupported image payload (revised={bool(revised)})."}
    except Exception as e:
        log_error(str(e), source="outputs.py:generate_image_openai")
        return {"status": "error", "message": str(e)}


async def generate_image_gemini(
    google_client: Any,
    model: str,
    prompt: str,
) -> dict[str, Any]:
    """Generate an image via the Gemini SDK with ``IMAGE`` modality.

    Args:
        google_client: Authenticated ``genai.Client`` instance.
        model: Gemini image model identifier.
        prompt: Text prompt describing the image.

    Returns:
        Dict with ``status``, ``b64``, ``mime`` and ``model`` on success,
        error dict otherwise.
    """
    try:
        from google.genai import types

        config = types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"])
        response = await google_client.aio.models.generate_content(
            model=model,
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
            config=config,
        )
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            for part in (getattr(content, "parts", None) or []):
                inline = getattr(part, "inline_data", None)
                if inline is not None and getattr(inline, "data", None):
                    raw = inline.data
                    if isinstance(raw, str):
                        b64 = raw
                    else:
                        b64 = base64.b64encode(bytes(raw)).decode("ascii")
                    mime = getattr(inline, "mime_type", None) or "image/png"
                    return {"status": "success", "b64": b64, "mime": mime, "model": model}
        return {"status": "error", "message": "No image data in Gemini response."}
    except Exception as e:
        log_error(str(e), source="outputs.py:generate_image_gemini")
        return {"status": "error", "message": str(e)}


async def generate_image_ollama(
    ollama_client: Any,
    model: str,
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    steps: int = 20,
) -> dict[str, Any]:
    """Generate an image via Ollama ``generate`` (opportunistic).

    Only image-capable Ollama models support ``width``/``height``/``steps``.
    Other models raise and the caller must fall back to chat.

    Args:
        ollama_client: Authenticated ``AsyncClient`` for Ollama.
        model: Local model identifier.
        prompt: Text prompt describing the image.
        width: Output width in pixels.
        height: Output height in pixels.
        steps: Diffusion steps.

    Returns:
        Dict with ``status``, ``b64``, ``mime`` and ``model`` on success,
        error dict otherwise.
    """
    try:
        if ollama_client is None:
            return {"status": "error", "message": "Ollama client not available."}
        response = await ollama_client.generate(
            model=model,
            prompt=prompt,
            width=int(width),
            height=int(height),
            steps=int(steps),
        )
        image = getattr(response, "image", None)
        if image:
            return {"status": "success", "b64": image, "mime": "image/png", "model": model}
        return {"status": "error", "message": "Model does not support image generation."}
    except Exception as e:
        log_error(str(e), source="outputs.py:generate_image_ollama")
        return {"status": "error", "message": str(e)}


async def generate_speech_openai(
    client: Any,
    model: str,
    text: str,
    voice: str = "alloy",
    response_format: str = "mp3",
) -> dict[str, Any]:
    """Generate speech audio via an OpenAI-compatible ``audio.speech`` endpoint.

    Args:
        client: Authenticated ``AsyncOpenAI`` client for the provider.
        model: Speech model identifier (e.g. ``"tts-1"``).
        text: Input text to synthesize.
        voice: Voice identifier (default ``"alloy"``).
        response_format: Audio format (``"mp3"``, ``"opus"``, ``"wav"``, ``"pcm"``).

    Returns:
        Dict with ``status``, ``audio`` (raw bytes), ``mime`` and ``model``.
    """
    try:
        response = await client.audio.speech.create(
            model=model,
            voice=voice or "alloy",
            input=text,
            response_format=response_format,
        )
        data: bytes = b""
        try:
            if hasattr(response, "aread"):
                data = await response.aread()
            elif hasattr(response, "read"):
                read_result = response.read()
                if hasattr(read_result, "__await__"):
                    data = await read_result
                else:
                    data = read_result
            elif isinstance(response, (bytes, bytearray)):
                data = bytes(response)
        except Exception as e:
            log_error(str(e), source="outputs.py:generate_speech_openai(read)")
            data = b""
        if not data:
            return {"status": "error", "message": "Empty audio response."}
        mime_map = {"mp3": "audio/mpeg", "opus": "audio/opus", "wav": "audio/wav", "pcm": "audio/pcm", "aac": "audio/aac", "flac": "audio/flac"}
        return {"status": "success", "audio": data, "mime": mime_map.get(response_format, "audio/mpeg"), "model": model}
    except Exception as e:
        log_error(str(e), source="outputs.py:generate_speech_openai")
        return {"status": "error", "message": str(e)}


async def generate_speech_gemini(
    google_client: Any,
    model: str,
    text: str,
    voice: str | None = None,
) -> dict[str, Any]:
    """Generate speech audio via the Gemini SDK with ``AUDIO`` modality.

    Args:
        google_client: Authenticated ``genai.Client`` instance.
        model: Gemini TTS model identifier.
        text: Input text to synthesize.
        voice: Optional voice name. ``None`` uses the model default.

    Returns:
        Dict with ``status``, ``b64``, ``mime`` and ``model`` on success.
    """
    try:
        from google.genai import types

        if voice:
            speech_config = types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            )
        else:
            speech_config = types.SpeechConfig()
        config = types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=speech_config)
        response = await google_client.aio.models.generate_content(
            model=model,
            contents=[{"role": "user", "parts": [{"text": text}]}],
            config=config,
        )
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            for part in (getattr(content, "parts", None) or []):
                inline = getattr(part, "inline_data", None)
                if inline is not None and getattr(inline, "data", None):
                    raw = inline.data
                    if isinstance(raw, str):
                        b64 = raw
                    else:
                        b64 = base64.b64encode(bytes(raw)).decode("ascii")
                    mime = getattr(inline, "mime_type", None) or "audio/mpeg"
                    return {"status": "success", "b64": b64, "mime": mime, "model": model}
        return {"status": "error", "message": "No audio data in Gemini response."}
    except Exception as e:
        log_error(str(e), source="outputs.py:generate_speech_gemini")
        return {"status": "error", "message": str(e)}


async def generate_speech(
    agent: Any,
    provider: str | None,
    model: str,
    text: str,
    voice: str | None = "alloy",
    response_format: str = "mp3",
) -> dict[str, Any]:
    """Dispatch speech synthesis to the provider-specific SDK call.

    Args:
        agent: Agent instance holding the provider clients.
        provider: Provider identifier.
        model: Speech model identifier.
        text: Input text to synthesize.
        voice: Voice identifier for OpenAI-compatible providers (also
            used as the Gemini prebuilt voice when set). ``None`` keeps
            the provider/model default.
        response_format: Audio container for OpenAI-compatible
            providers (``"mp3"``, ``"opus"``, ``"wav"``, ``"pcm"``).

    Returns:
        Dict with ``status`` plus audio payload (``audio`` bytes or ``b64``).
    """
    try:
        provider_norm = (provider or "").strip()
        if provider_norm == "LOCAL":
            return {"status": "error", "message": "Ollama (LOCAL) does not support speech synthesis."}
        if provider_norm.lower() == "google":
            if getattr(agent, "google_client", None) is None:
                return {"status": "error", "message": "Google client not available: missing API key."}
            return await generate_speech_gemini(agent.google_client, model, text, voice=voice or None)
        client = None
        try:
            getter = getattr(agent, "get_openai_client", None)
            if callable(getter):
                client = getter(provider_norm)
            if client is None:
                clients = getattr(agent, "_openai_clients", {}) or {}
                client = clients.get(provider_norm) or clients.get(provider_norm.lower())
        except Exception:
            client = None
        if client is None:
            return {"status": "error", "message": f"No client for provider '{provider}': missing API key."}
        return await generate_speech_openai(client, model, text, voice=voice, response_format=response_format)
    except Exception as e:
        log_error(str(e), source="outputs.py:generate_speech")
        return {"status": "error", "message": str(e)}


def build_audio_html(file_path: str, mime: str = "audio/mpeg") -> str:
    """Build an HTML snippet referencing a generated audio file.

    Args:
        file_path: Absolute or relative file path of the audio.
        mime: MIME type of the audio.

    Returns:
        HTML string with an ``<audio controls>`` tag.
    """
    try:
        import html as _html

        raw = str(file_path).replace('"', "")
        try:
            rel = str(Path(raw).resolve().relative_to(Path.cwd()))
        except Exception:
            rel = raw.replace("\\", "/")
        rel = rel.replace("\\", "/")
        safe_rel = _html.escape(rel, quote=True)
        return f'<audio controls src="{safe_rel}" style="width:100%;"></audio>'
    except Exception as e:
        log_error(str(e), source="outputs.py:build_audio_html")
        return ""


async def generate_video_openai(
    client: Any,
    model: str,
    prompt: str,
    seconds: int = 4,
    size: str = "720x1280",
) -> dict[str, Any]:
    """Generate a video via an OpenAI-compatible ``videos`` endpoint (late phase).

    Uses ``create_and_poll`` when available, falling back to ``create``.
    Only providers exposing ``/videos`` (OpenAI Sora, xAI imagine-video)
    support this path.

    Args:
        client: Authenticated ``AsyncOpenAI`` client for the provider.
        model: Video model identifier.
        prompt: Text prompt describing the video.
        seconds: Clip duration in seconds (4, 8 or 12 for Sora).
        size: Output resolution (e.g. ``"720x1280"``).

    Returns:
        Dict with ``status`` plus ``url``/``video_id`` on success.
    """
    try:
        videos = getattr(client, "videos", None)
        if videos is None:
            return {"status": "error", "message": "Provider does not expose a videos endpoint."}
        result = None
        try:
            if hasattr(videos, "create_and_poll"):
                result = await videos.create_and_poll(model=model, prompt=prompt, seconds=seconds, size=size)
            else:
                result = await videos.create(model=model, prompt=prompt, seconds=seconds, size=size)
        except Exception as e:
            return {"status": "error", "message": str(e)}
        url = getattr(result, "url", None)
        video_id = getattr(result, "id", None)
        if url:
            return {"status": "success", "url": url, "video_id": video_id, "mime": "video/mp4", "model": model}
        return {"status": "error", "message": "Video job accepted but no URL yet (polling required)."}
    except Exception as e:
        log_error(str(e), source="outputs.py:generate_video_openai")
        return {"status": "error", "message": str(e)}


async def generate_video(
    agent: Any,
    provider: str | None,
    model: str,
    prompt: str,
) -> dict[str, Any]:
    """Dispatch video generation (late phase, limited providers).

    Args:
        agent: Agent instance holding the provider clients.
        provider: Provider identifier.
        model: Video model identifier.
        prompt: Text prompt describing the video.

    Returns:
        Dict with ``status`` plus video payload or explanatory error.
    """
    try:
        provider_norm = (provider or "").strip()
        if provider_norm == "LOCAL":
            return {"status": "error", "message": "Ollama (LOCAL) does not support video generation."}
        if provider_norm.lower() == "google":
            return {"status": "error", "message": "Video is not supported for Google in phase 1 (use Vertex/Veo separately)."}
        client = None
        try:
            getter = getattr(agent, "get_openai_client", None)
            if callable(getter):
                client = getter(provider_norm)
            if client is None:
                clients = getattr(agent, "_openai_clients", {}) or {}
                client = clients.get(provider_norm) or clients.get(provider_norm.lower())
        except Exception:
            client = None
        if client is None:
            return {"status": "error", "message": f"No client for provider '{provider}': missing API key."}
        return await generate_video_openai(client, model, prompt)
    except Exception as e:
        log_error(str(e), source="outputs.py:generate_video")
        return {"status": "error", "message": str(e)}


def build_video_html(url_or_path: str) -> str:
    """Build an HTML snippet referencing a generated video.

    Only ``http``/``https`` URLs or relative ``store/outputs`` paths are
    allowed; anything else returns an empty string to prevent XSS via
    ``javascript:`` or ``data:text/html`` schemes.

    Args:
        url_or_path: Public URL or relative store path of the video.

    Returns:
        HTML string with a ``<video controls>`` tag.
    """
    try:
        import html as _html

        raw = str(url_or_path).replace('"', "").replace("\\", "/").strip()
        lowered = raw.lower()
        if lowered.startswith("http://") or lowered.startswith("https://"):
            safe = _html.escape(raw, quote=True)
        elif lowered.startswith("store/outputs/"):
            safe = _html.escape(raw, quote=True)
        else:
            return ""
        return f'<video controls src="{safe}" style="max-width:100%;border-radius:8px;"></video>'
    except Exception as e:
        log_error(str(e), source="outputs.py:build_video_html")
        return ""


async def generate_image(
    agent: Any,
    provider: str | None,
    model: str,
    prompt: str,
) -> dict[str, Any]:
    """Dispatch image generation to the provider-specific SDK call.

    Args:
        agent: Agent instance holding the provider clients.
        provider: Provider identifier (``"LOCAL"``, ``"google"`` or any
            OpenAI-compatible curated provider).
        model: Model identifier.
        prompt: Text prompt describing the image.

    Returns:
        Dict with ``status`` plus ``b64``/``url``/``mime`` on success.
    """
    try:
        provider_norm = (provider or "").strip()
        if provider_norm == "LOCAL":
            return await generate_image_ollama(agent.ollama_client, model, prompt)
        if provider_norm.lower() == "google":
            if getattr(agent, "google_client", None) is None:
                return {"status": "error", "message": "Google client not available: missing API key."}
            return await generate_image_gemini(agent.google_client, model, prompt)
        client = None
        try:
            getter = getattr(agent, "get_openai_client", None)
            if callable(getter):
                client = getter(provider_norm)
            if client is None:
                clients = getattr(agent, "_openai_clients", {}) or {}
                client = clients.get(provider_norm) or clients.get(provider_norm.lower())
        except Exception:
            client = None
        if client is None:
            return {"status": "error", "message": f"No client for provider '{provider}': missing API key."}
        return await generate_image_openai(client, model, prompt)
    except Exception as e:
        log_error(str(e), source="outputs.py:generate_image")
        return {"status": "error", "message": str(e)}


def build_image_markdown(file_path: str, mime: str = "image/png") -> str:
    """Build a markdown snippet referencing a generated image file.

    Uses an HTML ``<img>`` tag with a relative store path so the
    frontend can serve it via HTTP (no ``file://`` absolute paths).
    All attributes are HTML-escaped to prevent stored XSS.

    Args:
        file_path: Absolute or relative file path of the image.
        mime: MIME type of the image.

    Returns:
        Markdown string with an HTML ``<img>`` tag (diagrams in HTML
        per user instruction).
    """
    try:
        import html as _html

        raw = str(file_path).replace('"', "")
        try:
            rel = str(Path(raw).resolve().relative_to(Path.cwd()))
        except Exception:
            rel = raw.replace("\\", "/")
        rel = rel.replace("\\", "/")
        safe_rel = _html.escape(rel, quote=True)
        safe_mime = _html.escape(str(mime), quote=True)
        return f'<img src="{safe_rel}" alt="Generated image ({safe_mime})" style="max-width:100%;border-radius:8px;" />'
    except Exception as e:
        log_error(str(e), source="outputs.py:build_image_markdown")
        return ""
