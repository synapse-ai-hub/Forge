"""Scheduler (agenda) commands: Telegram as remote control for scheduled tasks."""

from __future__ import annotations



class SchedulerCommandsMixin:
    """``/agenda``, ``/agendar``, ``/horario`` and ``/eliminar_tarea``."""

    _DAY_LETTERS = ["D", "L", "M", "X", "J", "V", "S"]

    """Weekday letters indexed JS-style (0=Sunday .. 6=Saturday), same as the UI."""

    def _format_days(self, days: list[int]) -> str:
        """Format a weekday list as human-readable letters (e.g. ``L X V``).

        Args:
            days: Weekday list, 0=Sunday .. 6=Saturday.

        Returns:
            A compact label like ``Todos`` or ``L X V``.
        """
        if sorted(set(days)) == [0, 1, 2, 3, 4, 5, 6]:
            return "Todos"
        return " ".join(self._DAY_LETTERS[d] for d in sorted(days))

    def _parse_days(self, text: str) -> list[int] | None:
        """Parse a user-provided day selection into a weekday list.

        Accepts ``todos`` / ``diario``, single letters (``L M X J V S D``)
        and numbers (``0``=Sunday .. ``6``=Saturday), in any mix.

        Args:
            text: The raw user reply.

        Returns:
            The sorted weekday list, or ``None`` if nothing valid was found.
        """
        t = text.strip().lower()
        if not t:
            return None
        if t in ("todos", "todo", "diario", "todos los dias", "todos los días"):
            return [0, 1, 2, 3, 4, 5, 6]
        days: set[int] = set()
        for token in t.replace(",", " ").split():
            if token in ("l", "lun", "lunes"):
                days.add(1)
            elif token in ("m", "mar", "martes"):
                days.add(2)
            elif token in ("x", "mi", "miercoles", "miércoles"):
                days.add(3)
            elif token in ("j", "jue", "jueves"):
                days.add(4)
            elif token in ("v", "vie", "viernes"):
                days.add(5)
            elif token in ("s", "sab", "sábado", "sabado"):
                days.add(6)
            elif token in ("d", "dom", "domingo"):
                days.add(0)
            elif token.isdigit() and 0 <= int(token) <= 6:
                days.add(int(token))
        return sorted(days) if days else None

    async def _cmd_agenda(self, chat_id: int) -> None:
        """Handle ``/agenda``: list every scheduled task.

        Args:
            chat_id: Telegram chat id.
        """
        from backend.agent.utils import scheduler_helpers as scheduler_db

        tasks = scheduler_db.list_tasks()
        if not tasks:
            await self.send_message(chat_id, "No hay tareas programadas. Usá /agendar para crear una.")
            return
        lines = ["Tareas programadas:"]
        for i, task in enumerate(tasks, start=1):
            state = "" if task["enabled"] else " (pausada)"
            lines.append(
                f"{i}. [{self._format_days(task['days'])}] {task['time']} — "
                f"{task['prompt'][:60]}{state}"
            )
        lines.append("")
        lines.append("/agendar crear · /horario editar · /eliminar_tarea eliminar")
        await self.send_message(chat_id, "\n".join(lines))

    async def _cmd_agendar(self, chat_id: int, arg: str) -> None:
        """Handle ``/agendar``: guided creation of a scheduled task.

        With an argument it uses it as the prompt and asks for the time;
        without one it asks for the prompt first (or /cancelar).

        Args:
            chat_id: The Telegram chat id.
            arg: Optional inline prompt for the task.
        """
        prompt = arg.strip()
        if prompt:
            self._mode_data[chat_id] = {"agenda": {"prompt": prompt}}
            self._awaiting[chat_id] = "agenda_time"
            await self.send_message(chat_id, "¿A qué hora? (HH:MM, o 'cancelar')")
            return
        self._mode_data[chat_id] = {"agenda": {}}
        self._awaiting[chat_id] = "agenda_prompt"
        await self.send_message(
            chat_id, "¿Qué tiene que hacer el agente? (o 'cancelar')"
        )

    async def _process_agenda_awaiting(self, chat_id: int, cmd: str, text: str) -> None:
        """Process a reply of the guided ``/agendar`` flow.

        Args:
            chat_id: The Telegram chat id.
            cmd: The awaiting key (``agenda_prompt``, ``agenda_time`` or
                ``agenda_days``).
            text: The raw user reply.
        """
        import re

        from backend.agent.utils import scheduler_helpers as scheduler_db

        data = self._mode_data.get(chat_id, {}).get("agenda")
        if data is None:
            self._awaiting.pop(chat_id, None)
            return

        if cmd == "agenda_prompt":
            prompt = text.strip()
            if not prompt:
                await self.send_message(chat_id, "La descripción no puede estar vacía.")
                return
            data["prompt"] = prompt
            self._awaiting[chat_id] = "agenda_time"
            await self.send_message(chat_id, "¿A qué hora? (HH:MM, o 'cancelar')")
        elif cmd == "agenda_time":
            time_str = text.strip()
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", time_str):
                await self.send_message(chat_id, "Horario inválido. Usá formato HH:MM (ej.: 09:30).")
                return
            data["time"] = time_str
            self._awaiting[chat_id] = "agenda_days"
            await self.send_message(
                chat_id,
                "¿Qué días? (L M X J V S D, números 0-6 donde 0=domingo, "
                "o 'todos' — ej.: L X V)",
            )
        elif cmd == "agenda_days":
            days = self._parse_days(text)
            if not days:
                await self.send_message(
                    chat_id, "No entendí los días. Ejemplos: 'todos', 'L X V', '0 2 4'."
                )
                return
            result = scheduler_db.add_task(
                name=scheduler_db._slugify(data.get("prompt", "")),
                prompt=data.get("prompt", ""),
                time_str=data.get("time", ""),
                days=days,
            )
            self._awaiting.pop(chat_id, None)
            self._mode_data.pop(chat_id, None)
            await self.send_message(chat_id, result["message"])

    async def _cmd_horario(self, chat_id: int, arg: str) -> None:
        """Handle ``/horario``: edit the schedule of a scheduled task.

        Asks which task to edit (by number from ``/agenda``), then the new
        time and the new days.

        Args:
            chat_id: The Telegram chat id.
            arg: Optional inline task number.
        """
        from backend.agent.utils import scheduler_helpers as scheduler_db

        tasks = scheduler_db.list_tasks()
        if not tasks:
            await self.send_message(chat_id, "No hay tareas programadas. Usá /agendar para crear una.")
            return
        num_text = arg.strip()
        if num_text:
            await self._horario_num(chat_id, num_text)
            return
        listing = "\n".join(
            f"{i}. [{self._format_days(t['days'])}] {t['time']} — {t['prompt'][:50]}"
            for i, t in enumerate(tasks, start=1)
        )
        self._mode_data[chat_id] = {}
        self._awaiting[chat_id] = "horario_num"
        await self.send_message(
            chat_id, f"¿Qué tarea querés editar?\n{listing}\n(número o 'cancelar')"
        )

    async def _horario_num(self, chat_id: int, text: str) -> None:
        """Resolve the selected task number of the ``/horario`` flow.

        Args:
            chat_id: Telegram chat id.
            text: Number the user answered.
        """
        from backend.agent.utils import scheduler_helpers as scheduler_db

        tasks = scheduler_db.list_tasks()
        try:
            idx = int(text.strip()) - 1
        except ValueError:
            await self.send_message(chat_id, "Número inválido.")
            return
        if idx < 0 or idx >= len(tasks):
            await self.send_message(chat_id, f"Elegí un número entre 1 y {len(tasks)}.")
            return
        task = tasks[idx]
        partial = self._mode_data.setdefault(chat_id, {})
        partial["horario"] = {"task_id": task["id"]}
        self._awaiting[chat_id] = "horario_time"
        await self.send_message(
            chat_id,
            f"Editando: {task['prompt'][:60]}\nNuevo horario (HH:MM, o 'cancelar'):",
        )

    async def _process_horario_awaiting(self, chat_id: int, cmd: str, text: str) -> None:
        """Process a reply of the guided ``/horario`` flow.

        Args:
            chat_id: The Telegram chat id.
            cmd: The awaiting key (``horario_time`` or ``horario_days``).
            text: The raw user reply.
        """
        import re

        from backend.agent.utils import scheduler_helpers as scheduler_db

        data = self._mode_data.get(chat_id, {}).get("horario")
        if data is None:
            self._awaiting.pop(chat_id, None)
            return

        if cmd == "horario_time":
            time_str = text.strip()
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", time_str):
                await self.send_message(chat_id, "Horario inválido. Usá formato HH:MM (ej.: 09:30).")
                return
            data["time"] = time_str
            self._awaiting[chat_id] = "horario_days"
            await self.send_message(
                chat_id,
                "¿Qué días? (L M X J V S D, números 0-6 donde 0=domingo, "
                "o 'todos' — ej.: L X V)",
            )
        elif cmd == "horario_days":
            days = self._parse_days(text)
            if not days:
                await self.send_message(
                    chat_id, "No entendí los días. Ejemplos: 'todos', 'L X V', '0 2 4'."
                )
                return
            result = scheduler_db.update_task(data["task_id"], time_str=data["time"], days=days)  # noqa: E501 — name/prompt/permissions unchanged via Telegram
            self._awaiting.pop(chat_id, None)
            self._mode_data.pop(chat_id, None)
            await self.send_message(chat_id, result["message"])

    async def _cmd_eliminar_tarea(self, chat_id: int, arg: str) -> None:
        """Handle ``/eliminar_tarea``: delete a scheduled task by its number.

        Args:
            chat_id: The Telegram chat id.
            arg: Optional inline task number.
        """
        from backend.agent.utils import scheduler_helpers as scheduler_db

        tasks = scheduler_db.list_tasks()
        if not tasks:
            await self.send_message(chat_id, "No hay tareas programadas.")
            return
        num_text = arg.strip()
        if num_text:
            await self._eliminar_tarea_num(chat_id, num_text)
            return
        listing = "\n".join(
            f"{i}. [{self._format_days(t['days'])}] {t['time']} — {t['prompt'][:50]}"
            for i, t in enumerate(tasks, start=1)
        )
        self._awaiting[chat_id] = "eliminar_tarea_num"
        await self.send_message(
            chat_id, f"¿Qué tarea querés eliminar?\n{listing}\n(número o 'cancelar')"
        )

    async def _eliminar_tarea_num(self, chat_id: int, text: str) -> None:
        """Delete the task selected by number in the ``/eliminar_tarea`` flow.

        Args:
            chat_id: Telegram chat id.
            text: Number the user answered.
        """
        from backend.agent.utils import scheduler_helpers as scheduler_db

        tasks = scheduler_db.list_tasks()
        try:
            idx = int(text.strip()) - 1
        except ValueError:
            await self.send_message(chat_id, "Número inválido.")
            return
        if idx < 0 or idx >= len(tasks):
            await self.send_message(chat_id, f"Elegí un número entre 1 y {len(tasks)}.")
            return
        result = scheduler_db.delete_task(tasks[idx]["id"])
        self._awaiting.pop(chat_id, None)
        await self.send_message(chat_id, result["message"])
