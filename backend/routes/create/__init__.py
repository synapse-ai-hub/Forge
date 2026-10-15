"""Router para endpoints de creación (tools, skills, agents, workflows, RAG).

Endpoints:
- ``POST /api/create/skill`` — Streaming SSE para crear skills, exacto ChatInterface.
- ``POST /api/create/tool`` — Streaming SSE para crear tools externas, mismo contrato.
- ``POST /api/create/agent`` — Streaming SSE para crear agentes especializados.
- ``POST /api/create/workflow`` — Streaming SSE para crear workflows, mismo contrato.

Este paquete re-exporta ``router``, los request models y las funciones
para compatibilidad hacia atrás con ``from backend.routes.create import ...``.
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
