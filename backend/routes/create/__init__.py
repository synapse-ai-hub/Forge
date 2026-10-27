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
    CreateAgentRequest,
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
from backend.routes.create.agent import post_create_agent_stream
from backend.routes.create.skill import post_create_skill_stream
from backend.routes.create.tool import post_create_tool_stream
from backend.routes.create.workflow import CreateWorkflowRequest, create_scheduled_task, post_create_workflow_stream

__all__ = [
    "router",
    "CreateToolRequest",
    "CreateAgentRequest",
    "CreateWorkflowRequest",
    "post_create_skill_stream",
    "post_create_tool_stream",
    "post_create_agent_stream",
    "post_create_workflow_stream",
    "create_scheduled_task",
]
