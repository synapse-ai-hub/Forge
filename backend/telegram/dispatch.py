"""Update dispatch: routes each update to a command, a pending question or the event bus."""

from __future__ import annotations

import logging

from backend.event_bus import event_bus

logger = logging.getLogger(__name__)

class DispatchMixin:
    """Routes incoming updates and resolves per-chat "awaiting" replies."""

    async def _handle_update(self, update: dict) -> None:
        message = update.get("message") or update.get("edited_message")
        if not message:
            return
        chat_id = message["chat"]["id"]
        text = message.get("text") or ""
        voice = message.get("voice")
        audio = message.get("audio")
        caption = message.get("caption") or ""


        # Whitelist: only allow configured chat ids.
        if chat_id not in self.allowed_chat_ids:
            logger.warning("Telegram update from unauthorized chat_id=%s ignored", chat_id)
            return

        # File attachment (document / photo) -> process like the backend does.
        if message.get("document") or message.get("photo"):
            await self._handle_attachment(chat_id, message)
            return

        # Voice / audio note -> transcribe locally and use as the message.
        voice_file_id = (voice or {}).get("file_id") or (audio or {}).get("file_id")
        if voice_file_id:
            try:
                content = await self._download_file(voice_file_id)
                transcript = await self._transcribe(content)
                text = f"{caption}\n{transcript}".strip() if caption else transcript
                logger.info("Voice transcribed: %d chars", len(transcript))
            except Exception as exc:
                logger.warning("Failed to transcribe voice: %s", exc)
                await self.send_message(chat_id, "No pude transcribir la nota de voz.")
                return

        if not text:
            return

        # "cancelar" aborts any pending question or exits a skill/RAG mode.
        if text.strip().lower() in ("cancelar", "/cancelar"):
            if chat_id in self._mode:
                await self._exit_mode(chat_id, "Cancelado.")
                return
            if chat_id in self._awaiting:
                self._awaiting.pop(chat_id, None)
                self._mode_data.pop(chat_id, None)
                await self.send_message(chat_id, "Cancelado.")
                # If a conversation download was pending, finish the exit
                # (close the window) since the creation already ended.
                pending = self._pending_download.pop(chat_id, None)
                if pending:
                    await self._close_create_window(chat_id, pending["kind"])
            return

        # "terminar" closes the current skill/RAG creation window.
        if text.strip().lower() == "terminar":
            if chat_id in self._mode:
                await self._exit_mode(chat_id, "Listo. Ventana cerrada.")
            else:
                await self.send_message(chat_id, "No hay ninguna creación en curso.")
            return

        # If in a skill/RAG mode, route the message to the mode handler.
        if chat_id in self._mode:
            await self._handle_mode_message(chat_id, text)
            return

        # If a command is awaiting a reply, treat this message as the answer.
        if chat_id in self._awaiting:
            await self._process_awaiting(chat_id, text)
            return

        if text.startswith("/"):
            await self._handle_command(chat_id, text)
            return

        # Detect skill/RAG creation intent (Telegram as remote control).
        intent = self._detect_intent(text)
        if intent:
            await self._enter_mode(chat_id, intent, text)
            return

        # Normal message -> emit to the frontend. The frontend decides the
        # session: it continues the currently active session (the one the user
        # has open in the web UI) instead of creating a new one. Only the
        # /nueva command starts a fresh conversation.

        await event_bus.emit({
            "type": "telegram_message",
            "content": text,
            "session_id": self._active_session(chat_id),
            "chat_id": chat_id,
        })

    async def _handle_command(self, chat_id: int, text: str) -> None:
        parts = text.split()
        cmd = parts[0].lower()
        arg = " ".join(parts[1:]) if len(parts) > 1 else ""


        if cmd == "/nueva":
            self._session[chat_id] = None
            try:
                self.session_manager.set_config("active_session", "")
            except Exception as exc:
                logger.warning("No se pudo limpiar la sesión activa: %s", exc)

            await event_bus.emit({
                "type": "telegram_command",
                "command": "nueva",
                "chat_id": chat_id,
            })
        elif cmd == "/detener":
            await event_bus.emit({
                "type": "telegram_command",
                "command": "detener",
                "chat_id": chat_id,
            })
        elif cmd == "/sesiones":
            await self._cmd_sesiones(chat_id)
        elif cmd == "/usar":
            await self._cmd_usar(chat_id)
        elif cmd == "/cancelar":
            self._awaiting.pop(chat_id, None)
            self._mode_data.pop(chat_id, None)
            await self.send_message(chat_id, "Cancelado.")
        elif cmd == "/actual":
            await self._cmd_actual(chat_id)
        elif cmd == "/contexto":
            await self._cmd_contexto(chat_id)
        elif cmd == "/borrar":
            await self._cmd_borrar(chat_id)
        elif cmd == "/proveedor":
            await self._cmd_proveedor(chat_id)
        elif cmd == "/modelo":
            await self._cmd_modelo(chat_id)
        elif cmd == "/skills":
            await self._cmd_skills(chat_id)
        elif cmd == "/tools":
            await self._cmd_tools(chat_id)
        elif cmd == "/agentes":
            await self._cmd_agentes(chat_id)
        elif cmd == "/crear":
            await self._cmd_crear(chat_id, arg)
        elif cmd == "/archivo":
            await self._cmd_archivo(chat_id, arg)
        elif cmd == "/agenda":
            await self._cmd_agenda(chat_id)
        elif cmd == "/agendar":
            await self._cmd_agendar(chat_id, arg)
        elif cmd == "/horario":
            await self._cmd_horario(chat_id, arg)
        elif cmd == "/eliminar_tarea":
            await self._cmd_eliminar_tarea(chat_id, arg)
        elif cmd == "/uso":
            await self._cmd_usage(chat_id)
        elif cmd == "/facturacion":
            await self._cmd_billing(chat_id)
        elif cmd in ("/ayuda", "/help"):
            await self._cmd_ayuda(chat_id)
        else:
            await self.send_message(chat_id, f"Comando desconocido: {cmd}")

    async def _process_awaiting(self, chat_id: int, text: str) -> None:
        """Process a reply given while a command is awaiting an argument."""
        cmd = self._awaiting.pop(chat_id, None)
        if not cmd:
            return

        if text.strip().lower() == "cancelar":
            await self.send_message(chat_id, "Cancelado.")
            return
        if cmd == "usar":
            await self._cmd_usar(chat_id, text)
        elif cmd == "borrar":
            await self._cmd_borrar(chat_id, text)
        elif cmd == "proveedor":
            await self._cmd_proveedor(chat_id, text)
        elif cmd == "modelo":
            await self._cmd_modelo(chat_id, text)
        elif cmd == "crear":
            await self._cmd_crear(chat_id, text)
        elif cmd == "archivo":
            await self._cmd_archivo(chat_id, text)
        elif cmd == "descargar":
            await self._handle_download_question(chat_id, text)
        elif cmd == "descargar_path":
            await self._handle_download_path(chat_id, text)
        elif cmd.startswith("agenda_"):
            await self._process_agenda_awaiting(chat_id, cmd, text)
        elif cmd.startswith("horario_"):
            await self._process_horario_awaiting(chat_id, cmd, text)
        elif cmd == "eliminar_tarea_num":
            await self._eliminar_tarea_num(chat_id, text)
        elif cmd.startswith("billing_"):
            await self._process_billing_awaiting(chat_id, cmd, text)
