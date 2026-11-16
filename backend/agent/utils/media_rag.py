"""Media ingestion for the knowledge base (RAG).

Images, audio and video files are vectorized with the multimodal
``gemini-embedding-2`` model (text, image, audio and video share one
embedding space, so cross-modal search works) and stored in ChromaDB
like any other chunk.

Design notes (from the official Gemini embeddings documentation):

- Images: at most 6 per request (PNG/JPEG). One file = one chunk:
  character chunk/overlap does not apply to images.
- Audio: at most 180 seconds per request (MP3/WAV). Longer files are
  split into overlapping time segments, so time-based chunking DOES
  apply to audio.
- Video: at most 120 seconds per request (MP4/MOV, audio tracks are
  ignored by the model). Longer files are split into overlapping time
  segments; each segment is embedded from up to 6 evenly spaced frames
  (the per-request image cap), so time-based chunking DOES apply.

Only ``Pillow``, ``soundfile`` (+ ``numpy``) and ``cv2`` are used (all
already installed). MP3/M4A cannot be decoded locally (no ffmpeg), so
files in those formats are embedded from their raw bytes when they fit
the duration cap; longer ones fail with the API error surfaced in
Spanish by the upload route.
"""

from __future__ import annotations

import io
import logging
import os
import tempfile
import wave
from typing import Any

logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"})
SUPPORTED_AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".ogg", ".flac", ".m4a"})
SUPPORTED_VIDEO_EXTENSIONS = frozenset({".mp4", ".mov"})

SUPPORTED_MEDIA_EXTENSIONS = (
    SUPPORTED_IMAGE_EXTENSIONS | SUPPORTED_AUDIO_EXTENSIONS | SUPPORTED_VIDEO_EXTENSIONS
)

# Generation model used to transcribe/describe media at index time.
# Must accept text+image+audio+video input with text output.
MEDIA_DESCRIBE_MODEL = "gemini-3.5-flash-lite"

# Caps from the Gemini embeddings documentation (with a safety margin).
AUDIO_MAX_SECONDS = 170.0
VIDEO_MAX_SECONDS = 110.0

# Time-based chunking windows (overlap in seconds).
AUDIO_SEGMENT_SECONDS = 150.0
AUDIO_OVERLAP_SECONDS = 10.0
VIDEO_SEGMENT_SECONDS = 100.0
VIDEO_OVERLAP_SECONDS = 10.0

# The API accepts at most 6 images per embedding request.
VIDEO_FRAMES_PER_SEGMENT = 6

# Formats decodable locally (via soundfile) for splitting.
_DECODABLE_AUDIO = frozenset({".wav", ".ogg", ".flac"})

_MIME_BY_EXTENSION = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/png",
    ".gif": "image/png",
    ".bmp": "image/png",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
}


class MediaRagError(Exception):
    """Raised when a media file cannot be prepared for RAG indexing."""


def detect_media_kind(filename: str) -> str | None:
    """Classify a file as RAG media.

    Args:
        filename: Original file name.

    Returns:
        ``"image"``, ``"audio"``, ``"video"`` or ``None`` when the
        extension is not a supported media type.
    """
    ext = os.path.splitext(filename or "")[1].lower()
    if ext in SUPPORTED_IMAGE_EXTENSIONS:
        return "image"
    if ext in SUPPORTED_AUDIO_EXTENSIONS:
        return "audio"
    if ext in SUPPORTED_VIDEO_EXTENSIONS:
        return "video"
    return None


def media_mime(filename: str) -> str:
    """Return the MIME type for a supported media file.

    Args:
        filename: Original file name.

    Returns:
        MIME type string (``application/octet-stream`` as fallback).
    """
    ext = os.path.splitext(filename or "")[1].lower()
    return _MIME_BY_EXTENSION.get(ext, "application/octet-stream")


def normalize_image(filename: str, data: bytes) -> tuple[bytes, str]:
    """Normalize an image to embeddable PNG/JPEG bytes.

    Args:
        filename: Original file name (used for error messages).
        data: Raw file bytes.

    Returns:
        Tuple of ``(image_bytes, mime_type)`` ready for the embedding
        model (PNG, or JPEG when the source already is JPEG).

    Raises:
        MediaRagError: If Pillow is missing or the image cannot be read.
    """
    try:
        from PIL import Image
    except ImportError as exc:
        raise MediaRagError(
            "Imágenes no disponibles: falta la dependencia Pillow."
        ) from exc
    ext = os.path.splitext(filename or "")[1].lower()
    try:
        with Image.open(io.BytesIO(data)) as img:
            try:
                img.seek(0)
            except Exception:
                pass
            rgb = img.convert("RGB")
            buf = io.BytesIO()
            if ext in (".jpg", ".jpeg"):
                rgb.save(buf, format="JPEG")
                return buf.getvalue(), "image/jpeg"
            rgb.save(buf, format="PNG")
            return buf.getvalue(), "image/png"
    except MediaRagError:
        raise
    except Exception as exc:
        raise MediaRagError(f"No se pudo leer la imagen {filename}: {exc}") from exc


def probe_audio(filename: str, data: bytes) -> dict[str, Any]:
    """Probe an audio file without fully loading it when possible.

    Args:
        filename: Original file name.
        data: Raw file bytes.

    Returns:
        Dict with ``duration_s`` (float or ``None`` when it cannot be
        probed locally, e.g. MP3 without ffmpeg) and ``decodable``
        (whether the file can be split into segments locally).
    """
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in _DECODABLE_AUDIO:
        return {"duration_s": None, "decodable": False}
    try:
        import soundfile as sf

        with io.BytesIO(data) as bio:
            info = sf.info(bio)
            duration = float(info.frames) / float(info.samplerate or 1)
        return {"duration_s": duration, "decodable": True}
    except Exception as exc:
        logger.warning("No se pudo sondear el audio %s: %s", filename, exc)
        return {"duration_s": None, "decodable": False}


def split_audio_wav(
    data: bytes,
    segment_seconds: float = AUDIO_SEGMENT_SECONDS,
    overlap_seconds: float = AUDIO_OVERLAP_SECONDS,
) -> list[tuple[bytes, float, float]]:
    """Split decodable audio into overlapping WAV segments.

    Args:
        data: Raw audio bytes (WAV/OGG/FLAC).
        segment_seconds: Length of each segment in seconds.
        overlap_seconds: Overlap between consecutive segments.

    Returns:
        List of ``(wav_bytes, start_s, end_s)`` tuples.

    Raises:
        MediaRagError: If the audio cannot be decoded.
    """
    try:
        import soundfile as sf
    except ImportError as exc:
        raise MediaRagError(
            "Audio no disponible: falta la dependencia soundfile."
        ) from exc
    try:
        import numpy as np
    except ImportError as exc:
        raise MediaRagError(
            "Audio no disponible: falta la dependencia numpy."
        ) from exc
    try:
        with io.BytesIO(data) as bio:
            samples, rate = sf.read(bio, dtype="float32", always_2d=True)
    except Exception as exc:
        raise MediaRagError(f"No se pudo decodificar el audio: {exc}") from exc
    total_s = len(samples) / float(rate)
    step = max(segment_seconds - overlap_seconds, 1.0)
    segments: list[tuple[bytes, float, float]] = []
    start = 0.0
    while start < total_s:
        end = min(start + segment_seconds, total_s)
        s0 = int(start * rate)
        s1 = int(end * rate)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(samples.shape[1])
            wav.setsampwidth(2)
            wav.setframerate(rate)
            pcm = (samples[s0:s1, :] * 32767.0).clip(-32768, 32767).astype("<i2")
            wav.writeframes(np.ascontiguousarray(pcm).tobytes())
        segments.append((buf.getvalue(), round(start, 1), round(end, 1)))
        if end >= total_s:
            break
        start += step
    return segments


def probe_video(filename: str, data: bytes) -> dict[str, Any]:
    """Probe a video file (duration, fps, frame count).

    Args:
        filename: Original file name.
        data: Raw file bytes.

    Returns:
        Dict with ``duration_s`` (float or ``None``), ``fps`` and
        ``frames``. ``duration_s`` is ``None`` when OpenCV cannot open
        the file.

    Raises:
        MediaRagError: If OpenCV is missing.
    """
    try:
        import cv2
    except ImportError as exc:
        raise MediaRagError(
            "Video no disponible: falta la dependencia opencv (cv2)."
        ) from exc
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            suffix=os.path.splitext(filename or "")[1].lower(), delete=False
        ) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        cap = cv2.VideoCapture(tmp_path)
        try:
            if not cap.isOpened():
                return {"duration_s": None, "fps": 0.0, "frames": 0}
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            duration = (frames / fps) if fps > 0 and frames > 0 else None
            return {"duration_s": duration, "fps": fps, "frames": frames}
        finally:
            cap.release()
    finally:
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def extract_video_frames(
    data: bytes,
    suffix: str,
    start_s: float,
    end_s: float,
    max_frames: int = VIDEO_FRAMES_PER_SEGMENT,
) -> list[tuple[bytes, str]]:
    """Extract evenly spaced PNG frames from a video time range.

    Args:
        data: Raw video bytes.
        suffix: File suffix (e.g. ``".mp4"``) for the temp file.
        start_s: Range start in seconds.
        end_s: Range end in seconds.
        max_frames: Maximum frames to extract.

    Returns:
        List of ``(png_bytes, "image/png")`` tuples (possibly empty).

    Raises:
        MediaRagError: If OpenCV is missing or the video cannot be read.
    """
    try:
        import cv2
    except ImportError as exc:
        raise MediaRagError(
            "Video no disponible: falta la dependencia opencv (cv2)."
        ) from exc
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        cap = cv2.VideoCapture(tmp_path)
        try:
            if not cap.isOpened():
                raise MediaRagError("No se pudo abrir el video.")
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if fps <= 0 or total <= 0:
                raise MediaRagError("No se pudo leer la duración del video.")
            f0 = max(int(start_s * fps), 0)
            f1 = min(int(end_s * fps), total - 1)
            if f1 <= f0:
                f1 = min(f0 + 1, total - 1)
            count = min(max_frames, f1 - f0 + 1)
            step = max((f1 - f0) // max(count, 1), 1)
            frames: list[tuple[bytes, str]] = []
            idx = f0
            while idx <= f1 and len(frames) < max_frames:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ok, frame = cap.read()
                if not ok or frame is None:
                    idx += step
                    continue
                ok_enc, buf = cv2.imencode(".png", frame)
                if ok_enc:
                    frames.append((bytes(buf.tobytes()), "image/png"))
                idx += step
            return frames
        finally:
            cap.release()
    finally:
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def _mmss(seconds: float) -> str:
    """Format seconds as ``MM:SS``.

    Args:
        seconds: Seconds to format.

    Returns:
        ``MM:SS`` string.
    """
    total = max(int(round(seconds)), 0)
    return f"{total // 60:02d}:{total % 60:02d}"


def build_media_chunks(
    filename: str, data: bytes, kind: str
) -> list[dict[str, Any]]:
    """Split a media file into embeddable chunks.

    Images produce exactly one chunk (character chunk/overlap does not
    apply). Audio and video produce one chunk per time segment
    (overlapping windows, so time-based chunking applies).

    Args:
        filename: Original file name.
        data: Raw file bytes.
        kind: ``"image"``, ``"audio"`` or ``"video"``.

    Returns:
        List of chunk dicts with ``chunk_id``, ``chunk_number``,
        ``chunk_text`` (descriptive placeholder), ``byte_size``,
        ``media_kind``, ``media_parts`` (list of ``(bytes, mime)`` for
        the embedding model) and ``segment`` info. The placeholder text
        is what gets stored in Chroma; the vectors come from the media
        bytes.

    Raises:
        MediaRagError: If the file cannot be prepared.
    """
    import uuid

    if kind == "image":
        img_bytes, mime = normalize_image(filename, data)
        text = f"[imagen: {filename}]"
        return [
            {
                "chunk_id": str(uuid.uuid4()),
                "chunk_number": 0,
                "chunk_text": text,
                "byte_size": len(text.encode("utf-8")),
                "media_kind": "image",
                "media_parts": [(img_bytes, mime)],
                "segment": None,
            }
        ]

    if kind == "audio":
        probe = probe_audio(filename, data)
        duration = probe.get("duration_s")
        if duration is not None and duration <= AUDIO_MAX_SECONDS:
            parts = [(bytes(data), media_mime(filename))]
            text = f"[audio 00:00–{_mmss(duration)} de {filename}]"
            seg = {"start_s": 0.0, "end_s": round(duration, 1)}
        elif duration is not None and probe.get("decodable"):
            parts_list = split_audio_wav(bytes(data))
            chunks = []
            for i, (wav_bytes, s0, s1) in enumerate(parts_list):
                text = f"[audio {_mmss(s0)}–{_mmss(s1)} de {filename}]"
                chunks.append(
                    {
                        "chunk_id": str(uuid.uuid4()),
                        "chunk_number": i,
                        "chunk_text": text,
                        "byte_size": len(text.encode("utf-8")),
                        "media_kind": "audio",
                        "media_parts": [(wav_bytes, "audio/wav")],
                        "segment": {"start_s": s0, "end_s": s1},
                    }
                )
            return chunks
        elif duration is None and not probe.get("decodable"):
            # Not decodable locally (e.g. MP3 without ffmpeg): embed raw
            # bytes and let the API enforce its 180s cap.
            parts = [(bytes(data), media_mime(filename))]
            text = f"[audio de {filename}]"
            seg = None
        else:
            raise MediaRagError(
                f"El audio {filename} supera el máximo indexable "
                f"({AUDIO_MAX_SECONDS:.0f}s) y no se puede dividir en este "
                "formato. Convertilo a WAV."
            )
        return [
            {
                "chunk_id": str(uuid.uuid4()),
                "chunk_number": 0,
                "chunk_text": text,
                "byte_size": len(text.encode("utf-8")),
                "media_kind": "audio",
                "media_parts": parts,
                "segment": seg,
            }
        ]

    if kind == "video":
        probe = probe_video(filename, data)
        duration = probe.get("duration_s")
        suffix = os.path.splitext(filename or "")[1].lower() or ".mp4"
        if duration is not None and duration <= VIDEO_MAX_SECONDS:
            parts = [(bytes(data), media_mime(filename))]
            text = f"[video 00:00–{_mmss(duration)} de {filename}]"
            seg = {"start_s": 0.0, "end_s": round(duration, 1)}
            chunks_out = [
                {
                    "chunk_id": str(uuid.uuid4()),
                    "chunk_number": 0,
                    "chunk_text": text,
                    "byte_size": len(text.encode("utf-8")),
                    "media_kind": "video",
                    "media_parts": parts,
                    "segment": seg,
                }
            ]
            return chunks_out
        if duration is not None and duration > VIDEO_MAX_SECONDS:
            step = VIDEO_SEGMENT_SECONDS - VIDEO_OVERLAP_SECONDS
            chunks_out = []
            start = 0.0
            idx = 0
            while start < duration:
                end = min(start + VIDEO_SEGMENT_SECONDS, duration)
                frames = extract_video_frames(bytes(data), suffix, start, end)
                if not frames:
                    raise MediaRagError(
                        f"No se pudieron extraer cuadros del video {filename} "
                        f"en el tramo {_mmss(start)}–{_mmss(end)}."
                    )
                text = f"[video {_mmss(start)}–{_mmss(end)} de {filename}]"
                chunks_out.append(
                    {
                        "chunk_id": str(uuid.uuid4()),
                        "chunk_number": idx,
                        "chunk_text": text,
                        "byte_size": len(text.encode("utf-8")),
                        "media_kind": "video",
                        "media_parts": frames,
                        "segment": {"start_s": round(start, 1), "end_s": round(end, 1)},
                    }
                )
                idx += 1
                if end >= duration:
                    break
                start += step
            return chunks_out
        raise MediaRagError(
            f"No se pudo leer la duración del video {filename}."
        )

    raise MediaRagError(f"Tipo de medio no soportado: {kind}.")


def build_content_prompt(kind: str) -> str:
    """Build the transcription/description prompt for a media chunk.

    Args:
        kind: ``"image"``, ``"audio"`` or ``"video"``.

    Returns:
        Prompt string in Spanish for the generation model.
    """
    if kind == "audio":
        return (
            "Transcribí este audio de forma literal y completa, en su idioma "
            "original. Devolvé solo la transcripción, sin comentarios."
        )
    if kind == "video":
        return (
            "Describí en detalle lo que se ve y lo que se escucha en este "
            "fragmento de video: escena, personas, objetos, acciones, texto "
            "visible y audio relevante. Devolvé solo la descripción."
        )
    return (
        "Describí en detalle lo que se ve en esta imagen: escena, personas, "
        "objetos, texto visible y cualquier elemento relevante. "
        "Devolvé solo la descripción."
    )


def content_document(placeholder: str, content: str | None) -> str:
    """Combine the placeholder header with the real media content.

    Args:
        placeholder: Short header (e.g. ``[audio 00:00-00:30 de x.wav]``).
        content: Transcription or description (None/empty = keep header).

    Returns:
        Full document text to store in Chroma.
    """
    if content and content.strip():
        return f"{placeholder}\n{content.strip()}"
    return placeholder
