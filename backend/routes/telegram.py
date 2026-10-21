"""Telegram status and toggle endpoints.

The toggle only controls whether the bot polls Telegram. It is persisted in
``config_kv`` so it survives restarts.
"""

from __future__ import annotations

import logging
import os
import sys

from fastapi import APIRouter
from pydantic import BaseModel

_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.instances import session_manager
from backend.telegram.instance import telegram_bot

logger = logging.getLogger(__name__)

router = APIRouter()


class TogglePayload(BaseModel):
    """Body of the request that enables or disables the Telegram bot."""
    enabled: bool


class ActiveSessionPayload(BaseModel):
    """Body of the request that sets the active session shared with Telegram."""
    session_id: str


@router.get("/telegram/status")
async def telegram_status() -> dict:
    """Report whether the Telegram bot is currently enabled.

    Returns:
        A dict with the ``enabled`` flag.
    """
    return {"enabled": telegram_bot.enabled}


@router.post("/telegram/toggle")
async def telegram_toggle(payload: TogglePayload) -> dict:
    """Enable/disable the Telegram bot and persist the choice.

    Args:
        payload: Body with the new ``enabled`` value.

    Returns:
        A dict with the resulting ``enabled`` flag.
    """
    telegram_bot.set_enabled(payload.enabled)
    session_manager.set_config("telegram_enabled", "true" if payload.enabled else "false")
    logger.info("Telegram toggle -> %s", payload.enabled)
    return {"enabled": payload.enabled}


@router.get("/telegram/active-session")
async def telegram_active_session() -> dict:
    """Get the active session id shared between frontend and Telegram.

    Returns:
        A dict with the ``session_id``.
    """
    sid = session_manager.get_config("active_session")
    return {"session_id": sid}


@router.post("/telegram/active-session")
async def telegram_set_active_session(payload: ActiveSessionPayload) -> dict:
    """Persist the active session id (single source of truth for front/Telegram).

    Args:
        payload: Body with the new ``session_id``.

    Returns:
        A dict with the stored ``session_id``.
    """
    session_manager.set_config("active_session", payload.session_id)
    logger.info("Active session -> %s", payload.session_id)
    return {"session_id": payload.session_id}