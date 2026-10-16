"""Listing commands for skills, tools and agents."""

from __future__ import annotations



class ListingCommandsMixin:
    """``/skills``, ``/tools`` and ``/agentes``."""

    async def _cmd_skills(self, chat_id: int) -> None:
        if not self.is_dev:
            await self.send_message(chat_id, "Disponible solo en modo dev.")
            return
        from backend.agent.utils.agent_helpers import get_skills_list
        skills = get_skills_list()
        if not skills:
            await self.send_message(chat_id, "No hay skills.")
            return
        lines = ["Skills:"]
        for s in skills:
            lines.append(f"- {s.get('name')}: {s.get('description')}")
        await self.send_message(chat_id, "\n".join(lines))

    async def _cmd_tools(self, chat_id: int) -> None:
        if not self.is_dev:
            await self.send_message(chat_id, "Disponible solo en modo dev.")
            return
        from backend.agent.utils.agent_helpers import get_tools_list
        tools = get_tools_list()
        if not tools:
            await self.send_message(chat_id, "No hay tools.")
            return
        lines = ["Tools:"]
        for t in tools:
            lines.append(f"- {t.get('name')}: {t.get('description')}")
        await self.send_message(chat_id, "\n".join(lines))

    async def _cmd_agentes(self, chat_id: int) -> None:
        if not self.is_dev:
            await self.send_message(chat_id, "Disponible solo en modo dev.")
            return
        from backend.agent.utils.agent_helpers import get_agents_list
        agents = get_agents_list()
        if not agents:
            await self.send_message(chat_id, "No hay agentes.")
            return
        lines = ["Agentes:"]
        for a in agents:
            lines.append(f"- {a.get('name')}: {a.get('description')}")
        await self.send_message(chat_id, "\n".join(lines))
