"""Conversation download: ask where to save and write the exported file."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class DownloadsMixin:
    """Export of a conversation to a file chosen by the user."""

    async def _handle_download_question(self, chat_id: int, text: str) -> None:
        """Handle the user's answer to the "download conversation?" question.

        Args:
            chat_id: The Telegram chat id.
            text: The user's reply.
        """
        pending = self._pending_download.pop(chat_id, None)
        if not pending:
            return
        answer = text.strip().lower()
        if answer in ("sí", "si", "yes", "y"):
            self._pending_download[chat_id] = pending
            self._awaiting[chat_id] = "descargar_path"
            await self.send_message(
                chat_id, "¿Dónde querés guardarla? (path, 'default' o 'cancelar')"
            )
            return
        # "no" or anything else → close without downloading.
        await self._close_create_window(chat_id, pending["kind"])
        await self.send_message(chat_id, "Listo. Ventana cerrada.")

    async def _handle_download_path(self, chat_id: int, text: str) -> None:
        """Handle the user's path answer and save the conversation.

        Args:
            chat_id: The Telegram chat id.
            text: The user's reply (a path, "default" or "cancelar").
        """
        pending = self._pending_download.pop(chat_id, None)
        if not pending:
            return
        kind = pending["kind"]
        answer = text.strip()
        if answer.lower() == "default":
            path = self._default_download_path()
        else:
            path = answer
        try:
            md = await self._export_conversation(pending["mensajes"], pending["title"])
            await asyncio.to_thread(self._write_file, path, md)
            await self.send_message(chat_id, f"Conversación guardada en: {path}")
        except Exception as exc:
            logger.warning("No se pudo guardar la conversación: %s", exc)
            await self.send_message(
                chat_id, f"No se pudo guardar la conversación: {exc}"
            )
        await self._close_create_window(chat_id, kind)

    def _default_download_path(self) -> str:
        """Build the default Windows Downloads folder path for the file.

        Returns:
            The path as text.
        """
        return str(Path.home() / "Downloads" / "conversacion.md")

    async def _export_conversation(self, mensajes: list, title: str) -> str:
        """Generate the Markdown for a conversation via the export endpoint.

        Args:
            mensajes: The conversation messages (list of role/content dicts).
            title: The document title.

        Returns:
            The generated Markdown string.
        """
        from backend.routes.conversation import (
            ExportRequest,
            Message,
            conversation_to_markdown,
        )

        msgs = [
            Message(
                id=str(i),
                type=m.get("role", "assistant"),
                content=m.get("content", ""),
            )
            for i, m in enumerate(mensajes)
        ]
        return conversation_to_markdown(msgs, title)

    def _write_file(self, path: str, content: str) -> None:
        """Write content to a file, creating parent directories if needed.

        Args:
            path: File to write.
            content: Text to write.
        """
        target = Path(path)
        if target.suffix.lower() != ".md":
            target = target.with_suffix(".md")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
