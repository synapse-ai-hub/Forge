"""Help command."""

from __future__ import annotations



class HelpCommandsMixin:
    """``/ayuda``."""

    async def _cmd_ayuda(self, chat_id: int) -> None:
        """Answer ``/ayuda``: list the available commands.

        Args:
            chat_id: Telegram chat id.
        """
        help_text = (
            "Comandos:\n"
            "/sesiones - Listar sesiones\n"
            "/usar - Cambiar a una sesión\n"
            "/cancelar - Cancelar comando en espera\n"
            "/nueva - Crear chat nuevo\n"
            "/actual - Mostrar sesión actual\n"
            "/contexto - Ver uso de ventana de contexto\n"
            "/borrar - Borrar un chat\n"
            "/detener - Detener tarea en curso\n"
            "/proveedor - Cambiar proveedor\n"
            "/modelo - Cambiar modelo\n"
            "/uso - Ver uso por proveedor/modelo\n"
            "/facturacion - Ver/configurar límites de gasto\n"
            "/skills - Ver skills (dev)\n"
            "/tools - Ver tools (dev)\n"
            "/agentes - Ver agentes (dev)\n"
            "/crear - Crear skill o colección RAG (dev)\n"
            "/archivo - Enviar un archivo por path\n"
            "/agenda - Ver tareas programadas\n"
            "/agendar - Crear una tarea programada\n"
            "/horario - Editar horario de una tarea\n"
            "/eliminar_tarea - Eliminar una tarea programada\n"
            "/ayuda - Mostrar ayuda"
        )
        await self.send_message(chat_id, help_text)
