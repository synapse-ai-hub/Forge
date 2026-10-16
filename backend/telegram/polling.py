"""Long-polling against the Telegram Bot API."""

from __future__ import annotations

import asyncio
import logging

from backend.telegram.transport import _TELEGRAM_API

logger = logging.getLogger(__name__)

class PollingMixin:
    """Polling loop: fetches updates and hands each one to the dispatcher."""

    async def _poll_loop(self) -> None:
        was_enabled = False  # force a sync when the bot becomes enabled (startup or re-enable)
        while self._running:
            if not self._enabled:
                was_enabled = False
                await asyncio.sleep(1)
                continue
            if not was_enabled:
                # Telegram was just enabled (or started enabled): discard any
                # messages that arrived while it was disabled/offline so they
                # are NOT processed. Only messages from the moment of enabling
                # are handled.
                await self._skip_queued_updates()
                was_enabled = True
            try:
                updates = await self._get_updates()
                for update in updates:
                    await self._handle_update(update)
            except Exception as exc:
                logger.warning("Telegram poll error: %s", exc)
            await asyncio.sleep(0.5)

    async def _skip_queued_updates(self) -> None:
        """Advance the poll offset past queued updates without processing them.

        Called when the bot transitions to enabled (startup or re-enable) so
        messages that arrived while Telegram was disabled/offline are discarded
        instead of being replayed. Only updates received after this point are
        handled by the normal polling loop.
        """
        try:
            url = _TELEGRAM_API.format(token=self.token) + "/getUpdates"
            for _ in range(100):  # safety cap (100 rounds * 100 updates)
                resp = await self._client.post(
                    url, json={"timeout": 0, "offset": self._offset}
                )
                data = resp.json()
                if not data.get("ok"):
                    return
                updates = data.get("result", [])
                if not updates:
                    return
                self._offset = updates[-1]["update_id"] + 1

                if len(updates) < 100:
                    return
        except Exception as exc:
            logger.warning("Failed to skip queued Telegram updates: %s", exc)

    async def _get_updates(self) -> list[dict]:
        url = _TELEGRAM_API.format(token=self.token) + "/getUpdates"
        resp = await self._client.post(url, json={"timeout": 0, "offset": self._offset})
        data = resp.json()
        if not data.get("ok"):
            return []
        updates = data.get("result", [])

        if updates:
            for u in updates:
                msg = u.get("message") or u.get("edited_message") or {}
                chat = msg.get("chat", {})

            self._offset = updates[-1]["update_id"] + 1

        return updates
