"""Skill, tool and RAG creation modes driven from Telegram (remote control)."""

from __future__ import annotations

import json
import logging

from backend.event_bus import event_bus

logger = logging.getLogger(__name__)

class CreateFlowsMixin:
    """Per-chat creation modes: intent detection, iteration against the create endpoints and RAG upload."""

    def _detect_intent(self, text: str) -> str | None:
        """Detect whether a message asks to create a skill, tool or RAG collection.

        Args:
            text: The incoming message text.

        Returns:
            ``"skill"``, ``"tool"``, ``"rag"`` or ``None`` if no creation intent is found.
        """
        t = text.strip().lower()
        if "crear skill" in t or "crear una skill" in t or "crear la skill" in t:
            return "skill"
        if (
            "crear tool" in t
            or "crear una tool" in t
            or "crear la tool" in t
            or "crear una herramienta" in t
            or "crear herramienta" in t
        ):
            return "tool"
        if (
            "crear rag" in t
            or "crear un rag" in t
            or "crear colección" in t
            or "crear coleccion" in t
            or "crear una colección" in t
            or "crear una coleccion" in t
        ):
            return "rag"
        return None

    def _extract_skill_descripcion(self, text: str) -> str | None:
        """Extract the skill description that follows 'crear skill'.

        Args:
            text: The full message text.

        Returns:
            The description, or ``None`` if nothing follows the trigger.
        """
        t = text.strip()
        lower = t.lower()
        for marker in ("crear skill", "crear una skill", "crear la skill"):
            idx = lower.find(marker)
            if idx != -1:
                desc = t[idx + len(marker):].strip()
                return desc or None
        return None

    def _extract_tool_descripcion(self, text: str) -> str | None:
        """Extract the tool description that follows 'crear tool/herramienta'.

        Args:
            text: The full message text.

        Returns:
            The description, or ``None`` if nothing follows the trigger.
        """
        t = text.strip()
        lower = t.lower()
        markers = (
            "crear una herramienta",
            "crear herramienta",
            "crear una tool",
            "crear la tool",
            "crear tool",
        )
        for marker in markers:
            idx = lower.find(marker)
            if idx != -1:
                desc = t[idx + len(marker):].strip()
                return desc or None
        return None

    async def _enter_mode(self, chat_id: int, intent: str, text: str) -> None:
        """Enter a skill, tool or RAG creation mode for a chat.

        Saves the current session so it can be restored when the mode ends.

        Args:
            chat_id: The Telegram chat id.
            intent: ``"skill"``, ``"tool"`` or ``"rag"``.
            text: The triggering message text.
        """
        self._prev_session[chat_id] = self._active_session(chat_id)
        if intent == "skill":
            descripcion = self._extract_skill_descripcion(text)
            self._mode[chat_id] = "skill"
            self._mode_data[chat_id] = {
                "descripcion": descripcion,
                "name": None,
                "mensajes": [],
            }
            await self._emit_create_window(chat_id, intent, "open")
            if not descripcion:
                await self.send_message(
                    chat_id, "¿Qué skill querés crear? Describí la tarea (o /cancelar)."
                )
                return
            await self._run_skill_iteration(chat_id)
        elif intent == "tool":
            descripcion = self._extract_tool_descripcion(text)
            self._mode[chat_id] = "tool"
            self._mode_data[chat_id] = {
                "descripcion": descripcion,
                "name": None,
                "mensajes": [],
            }
            await self._emit_create_window(chat_id, intent, "open")
            if not descripcion:
                await self.send_message(
                    chat_id, "¿Qué tool querés crear? Describí la tarea (o /cancelar)."
                )
                return
            await self._run_tool_iteration(chat_id)
        elif intent == "rag":
            self._mode[chat_id] = "rag"
            self._mode_data[chat_id] = {"collection": None}
            await self._emit_create_window(chat_id, intent, "open")
            await self.send_message(
                chat_id, "¿Nombre de la colección? (o /cancelar)"
            )

    async def _handle_mode_message(self, chat_id: int, text: str) -> None:
        """Route a message while a skill/tool/RAG mode is active.

        Args:
            chat_id: The Telegram chat id.
            text: The message text.
        """
        mode = self._mode.get(chat_id)
        data = self._mode_data.get(chat_id, {})
        if mode == "skill":
            if not data.get("descripcion"):
                data["descripcion"] = text.strip()
                await self._run_skill_iteration(chat_id)
                return
            data["mensajes"] = data.get("mensajes", []) + [
                {"role": "user", "content": text}
            ]
            await self._run_skill_iteration(chat_id)
        elif mode == "tool":
            if not data.get("descripcion"):
                data["descripcion"] = text.strip()
                await self._run_tool_iteration(chat_id)
                return
            data["mensajes"] = data.get("mensajes", []) + [
                {"role": "user", "content": text}
            ]
            await self._run_tool_iteration(chat_id)
        elif mode == "rag":
            if data.get("awaiting_finish"):
                await self._handle_rag_finish(chat_id, text.strip())
            elif not data.get("collection"):
                await self._create_rag_collection(chat_id, text.strip())
            else:
                await self._handle_rag_url(chat_id, text.strip())

    async def _run_skill_iteration(self, chat_id: int) -> None:
        """Run one skill-creation iteration against the /api/create/skill route.

        Streams the SSE response and either asks the next question (staying in
        the mode) or finishes the skill (exiting the mode).

        Args:
            chat_id: The Telegram chat id.
        """
        data = self._mode_data.get(chat_id, {})
        descripcion = data.get("descripcion")
        if not descripcion:
            return
        mensajes = data.get("mensajes", [])
        try:
            import json as _json

            from backend.routes.create.skill import post_create_skill_stream

            resp = await post_create_skill_stream(
                descripcion=descripcion,
                name=data.get("name"),
                mensajes=_json.dumps(mensajes),
                model=None,
                provider=None,
                iterate=False,
                files=None,
            )
            accumulated = ""
            async for raw in resp.body_iterator:
                for event in self._parse_sse(raw):
                    etype = event.get("type")
                    if etype == "chunk":
                        accumulated += event.get("content", "")
                    elif etype == "skill_action":
                        action = (event.get("content") or {}).get("action")
                        if action == "question":
                            question = (event.get("content") or {}).get("question", "")
                            if accumulated.strip():
                                mensajes.append(
                                    {"role": "assistant", "content": accumulated}
                                )
                            data["mensajes"] = mensajes
                            await self.send_message(
                                chat_id, question or accumulated or "Continuá."
                            )
                            return
                    elif etype == "skill_result":
                        content = event.get("content") or {}
                        if content.get("status") == "success":
                            await self.send_message(
                                chat_id,
                                content.get("message", "Skill creada exitosamente."),
                            )
                        else:
                            await self.send_message(
                                chat_id,
                                "Error: "
                                + (content.get("message") or "Error desconocido"),
                            )
                        await self._exit_mode(chat_id)
                        return
                    elif etype == "error":
                        await self.send_message(
                            chat_id, event.get("content") or "Error al crear la skill."
                        )
                        await self._exit_mode(chat_id)
                        return
        except Exception as exc:
            logger.warning("Error en skill iteration: %s", exc)
            await self.send_message(chat_id, "Error al comunicarse con el backend.")
            await self._exit_mode(chat_id)

    async def _run_tool_iteration(self, chat_id: int) -> None:
        """Run one tool-creation iteration against the /api/create/tool route.

        Streams the SSE response and either asks the next question (staying in
        the mode) or finishes the tool (exiting the mode).

        Args:
            chat_id: The Telegram chat id.
        """
        data = self._mode_data.get(chat_id, {})
        descripcion = data.get("descripcion")
        if not descripcion:
            return
        mensajes = data.get("mensajes", [])
        try:
            from backend.routes.create import CreateToolRequest, post_create_tool_stream

            resp = await post_create_tool_stream(
                CreateToolRequest(
                    descripcion=descripcion,
                    name=data.get("name"),
                    mensajes=mensajes,
                )
            )
            accumulated = ""
            async for raw in resp.body_iterator:
                for event in self._parse_sse(raw):
                    etype = event.get("type")
                    if etype == "chunk":
                        accumulated += event.get("content", "")
                    elif etype == "tool_action":
                        action = (event.get("content") or {}).get("action")
                        if action == "question":
                            question = (event.get("content") or {}).get("question", "")
                            if accumulated.strip():
                                mensajes.append(
                                    {"role": "assistant", "content": accumulated}
                                )
                            data["mensajes"] = mensajes
                            await self.send_message(
                                chat_id, question or accumulated or "Continuá."
                            )
                            return
                        if action == "creating":
                            await self.send_message(
                                chat_id, "Creando tool..."
                            )
                    elif etype == "tool_result_final":
                        content = event.get("content") or {}
                        if isinstance(content, dict):
                            msg = content.get("message", "")
                            status = content.get("status", "success")
                        else:
                            msg = str(content)
                            status = "success"
                        if status == "success":
                            await self.send_message(chat_id, msg or "Tool creada.")
                        else:
                            await self.send_message(
                                chat_id,
                                "Error: " + (msg or "Error desconocido"),
                            )
                        await self._exit_mode(chat_id)
                        return
                    elif etype == "error":
                        await self.send_message(
                            chat_id, event.get("content") or "Error al crear la tool."
                        )
                        await self._exit_mode(chat_id)
                        return
        except Exception as exc:
            logger.warning("Error en tool iteration: %s", exc)
            await self.send_message(chat_id, "Error al comunicarse con el backend.")
            await self._exit_mode(chat_id)

    async def _exit_mode(self, chat_id: int, message: str | None = None) -> None:
        """Exit a skill/RAG mode and restore the previous session.

        For skill/tool creation with a conversation, it first asks the user
        (via Telegram) whether they want to download the conversation before
        closing the window. The window is only closed once the user answers.

        Args:
            chat_id: The Telegram chat id.
            message: Optional message to send after exiting.
        """
        kind = self._mode.get(chat_id)
        data = self._mode_data.get(chat_id, {})
        mensajes = data.get("mensajes", [])
        self._mode.pop(chat_id, None)
        self._mode_data.pop(chat_id, None)
        prev = self._prev_session.pop(chat_id, None)
        if prev:
            try:
                self.session_manager.set_config("active_session", prev)
            except Exception as exc:
                logger.warning("No se pudo restaurar la sesión: %s", exc)
        # For skill/tool creation with a conversation, ask before closing.
        if kind in ("skill", "tool") and mensajes:
            if message:
                await self.send_message(chat_id, message)
            self._pending_download[chat_id] = {
                "kind": kind,
                "mensajes": mensajes,
                "title": (
                    "Conversación - Creador de Skills"
                    if kind == "skill"
                    else "Conversación - Creador de Tools"
                ),
            }
            self._awaiting[chat_id] = "descargar"
            await self.send_message(
                chat_id, "¿Querés descargar la conversación? (sí/no/cancelar)"
            )
            return
        if kind:
            await self._emit_create_window(chat_id, kind, "close")
        if message:
            await self.send_message(chat_id, message)

    async def _close_create_window(self, chat_id: int, kind: str) -> None:
        """Close the create window for a chat (used after the download flow)."""
        if kind:
            await self._emit_create_window(chat_id, kind, "close")

    async def _emit_create_window(self, chat_id: int, kind: str, action: str) -> None:
        """Emit an event to the frontend to open/close the create window.

        Telegram acts as a remote control ("or"): the same window the user
        would open in the web UI is opened/closed in the frontend.

        Args:
            chat_id: The Telegram chat id.
            kind: ``"skill"`` or ``"rag"``.
            action: ``"open"`` or ``"close"``.
        """
        await event_bus.emit({
            "type": "telegram_create",
            "kind": kind,
            "action": action,
            "chat_id": chat_id,
        })

    @staticmethod
    def _parse_sse(raw: bytes) -> list[dict]:
        """Parse SSE ``data:`` lines from a raw chunk into event dicts.

        Args:
            raw: Raw bytes from the streaming response.

        Returns:
            A list of parsed event dicts.
        """
        events: list[dict] = []
        text = raw.decode("utf-8", errors="ignore")
        for line in text.splitlines():
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                continue
            try:
                events.append(json.loads(payload))
            except Exception:
                continue
        return events

    async def _cmd_crear(self, chat_id: int, arg: str) -> None:
        """Handle ``/crear``.

        With an argument (``/crear skill <desc>``, ``/crear tool <desc>`` or
        ``/crear rag``) it enters the mode directly. Without arguments it asks
        what to create and routes the reply (or /cancelar).

        Args:
            chat_id: The Telegram chat id.
            arg: The argument after ``/crear``.
        """
        sub = arg.strip().lower()
        if sub.startswith("skill"):
            desc = arg.strip()[5:].strip()
            await self._enter_mode(chat_id, "skill", f"crear skill {desc}")
        elif sub.startswith("tool") or sub.startswith("herramienta"):
            desc_marker = arg.strip()
            lower_marker = arg.strip().lower()
            for marker in ("tool", "herramienta"):
                idx = lower_marker.find(marker)
                if idx != -1:
                    desc_marker = arg.strip()[idx + len(marker):].strip()
                    break
            await self._enter_mode(chat_id, "tool", f"crear tool {desc_marker}")
        elif sub.startswith("rag") or sub.startswith("coleccion") or sub.startswith("colección"):
            await self._enter_mode(chat_id, "rag", "crear rag")
        else:
            self._awaiting[chat_id] = "crear"
            await self.send_message(
                chat_id, "¿Qué querés crear? (skill, tool o rag, o /cancelar)"
            )
