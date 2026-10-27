"""Session commands: list, switch, show, context window and delete."""

from __future__ import annotations

import logging

from backend.event_bus import event_bus

logger = logging.getLogger(__name__)

class SessionCommandsMixin:
    """``/sesiones``, ``/usar``, ``/actual``, ``/contexto`` and ``/borrar``."""

    def _list_sessions(self) -> list[dict]:
        """List the root sessions.

        Returns:
            The sessions, most recent first.
        """
        try:
            return self.session_manager.list_sessions() or []
        except Exception as exc:
            logger.warning("No se pudieron listar sesiones: %s", exc)
            return []

    def _session_title(self, session_id: str) -> str | None:
        """Look up the title of a session.

        Args:
            session_id: Session identifier.

        Returns:
            The title (the session id when it has none), or None when the session does not exist.
        """
        for s in self._list_sessions():
            if s.get("session_id") == session_id:
                return s.get("title") or session_id
        return None

    def _active_session(self, chat_id: int) -> str | None:
        """Get the active session for a chat.

        Prefers the in-memory per-chat session (set via ``/usar``, ``/nueva``,
        ``/borrar``). Falls back to the DB-persisted ``active_session`` so a
        session selected in the frontend is also active in Telegram.

        Args:
            chat_id: Telegram chat id.

        Returns:
            The session id, or None when there is no active session.
        """
        sid = self._session.get(chat_id)
        if sid:
            return sid
        try:
            return self.session_manager.get_config("active_session")
        except Exception as exc:
            logger.warning("No se pudo leer la sesión activa de la DB: %s", exc)
            return None

    async def _cmd_sesiones(self, chat_id: int) -> None:
        """Answer ``/sesiones``: list the sessions of the user.

        Args:
            chat_id: Telegram chat id.
        """
        sessions = self._list_sessions()
        if not sessions:
            await self.send_message(chat_id, "No hay sesiones.")
            return
        lines = ["Sesiones:"]
        for s in sessions:
            title = s.get("title") or "Sin título"
            lines.append(f"- {title}")
        await self.send_message(chat_id, "\n".join(lines))

    async def _cmd_usar(self, chat_id: int, title: str | None = None) -> None:
        """Answer ``/usar``: activate the session with the given title.

        Args:
            chat_id: Telegram chat id.
            title: Title of the session; when None the bot asks for it.
        """
        sessions = self._list_sessions()
        if not sessions:
            await self.send_message(chat_id, "No hay sesiones.")
            return
        if not title:
            self._awaiting[chat_id] = "usar"
            lines = ["¿Qué sesión querés usar? (respondé con el título o 'cancelar')"]
            for s in sessions:
                lines.append(f"- {s.get('title') or 'Sin título'}")
            await self.send_message(chat_id, "\n".join(lines))
            return
        target = next((s for s in sessions if (s.get("title") or "Sin título") == title), None)
        if not target:
            await self.send_message(chat_id, f"No encontré la sesión '{title}'.")
            return
        self._session[chat_id] = target["session_id"]
        try:
            self.session_manager.set_config("active_session", target["session_id"])
        except Exception as exc:
            logger.warning("No se pudo persistir la sesión activa: %s", exc)
        # Notify the frontend so it switches to the selected session.
        await event_bus.emit({
            "type": "telegram_command",
            "command": "usar",
            "session_id": target["session_id"],
            "chat_id": chat_id,
        })
        await self.send_message(chat_id, f"Sesión cambiada a '{target.get('title') or target['session_id']}'.")

    async def _cmd_actual(self, chat_id: int) -> None:
        """Answer ``/actual``: tell which session is active.

        Args:
            chat_id: Telegram chat id.
        """
        sid = self._active_session(chat_id)
        if not sid:
            await self.send_message(chat_id, "No hay sesión activa.")
            return
        title = self._session_title(sid)
        await self.send_message(chat_id, f"Sesión actual: {title or sid}")

    async def _cmd_contexto(self, chat_id: int) -> None:
        """Report the context usage of the active session.

        Shows session title, model, model context window, tokens used
        (cumulative ``prompt_tokens`` of the latest assistant message) and
        the percentage of the context window consumed.

        Args:
            chat_id: Telegram chat id.
        """
        sid = self._active_session(chat_id)
        if not sid:
            await self.send_message(chat_id, "No hay sesión activa.")
            return

        model = None
        context_window = None
        try:
            from backend.instances import agent
            model = agent._resolved_model if agent is not None else None
            context_window = agent._context_window if agent is not None else None
        except Exception as exc:
            logger.warning("No se pudo leer modelo/context window: %s", exc)

        title = self._session_title(sid) or sid

        prompt_tokens = None
        try:
            msgs = self.session_manager.load_messages(sid) or []
            for m in reversed(msgs):
                if m.get("role") == "assistant" and m.get("prompt_tokens"):
                    prompt_tokens = m["prompt_tokens"]
                    break
        except Exception as exc:
            logger.warning("No se pudieron leer los tokens de la sesión: %s", exc)

        percent = (
            round((prompt_tokens / context_window) * 100, 2)
            if (prompt_tokens and context_window)
            else None
        )

        lines = [
            f"Título: {title}",
            f"Modelo: {model or 'desconocido'}",
            f"Ventana de contexto: {context_window if context_window else 'desconocida'} tokens",
            f"Tokens utilizados: {prompt_tokens if prompt_tokens is not None else 'desconocido'}",
            f"Porcentaje: {percent if percent is not None else 'desconocido'}%",
        ]
        await self.send_message(chat_id, "\n".join(lines))

    async def _cmd_borrar(self, chat_id: int, title: str | None = None) -> None:
        """Answer ``/borrar``: delete the session with the given title.

        Args:
            chat_id: Telegram chat id.
            title: Title of the session; when None the bot asks for it.
        """
        sessions = self._list_sessions()
        if not sessions:
            await self.send_message(chat_id, "No hay sesiones.")
            return
        if not title:
            self._awaiting[chat_id] = "borrar"
            lines = ["¿Qué sesión querés borrar? (respondé con el título o 'cancelar')"]
            for s in sessions:
                lines.append(f"- {s.get('title') or 'Sin título'}")
            await self.send_message(chat_id, "\n".join(lines))
            return
        target = next((s for s in sessions if (s.get("title") or "Sin título") == title), None)
        if not target:
            await self.send_message(chat_id, f"No encontré la sesión '{title}'.")
            return
        try:
            self.session_manager.delete_session(target["session_id"])
        except Exception as exc:
            logger.warning("No se pudo borrar la sesión: %s", exc)
            await self.send_message(chat_id, f"No se pudo borrar la sesión '{title}'.")
            return
        if self._session.get(chat_id) == target["session_id"]:
            self._session[chat_id] = None
        # Notify the frontend so the sidebar refreshes after the deletion.
        await event_bus.emit({
            "type": "telegram_command",
            "command": "borrar",
            "chat_id": chat_id,
        })
        await self.send_message(chat_id, f"Sesión '{title}' borrada.")
