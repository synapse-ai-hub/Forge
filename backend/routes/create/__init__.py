"""Router of the creation endpoints (tools, skills, agents, workflows, RAG).

Endpoints:
- ``POST /api/create/skill``: SSE streaming to create skills, same contract as the chat.
- ``POST /api/create/tool``: SSE streaming to create external tools, same contract.
- ``POST /api/create/agent``: SSE streaming to create specialized agents.
- ``POST /api/create/workflow``: SSE streaming to create workflows, same contract.
- ``GET /api/create/history`` and ``/history/{creator_id}``: conversations of the creators, to list and reopen them.

This package re-exports ``router``, the request models and the functions
for backward compatibility with ``from backend.routes.create import ...``.
"""

from backend.routes.create.common import (
    _AGENT_TOOLS_PERMS,
    _FRIENDLY_ERROR,
    _FRIENDLY_ERROR_AGENT,
    _FRIENDLY_ERROR_TOOL,
    CreateAgentRequest,
    CreateSkillRequest,
    CreateToolRequest,
    router,
)

# Importar los módulos para registrar las rutas en el router compartido.
# (El import tiene side-effect: los decoradores @router.post registran endpoints.)
from backend.routes.create import agent as agent  # noqa: F401
from backend.routes.create import history as history  # noqa: F401
from backend.routes.create import skill as skill  # noqa: F401
from backend.routes.create import tool as tool  # noqa: F401
from backend.routes.create import workflow as workflow  # noqa: F401
from backend.routes.create.agent import _listar_agentes_locales, post_create_agent_stream
from backend.routes.create.skill import post_create_skill_stream
from backend.routes.create.tool import _evaluar_si_existe_tool_inline, post_create_tool_stream
from backend.routes.create.workflow import CreateWorkflowRequest, post_create_workflow_stream

__all__ = [
    "router",
    "CreateSkillRequest",
    "CreateToolRequest",
    "CreateAgentRequest",
    "CreateWorkflowRequest",
    "post_create_skill_stream",
    "post_create_tool_stream",
    "post_create_agent_stream",
    "post_create_workflow_stream",
    "_evaluar_si_existe_tool_inline",
    "_listar_agentes_locales",
]
