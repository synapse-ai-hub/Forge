"""Incoming attachments (documents, photos, audio) sent to the bot."""

from __future__ import annotations

import logging

from backend.event_bus import event_bus

logger = logging.getLogger(__name__)

class AttachmentsMixin:
    """Handles files and audio that arrive as Telegram attachments."""

    async def _handle_attachment(self, chat_id: int, message: dict) -> None:
        """Download a document/photo and process it like the backend does.

        The file is downloaded, its text is extracted with the same
        ``extract_text_from_bytes`` used by the backend, and the result is
        emitted to the frontend as a normal message so the agent processes it.

        Args:
            chat_id: Telegram chat id.
            message: The Telegram message that carries the document or photo.
        """
        document = message.get("document")
        photo = message.get("photo")
        caption = message.get("caption") or ""
        file_id = None
        filename = None
        if document:
            file_id = document.get("file_id")
            filename = document.get("file_name") or "archivo"
        elif photo:
            largest = photo[-1] if isinstance(photo, list) and photo else photo
            file_id = largest.get("file_id")
            filename = "foto.jpg"
        if not file_id:
            return
        try:
            content = await self._download_file(file_id)
        except Exception as exc:
            logger.warning("No se pudo descargar el archivo: %s", exc)
            await self.send_message(chat_id, f"No pude descargar el archivo: {exc}")
            return

        # If in RAG mode, upload the file to the collection instead of
        # emitting it to the frontend.
        if chat_id in self._mode and self._mode[chat_id] == "rag":
            await self._handle_rag_upload(chat_id, filename, content)
            return

        from backend.routes.file_text_extractor import extract_text_from_bytes
        result = extract_text_from_bytes(filename, content)
        if not result.success:
            await self.send_message(chat_id, result.text or "No se pudo procesar el archivo.")
            return
        text = result.text.strip()
        if not text:
            await self.send_message(chat_id, "No se encontró texto en el archivo.")
            return

        full = f"{caption}\n\n**Archivo: {filename}**\n{text}".strip()

        await event_bus.emit({
            "type": "telegram_message",
            "content": full,
            "session_id": self._session.get(chat_id),
            "chat_id": chat_id,
        })
