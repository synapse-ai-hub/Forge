"""Provider and model commands."""

from __future__ import annotations

import asyncio
import logging

from backend.event_bus import event_bus

logger = logging.getLogger(__name__)

class ModelCommandsMixin:
    """``/proveedor`` and ``/modelo``."""

    async def _cmd_proveedor(self, chat_id: int, provider: str | None = None) -> None:
        from backend.agent.utils import provider_keys

        valid = ["LOCAL"] + [e["provider"] for e in provider_keys.list_supported()]
        if not provider:
            self._awaiting[chat_id] = "proveedor"
            await self.send_message(chat_id, f"¿Qué proveedor? ({', '.join(valid)}, o 'cancelar')")
            return
        provider = provider.strip()
        exact = next((v for v in valid if v == provider), None)
        if exact is None:
            exact = next((v for v in valid if v.lower() == provider.lower()), None)
        if exact is None:
            await self.send_message(chat_id, f"Proveedor inválido. Usá {', '.join(valid)}.")
            return
        provider = exact
        try:
            from backend.instances import agent
            agent.provider = provider
            self.session_manager.set_config("selected_provider", provider)
        except Exception as exc:
            logger.warning("No se pudo cambiar el proveedor: %s", exc)
            await self.send_message(chat_id, f"No se pudo cambiar el proveedor: {exc}")
            return
        await self.send_message(chat_id, f"Proveedor cambiado a {provider}.")

    async def _cmd_modelo(self, chat_id: int, model: str | None = None) -> None:
        from backend.agent.utils.model_resolver import get_ollama_models
        from backend.agent.utils import model_catalog
        try:
            from backend.instances import agent
            provider = (agent.provider or "LOCAL").strip()
        except Exception:
            provider = "LOCAL"
        if provider == 'LOCAL':
            models = get_ollama_models()
        else:
            models = model_catalog.get_models(provider)
        if not models:
            await self.send_message(chat_id, "No hay modelos disponibles.")
            return
        if not model:
            self._awaiting[chat_id] = "modelo"
            lines = ["¿Qué modelo? (respondé con el número o 'cancelar')"]
            for i, m in enumerate(models, 1):
                lines.append(f"{i}. {m}")
            await self.send_message(chat_id, "\n".join(lines))
            return
        try:
            idx = int(model) - 1
            selected = models[idx] if 0 <= idx < len(models) else None
        except (ValueError, TypeError):
            selected = model if model in models else None
        if not selected:
            await self.send_message(chat_id, f"No encontré el modelo '{model}'.")
            return
        try:
            from backend.instances import agent
            agent._resolved_model = selected
            self.session_manager.set_config("selected_model", selected)
            # Persist the model's context window at the same moment (same
            # helper used by the web UI model selection).
            from backend.routes.config import _detect_and_persist_context_window
            provider = (agent.provider or "LOCAL").strip()
            await asyncio.to_thread(_detect_and_persist_context_window, selected, provider)
        except Exception as exc:
            logger.warning("No se pudo cambiar el modelo: %s", exc)
            await self.send_message(chat_id, f"No se pudo cambiar el modelo: {exc}")
            return
        # Broadcast the model change so the frontend refreshes (Telegram is
        # bidirectional: any persistence path must push the update).
        try:
            await event_bus.emit({
                "type": "model_changed",
                "content": {"model": selected, "provider": provider},
            })
        except Exception as exc:
            logger.warning("No se pudo emitir model_changed: %s", exc)
        await self.send_message(chat_id, f"Modelo cambiado a {selected}.")
