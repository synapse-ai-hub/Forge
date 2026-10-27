"""Telegram bot: polling bridge that emits events to the event bus.

The bot does NOT run the agent loop. When a message arrives it publishes a
``telegram_message`` event (with the resolved ``session_id``) to the event
bus; the frontend receives it through ``/api/events`` and runs the normal
chat flow (``chatService.sendMessage`` -> ``POST /api/chat``). When the
backend finishes that request it calls ``send_message`` to deliver the final
answer back to Telegram.

The bot also handles a set of commands directly (``/sesiones``, ``/usar``,
``/actual``, ``/contexto``, ``/borrar``, ``/proveedor``, ``/modelo``,
``/skills``, ``/tools``, ``/agentes``, ``/ayuda``, ``/cancelar``). Commands
that need a user reply (``/usar``, ``/borrar``, ``/proveedor``, ``/modelo``)
use a per-chat "awaiting" state: the bot asks a question and the next plain
message is treated as the answer. ``/cancelar`` (or the word "cancelar")
aborts any pending question.
"""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from backend.telegram.polling import PollingMixin
from backend.telegram.dispatch import DispatchMixin
from backend.telegram.transport import TransportMixin
from backend.telegram.attachments import AttachmentsMixin
from backend.telegram.create_flows import CreateFlowsMixin
from backend.telegram.rag_flow import RagFlowMixin
from backend.telegram.downloads import DownloadsMixin
from backend.telegram.commands.sessions import SessionCommandsMixin
from backend.telegram.commands.models import ModelCommandsMixin
from backend.telegram.commands.listings import ListingCommandsMixin
from backend.telegram.commands.billing import BillingCommandsMixin
from backend.telegram.commands.scheduler import SchedulerCommandsMixin
from backend.telegram.commands.help import HelpCommandsMixin
from backend.telegram.commands.files import FileCommandsMixin

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.agent.session import SessionManager

logger = logging.getLogger(__name__)


class TelegramBot(
    PollingMixin,
    DispatchMixin,
    TransportMixin,
    AttachmentsMixin,
    CreateFlowsMixin,
    RagFlowMixin,
    DownloadsMixin,
    SessionCommandsMixin,
    ModelCommandsMixin,
    ListingCommandsMixin,
    BillingCommandsMixin,
    SchedulerCommandsMixin,
    HelpCommandsMixin,
    FileCommandsMixin,
):
    """Minimal Telegram bot using long-polling against the Bot API."""

    def __init__(
        self,
        token: str,
        session_manager: SessionManager,
        allowed_chat_ids: set[int] | None = None,
    ) -> None:
        """Create the bot.

        Args:
            token: Bot token.
            session_manager: Session manager shared with the web app.
            allowed_chat_ids: Chats allowed to talk to the bot.
        """
        self.token = token
        self.session_manager = session_manager
        self.allowed_chat_ids = allowed_chat_ids if allowed_chat_ids is not None else set()
        # chat_id -> current session_id (set via /nueva, /usar, /borrar)
        self._session: dict[int, str | None] = {}
        # chat_id -> command awaiting a user reply ("usar", "borrar", ...)
        self._awaiting: dict[int, str] = {}
        self._offset = 0
        self._running = False
        self._task: asyncio.Task | None = None
        self._enabled = False
        self._client = httpx.AsyncClient(timeout=30.0)
        self.mode = os.getenv("MODE", os.getenv("VITE_MODE", "dev")).strip().lower()
        self.is_dev = self.mode == "dev"
        # Mode state for skill/RAG creation via Telegram (remote control).
        # chat_id -> "skill" | "rag"
        self._mode: dict[int, str] = {}
        # Per-chat mode data (skill: descripcion/name/mensajes; rag: collection).
        self._mode_data: dict[int, dict] = {}
        # Session to restore after the mode ends.
        self._prev_session: dict[int, str | None] = {}
        # Pending conversation download (chat_id -> {"kind", "mensajes", "title"}).
        self._pending_download: dict[int, dict] = {}

    @property
    def enabled(self) -> bool:
        """Whether the bot is enabled.

        Returns:
            True when the bot processes updates.
        """
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        """Enable or disable the bot.

        Args:
            value: True to process updates.
        """
        self._enabled = bool(value)
        logger.info("Telegram enabled=%s", self._enabled)

    async def start(self) -> None:
        """Start the task that polls Telegram for updates."""
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("Telegram bot polling started (enabled=%s).", self._enabled)

    async def stop(self) -> None:
        """Stop the polling task and close the HTTP client."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._client.aclose()
