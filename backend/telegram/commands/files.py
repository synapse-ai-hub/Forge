"""File command: send a file to the chat."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

class FileCommandsMixin:
    """``/archivo``."""

    async def _cmd_archivo(self, chat_id: int, path: str | None = None) -> None:
        """Send a file from the local filesystem to the chat.

        If no path is given, asks the user for one (or "cancelar"). Otherwise
        validates the path and sends the file as a Telegram document.

        Args:
            chat_id: The Telegram chat id.
            path: The file path to send, or ``None`` to ask for it.
        """
        if not path:
            self._awaiting[chat_id] = "archivo"
            await self.send_message(
                chat_id, "¿Qué archivo querés? (path o 'cancelar')"
            )
            return
        path = path.strip()
        if not os.path.isfile(path):
            await self.send_message(
                chat_id, f"No encontré el archivo: {path}"
            )
            return
        try:
            await self._send_document(chat_id, path)
        except Exception as exc:
            logger.warning("No se pudo enviar el archivo: %s", exc)
            await self.send_message(
                chat_id, f"No se pudo enviar el archivo: {exc}"
            )
