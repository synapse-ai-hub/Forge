"""RAG collection creation mode driven from Telegram: collection name, URLs and file uploads."""

from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

class RagFlowMixin:
    """Creates a RAG collection and feeds it URLs and uploaded files."""

    async def _create_rag_collection(self, chat_id: int, name: str) -> None:
        """Create a RAG collection via the /api/rag/collections route.

        Args:
            chat_id: The Telegram chat id.
            name: The collection name.
        """
        try:
            from backend.routes.rag import CreateCollectionRequest, create_collection

            result = await create_collection(
                CreateCollectionRequest(name=name, description="")
            )
            if result.get("status") == "success":
                self._mode_data[chat_id]["collection"] = name
                self._mode_data[chat_id]["awaiting_finish"] = True
                await self.send_message(
                    chat_id,
                    f"Colección '{name}' creada. ¿Querés terminar? (sí/no)",
                )
            else:
                await self.send_message(
                    chat_id, result.get("message") or "No se pudo crear la colección."
                )
                # Stay in mode: the next message is another name attempt (or
                # /cancelar) instead of going to the general session.
        except Exception as exc:
            logger.warning("Error creando colección: %s", exc)
            await self.send_message(chat_id, "Error al crear la colección.")
            await self._exit_mode(chat_id)

    async def _handle_rag_url(self, chat_id: int, url: str) -> None:
        """Add a URL to the active RAG collection via the /api/rag route.

        Args:
            chat_id: The Telegram chat id.
            url: The URL to add.
        """
        name = self._mode_data.get(chat_id, {}).get("collection")
        if not name:
            return
        try:
            from backend.routes.rag import AddUrlRequest, add_url

            result = await add_url(name, AddUrlRequest(url=url))
            if result.get("status") == "success":
                self._mode_data[chat_id]["awaiting_finish"] = True
                await self.send_message(
                    chat_id,
                    f"{result.get('message') or f'Página agregada a {name!r}.'} ¿Querés terminar? (sí/no)",
                )
            else:
                await self.send_message(
                    chat_id, result.get("message") or "No se pudo agregar la URL."
                )
        except Exception as exc:
            logger.warning("Error agregando URL: %s", exc)
            await self.send_message(chat_id, "Error al agregar la URL.")

    async def _handle_rag_upload(
        self, chat_id: int, filename: str, content: bytes
    ) -> None:
        """Upload a file to the active RAG collection via the /api/rag route.

        Args:
            chat_id: The Telegram chat id.
            filename: The file name.
            content: The file bytes.
        """
        name = self._mode_data.get(chat_id, {}).get("collection")
        if not name:
            return
        try:
            from fastapi import UploadFile
            from backend.routes.rag import upload_files

            result = await upload_files(
                name, [UploadFile(filename=filename, file=io.BytesIO(content))]
            )
            if result.get("status") == "success":
                self._mode_data[chat_id]["awaiting_finish"] = True
                await self.send_message(
                    chat_id,
                    f"{result.get('message') or f'Archivo procesado en {name!r}.'} ¿Querés terminar? (sí/no)",
                )
            else:
                await self.send_message(
                    chat_id, result.get("message") or "No se pudo procesar el archivo."
                )
        except Exception as exc:
            logger.warning("Error subiendo archivo: %s", exc)
            await self.send_message(chat_id, "Error al subir el archivo.")

    async def _handle_rag_finish(self, chat_id: int, text: str) -> None:
        """Handle the "¿Querés terminar?" reply in RAG mode.

        Args:
            chat_id: The Telegram chat id.
            text: The user reply (sí/no).
        """
        t = text.strip().lower()
        if t in ("si", "sí", "yes", "y"):
            await self._exit_mode(chat_id, "Listo. Ventana de RAG cerrada.")
        elif t in ("no", "n"):
            self._mode_data[chat_id]["awaiting_finish"] = False
            await self.send_message(chat_id, "Subí archivos o URLs, o /cancelar.")
        else:
            await self.send_message(chat_id, "Respondé sí o no, o /cancelar.")
