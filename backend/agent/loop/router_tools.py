"""Fallback tool schema for the router agent."""

from __future__ import annotations



# Tool schema for the router agent (agent_name=None). Fallback only: the
# router's tools are normally resolved from the tools registry via its
# permissions (the floor tools task, search_memory, read, websearch and
# webfetch without a stored selection; exactly the ones the selection lists
# with it; rag on the internal collections is always added).
_ROUTER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "task",
            "description": "Delegate work to a sub-agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "description": "Name of the sub-agent to delegate to."
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Detailed task description for the sub-agent (user message)."
                    }
                },
                "required": ["agent_name", "prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": (
                "Busca en conversaciones anteriores del usuario (memoria de "
                "largo plazo). Úsala cuando el usuario pregunte por "
                "conversaciones previas o mencione información que no está "
                "en la sesión actual."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Consulta en lenguaje natural sobre conversaciones pasadas."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Cantidad máxima de resultados (default 5)."
                    }
                },
                "required": ["query"]
            }
        }
    }
]

"""Tool schema list for the router agent (``task`` + ``search_memory``)."""
