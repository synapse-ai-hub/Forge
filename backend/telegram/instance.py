"""Singleton Telegram bot instance.

Created at import time from environment variables so it can be referenced
both by the routes (``/api/telegram/*``) and by ``chat.py`` (to deliver the
final answer to Telegram).
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)

_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.session import SessionManager
from backend.telegram.bot import TelegramBot


def _create_bot() -> TelegramBot:
    """Create the bot from the environment.

    Reads ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_ALLOWED_CHAT_IDS`` (comma-separated).

    Returns:
        The bot, not started.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    allowed_chat_ids: set[int] = set()
    for part in os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            allowed_chat_ids.add(int(part))
        except ValueError:
            logger.warning("Invalid TELEGRAM_ALLOWED_CHAT_IDS entry ignored: %r", part)
    return TelegramBot(
        token=token,
        session_manager=SessionManager(),
        allowed_chat_ids=allowed_chat_ids,
    )


telegram_bot = _create_bot()
