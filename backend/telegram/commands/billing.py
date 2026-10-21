"""Usage and billing commands, including the billing-limit conversation."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

class BillingCommandsMixin:
    """``/usage`` and ``/billing``."""

    async def _cmd_usage(self, chat_id: int) -> None:
        """Show usage metrics per provider.

        Args:
            chat_id: Telegram chat id.
        """
        try:
            from backend.agent.utils.spend_handler import get_all_spend
            spend = get_all_spend()
            if not spend:
                await self.send_message(chat_id, "No hay datos de uso aún.")
                return
            lines = ["**Uso por proveedor/modelo:**\n"]
            for s in spend:
                provider = s.get("provider", "?")
                model = s.get("model", "?")
                tokens = s.get("total_tokens", 0)
                cost = s.get("cost_total", 0.0)
                lines.append(f"- {provider}/{model}: {tokens} tokens, ${cost:.4f}")
            total_cost = sum(s.get("cost_total", 0.0) for s in spend)
            total_tokens = sum(s.get("total_tokens", 0) for s in spend)
            lines.append(f"\n**Total:** {total_tokens} tokens, ${total_cost:.4f}")
            await self.send_message(chat_id, "\n".join(lines))
        except Exception as exc:
            logger.warning("Error in /usage: %s", exc)
            await self.send_message(chat_id, "Error al obtener uso.")

    async def _cmd_billing(self, chat_id: int) -> None:
        """Show or configure billing limits.

        Shows current limits and asks what to configure via question-response flow.

        Args:
            chat_id: Telegram chat id.
        """
        try:
            from backend.agent.utils.spend_handler import get_spend_config
            from backend.agent.utils.provider_keys import list_configured

            # Get providers with keys
            configured = list_configured()
            providers_with_keys = [p["provider"] for p in configured if p.get("configured")]

            if not providers_with_keys:
                await self.send_message(chat_id, "No hay providers configurados.")
                return

            # Show current limits
            lines = ["**Configuración de billing:**\n"]
            has_limits = False
            for p in providers_with_keys:
                config = get_spend_config(p, None)
                if config and config.get("limit_amount", 0) > 0:
                    has_limits = True
                    lines.append(f"- {p}: ${config['limit_amount']:.2f}")

            if not has_limits:
                lines.append("Sin límites configurados.")

            lines.append("\n¿Qué querés hacer?")
            lines.append("1. Ver gasto actual")
            lines.append("2. Configurar límite")
            lines.append("3. Cancelar")

            self._awaiting[chat_id] = "billing_menu"
            await self.send_message(chat_id, "\n".join(lines))
        except Exception as exc:
            logger.warning("Error in /billing: %s", exc)
            await self.send_message(chat_id, "Error al obtener billing.")

    async def _process_billing_awaiting(self, chat_id: int, cmd: str, text: str) -> None:
        """Process billing awaiting responses.

        Args:
            chat_id: Telegram chat id.
            cmd: Command that is waiting for an answer.
            text: Text the user answered.
        """
        if text.strip().lower() == "cancelar":
            await self.send_message(chat_id, "Cancelado.")
            return

        if cmd == "billing_menu":
            if text.strip() == "1":
                # Show current spend
                try:
                    from backend.agent.utils.spend_handler import get_all_spend
                    spend = get_all_spend()
                    if not spend:
                        await self.send_message(chat_id, "No hay datos de gasto.")
                        return
                    lines = ["**Gasto actual:**\n"]
                    for s in spend:
                        provider = s.get("provider", "?")
                        model = s.get("model", "?")
                        tokens = s.get("total_tokens", 0)
                        cost = s.get("cost_total", 0.0)
                        lines.append(f"- {provider}/{model}: {tokens} tokens, ${cost:.4f}")
                    total_cost = sum(s.get("cost_total", 0.0) for s in spend)
                    lines.append(f"\n**Total:** ${total_cost:.4f}")
                    await self.send_message(chat_id, "\n".join(lines))
                except Exception as exc:
                    await self.send_message(chat_id, "Error al obtener gasto.")
            elif text.strip() == "2":
                # Ask for provider
                try:
                    from backend.agent.utils.provider_keys import list_configured
                    configured = list_configured()
                    providers = [p["provider"] for p in configured if p.get("configured")]
                    if not providers:
                        await self.send_message(chat_id, "No hay providers configurados.")
                        return
                    lines = ["¿Proveedor? (número o nombre)"]
                    for i, p in enumerate(providers, 1):
                        lines.append(f"{i}. {p}")
                    self._awaiting[chat_id] = "billing_provider"
                    await self.send_message(chat_id, "\n".join(lines))
                except Exception as exc:
                    await self.send_message(chat_id, "Error al obtener providers.")
            else:
                await self.send_message(chat_id, "Opción inválida.")
        elif cmd == "billing_provider":
            # Provider selected, ask for model
            provider = text.strip()
            if provider.isdigit():
                try:
                    from backend.agent.utils.provider_keys import list_configured
                    configured = list_configured()
                    providers = [p["provider"] for p in configured if p.get("configured")]
                    idx = int(provider) - 1
                    provider = providers[idx] if 0 <= idx < len(providers) else ""
                except (ValueError, IndexError):
                    pass
            if not provider:
                await self.send_message(chat_id, "Proveedor inválido.")
                return
            if not provider.isdigit():
                try:
                    from backend.agent.utils.provider_keys import list_configured
                    configured = list_configured()
                    names = [p["provider"] for p in configured if p.get("configured")]
                    match = next((n for n in names if n == provider), None)
                    if match is None:
                        match = next((n for n in names if n.lower() == provider.lower()), None)
                    if match is not None:
                        provider = match
                except Exception:
                    pass
            if not provider:
                await self.send_message(chat_id, "Proveedor inválido.")
                return
            self._awaiting[chat_id] = f"billing_model_{provider}"
            await self.send_message(
                chat_id,
                f"¿Modelo para {provider}? (nombre, '-' para nivel proveedor, o 'cancelar')"
            )
        elif cmd.startswith("billing_model_"):
            provider = cmd.replace("billing_model_", "")
            model = text.strip() if text.strip() != "-" else None
            self._awaiting[chat_id] = f"billing_limit_{provider}_{model or 'all'}"
            await self.send_message(
                chat_id,
                f"Límite en USD para {provider}{('/' + model) if model else ''}? (número o 'cancelar')"
            )
        elif cmd.startswith("billing_limit_"):
            parts = cmd.replace("billing_limit_", "").split("_", 1)
            provider = parts[0]
            model = parts[1] if len(parts) > 1 and parts[1] != "all" else None
            try:
                limit = float(text.strip())
            except ValueError:
                await self.send_message(chat_id, "Monto inválido.")
                return
            await self._apply_billing_limit(chat_id, provider, model, limit)

    async def _apply_billing_limit(self, chat_id: int, provider: str, model: str | None, limit: float) -> None:
        """Apply a billing limit for a provider/model.

        Args:
            chat_id: Telegram chat id.
            provider: Provider the limit applies to.
            model: Model the limit applies to, or None for the whole provider.
            limit: Monthly limit in USD.
        """
        try:
            from backend.agent.utils.spend_handler import set_spend_limit
            success = set_spend_limit(provider.strip(), model, limit)
            if success:
                msg = f"Límite configurado: {provider}"
                if model:
                    msg += f"/{model}"
                msg += f" = ${limit:.2f}"
                await self.send_message(chat_id, msg)
            else:
                await self.send_message(chat_id, "Error al configurar límite.")
        except Exception as exc:
            logger.warning("Error setting billing limit: %s", exc)
            await self.send_message(chat_id, f"Error: {exc}")
