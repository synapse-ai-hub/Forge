"""Telegram Bot API transport: send messages and documents, download files, transcribe audio."""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}"


class TransportMixin:
    """Outbound and file I/O calls against the Bot API."""

    async def _send_bytes(
        self, chat_id: int, endpoint: str, field: str, filename: str, data: bytes, mime: str, caption: str = ""
    ) -> None:
        """Send in-memory bytes to a chat via the Bot API.

        Args:
            chat_id: Telegram chat id.
            endpoint: Bot API endpoint (e.g. ``"sendPhoto"``).
            field: Multipart field name.
            filename: File name for the upload.
            data: File bytes (from DB ``attachments.content``).
            mime: MIME type.
            caption: Optional caption.

        Raises:
            RuntimeError: If Telegram rejects the upload.
        """
        try:
            import io as _io

            url = _TELEGRAM_API.format(token=self.token) + f"/{endpoint}"
            buf = _io.BytesIO(bytes(data))
            resp = await self._client.post(
                url,
                data={"chat_id": chat_id, "caption": caption[:1024]},
                files={field: (filename, buf, mime)},
            )
            payload = resp.json()
            if not payload.get("ok"):
                raise RuntimeError(payload.get("description", f"{endpoint} failed"))
        except Exception as exc:
            logger.warning("Failed to send Telegram %s: %s", endpoint, exc)
            raise

    async def _send_document(self, chat_id: int, path: str) -> None:
        """Send a file to a chat as a Telegram document (legacy path wrapper).

        .. deprecated::
            Use ``send_photo_bytes``, ``send_audio_bytes`` or
            ``send_video_bytes`` with DB attachment content instead.
            This wrapper only rejects server filesystem paths.

        Args:
            chat_id: The Telegram chat id.
            path: Attachment file name (DB ``attachments.file_name``).

        Raises:
            RuntimeError: Always; filesystem paths are never sent.
        """
        try:
            from backend.agent.llm.outputs import load_output_bytes as _load

            # Legacy callers pass session-less paths; without session context
            # only in-memory sends are supported.
            raise RuntimeError("Use _send_bytes with DB attachment content.")
        except Exception as exc:
            logger.warning("Failed to send Telegram document: %s", exc)
            raise

    async def send_message(self, chat_id: int, text: str) -> None:
        """Send a text message to a chat (used for the final answer).

        Args:
            chat_id: Telegram chat id.
            text: Text to send.
        """
        if not text:
            return

        url = _TELEGRAM_API.format(token=self.token) + "/sendMessage"
        # Telegram rejects messages over 4096 chars: split preserving lines.
        max_len = 4096
        chunks: list[str] = []
        remaining = text
        while len(remaining) > max_len:
            cut = remaining.rfind("\n", 0, max_len)
            if cut <= 0:
                cut = max_len
            chunks.append(remaining[:cut])
            remaining = remaining[cut:].lstrip("\n")
        chunks.append(remaining)
        try:
            for chunk in chunks:
                if not chunk:
                    continue
                resp = await self._client.post(url, json={"chat_id": chat_id, "text": chunk})
                try:
                    payload = resp.json()
                    if not payload.get("ok"):
                        logger.warning("Telegram sendMessage rejected: %s", payload.get("description"))
                except Exception:
                    pass
            

        except Exception as exc:
            logger.warning("Failed to send Telegram message: %s", exc)

    async def send_photo_bytes(self, chat_id: int, filename: str, data: bytes, caption: str = "") -> None:
        """Send image bytes as a Telegram photo (DB-backed, no filesystem).

        Args:
            chat_id: Telegram chat id.
            filename: File name for the upload.
            data: Image bytes from DB ``attachments.content``.
            caption: Optional caption.

        Raises:
            RuntimeError: If Telegram rejects the upload.
        """
        await self._send_bytes(chat_id, "sendPhoto", "photo", filename, data, "image/png", caption)

    async def send_audio_bytes(self, chat_id: int, filename: str, data: bytes, caption: str = "") -> None:
        """Send audio bytes as a Telegram audio message (DB-backed).

        Args:
            chat_id: Telegram chat id.
            filename: File name for the upload.
            data: Audio bytes from DB ``attachments.content``.
            caption: Optional caption.

        Raises:
            RuntimeError: If Telegram rejects the upload.
        """
        await self._send_bytes(chat_id, "sendAudio", "audio", filename, data, "audio/mpeg", caption)

    async def send_video_bytes(self, chat_id: int, filename: str, data: bytes, caption: str = "") -> None:
        """Send video bytes as a Telegram video message (DB-backed).

        Args:
            chat_id: Telegram chat id.
            filename: File name for the upload.
            data: Video bytes from DB ``attachments.content``.
            caption: Optional caption.

        Raises:
            RuntimeError: If Telegram rejects the upload.
        """
        await self._send_bytes(chat_id, "sendVideo", "video", filename, data, "video/mp4", caption)

    async def _download_file(self, file_id: str) -> bytes:
        """Download a file the user sent to the bot.

        Args:
            file_id: Telegram file id.

        Returns:
            The bytes of the file.

        Raises:
            RuntimeError: If Telegram does not return the file path.
        """
        url = _TELEGRAM_API.format(token=self.token) + "/getFile"
        resp = await self._client.post(url, json={"file_id": file_id})
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError("getFile failed")
        file_path = data["result"]["file_path"]
        file_url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
        resp = await self._client.get(file_url)
        return resp.content

    async def _transcribe(self, content: bytes) -> str:
        """Transcribe audio bytes using Groq Whisper API (whisper-large-v3-turbo).

        Requires a Groq API key configured in the provider_api_keys table.

        Args:
            content: Bytes of the audio.

        Returns:
            The transcribed text.

        Raises:
            RuntimeError: If no key is configured or the transcription fails.
        """
        from backend.agent.utils.provider_keys import get_key

        api_key = get_key("GROQ")
        if not api_key:
            raise RuntimeError(
                "No hay API key de Groq configurada. "
                "Las notas de voz requieren una API key de Groq (free tier). "
                "Sin ella, Telegram funciona solo por texto y comandos."
            )

        # Detect format from magic bytes
        if content[:4] == b"OggS":
            media_type = "audio/ogg"
        elif content[:4] == b"RIFF":
            media_type = "audio/wav"
        elif content[:4] in (b"\xff\xfb", b"ID3"):
            media_type = "audio/mpeg"
        else:
            media_type = "audio/ogg"

        _whisper_t0 = time.time()
        resp = await self._client.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("audio.ogg", content, media_type)},
            data={"model": "whisper-large-v3-turbo", "language": "es"},
            timeout=30.0,
        )
        _whisper_duration = round(time.time() - _whisper_t0, 2)
        if resp.status_code != 200:
            raise RuntimeError(f"Groq Whisper API error: {resp.status_code} — {resp.text[:200]}")
        text = resp.json().get("text", "").strip()
        # Contemplate the transcription call. Failures are never recorded
        # and never break the transcription flow.
        try:
            from backend.agent.utils.spend_handler import record_external_usage

            record_external_usage(
                "transcription", "groq", "whisper-large-v3-turbo", 1,
                duration=_whisper_duration,
            )
        except Exception:
            pass
        return text
