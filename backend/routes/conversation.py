"""Router to export a conversation to Markdown.

Endpoints:
- ``POST /api/conversation/export`` — Receives the list of messages (in the
  same format the frontend uses) and returns the generated Markdown,
  replicating the logic of ``frontend/src/utils/conversationExport.ts``
  (reasoning, tool calls with arguments and results, text, attachments and
  sub-agents).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Ensure project root for absolute imports
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.utils.contract import (
    make_error_response,
    make_success_response,
    validate_response,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class ContentBlock(BaseModel):
    """A single content block of a message (mirrors the frontend type)."""

    type: str
    content: str | None = None
    name: str | None = None
    args: dict[str, Any] | None = None
    result: Any = None


class Message(BaseModel):
    """A conversation message (mirrors the frontend ``Message`` type)."""

    id: str
    type: str
    content: str = ""
    reasoning: str | None = None
    blocks: list[ContentBlock] | None = None
    files: list[dict[str, Any]] | None = None
    toolCalls: list[dict[str, Any]] | None = None
    toolResults: list[dict[str, Any]] | None = None
    subagentEvents: dict[str, Any] | None = None


class ExportRequest(BaseModel):
    """Request body for the conversation export endpoint."""

    messages: list[Message]
    title: str = "Conversación"


# ---------------------------------------------------------------------------
# Markdown rendering helpers (mirror of conversationExport.ts)
# ---------------------------------------------------------------------------
def _escape_code_block(text: str) -> str:
    """Escape triple backticks so they are safe inside a fenced code block."""
    return text.replace("```", "\\`\\`\\`")


def _render_block(block: ContentBlock, index: int) -> str:
    """Render a single content block to Markdown."""
    if block.type == "reasoning":
        content = (block.content or "").strip()
        if not content:
            return ""
        return (
            f"### Razonamiento {index}\n\n"
            f"<details>\n<summary>Ver razonamiento</summary>\n\n"
            f"{content}\n\n</details>\n"
        )
    if block.type == "text":
        content = block.content or ""
        if not content:
            return ""
        return f"{content}\n"
    if block.type == "tool":
        name = block.name or "unknown"
        args = block.args or {}
        result = block.result
        args_str = (
            json.dumps(args, ensure_ascii=False, indent=2)
            if args
            else "(sin parámetros)"
        )
        out = f"### Llamada a tool: `{name}` {index}\n\n"
        out += f"**Parámetros:**\n\n```json\n{_escape_code_block(args_str)}\n```\n\n"
        if result is not None:
            result_str = (
                result
                if isinstance(result, str)
                else json.dumps(result, ensure_ascii=False, indent=2)
            )
            out += f"**Resultado:**\n\n```\n{_escape_code_block(result_str)}\n```\n\n"
        return out
    return ""


def _render_subagent_events(events: dict[str, Any] | None) -> str:
    """Render sub-agent events (for the ``task`` tool) to Markdown."""
    if not events:
        return ""
    out = ""
    for child_id, event in events.items():
        agent_name = event.get("agent_name", "unknown")
        out += f"\n#### Sub-agente: {agent_name} (id: {child_id[:8]})\n\n"
        if event.get("content"):
            out += f"**Respuesta:** {event['content']}\n\n"
        tool_calls = event.get("tool_calls") or []
        if tool_calls:
            out += "**Herramientas del sub-agente:**\n\n"
            for tc in tool_calls:
                out += f"- `{tc.get('name')}`: {json.dumps(tc.get('args', {}), ensure_ascii=False)}\n"
            out += "\n"
        tool_results = event.get("tool_results") or []
        if tool_results:
            out += "**Resultados:**\n\n"
            for tr in tool_results:
                result = tr.get("result")
                result_str = (
                    result
                    if isinstance(result, str)
                    else json.dumps(result, ensure_ascii=False, indent=2)
                )
                out += f"- `{tr.get('tool_name')}`:\n```\n{_escape_code_block(result_str)}\n```\n"
            out += "\n"
        steps = event.get("steps") or []
        if steps:
            out += "**Pasos (orden exacto):**\n\n"
            for i, step in enumerate(steps):
                kind = step.get("kind")
                if kind == "reasoning":
                    out += f"{i + 1}. **Razonamiento:** {step.get('content', '')}\n"
                elif kind == "text":
                    out += f"{i + 1}. **Texto:** {step.get('content', '')}\n"
                elif kind == "tool":
                    out += f"{i + 1}. **Tool `{step.get('name')}`:** {json.dumps(step.get('args', {}), ensure_ascii=False)}\n"
                    if step.get("result") is not None:
                        result = step["result"]
                        result_str = (
                            result
                            if isinstance(result, str)
                            else json.dumps(result, ensure_ascii=False, indent=2)
                        )
                        out += f"   - Resultado: ```\n{_escape_code_block(result_str)}\n```\n"
            out += "\n"
    return out


def _render_message(msg: Message, index: int) -> str:
    """Render a single message to Markdown."""
    role = "Usuario" if msg.type == "user" else "Asistente"
    out = f"---\n\n## Mensaje {index + 1}: {role}\n\n"

    # File attachments (user messages)
    if msg.type == "user" and msg.files:
        out += "**Archivos adjuntos:**\n\n"
        for f in msg.files:
            size = f.get("size")
            size_str = f" ({size / 1024:.0f} KB)" if size else ""
            out += f"- {f.get('name', '')}{size_str}\n"
        out += "\n"

    # Modern blocks format
    if msg.blocks:
        for i, block in enumerate(msg.blocks):
            out += _render_block(block, i)
    elif msg.content:
        out += msg.content + "\n"

    # Legacy toolCalls / toolResults format
    if msg.type == "assistant" and msg.toolCalls:
        for i, tc in enumerate(msg.toolCalls):
            result = msg.toolResults[i] if msg.toolResults and i < len(msg.toolResults) else None
            out += f"### Llamada a tool: `{tc.get('tool', 'unknown')}` {i}\n\n"
            params = tc.get("parameters", {})
            args_str = (
                json.dumps(params, ensure_ascii=False, indent=2)
                if params
                else "(sin parámetros)"
            )
            out += f"**Parámetros:**\n\n```json\n{_escape_code_block(args_str)}\n```\n\n"
            if result:
                result_val = result.get("result")
                result_str = (
                    result_val
                    if isinstance(result_val, str)
                    else json.dumps(result_val, ensure_ascii=False, indent=2)
                )
                out += f"**Resultado:**\n\n```\n{_escape_code_block(result_str)}\n```\n\n"

    # Sub-agent events
    if msg.type == "assistant" and msg.subagentEvents:
        out += _render_subagent_events(msg.subagentEvents)

    # Reasoning (legacy field)
    if msg.type == "assistant" and msg.reasoning:
        out += (
            f"### Razonamiento\n\n<details>\n<summary>Ver razonamiento</summary>\n\n"
            f"{msg.reasoning}\n\n</details>\n"
        )

    return out


def conversation_to_markdown(messages: list[Message], title: str = "Conversación") -> str:
    """Convert a list of messages to a Markdown string (mirror of the frontend)."""
    now = datetime.now().isoformat()
    md = f"# {title}\n\n"
    md += f"> Exportado el: {now}\n\n"
    for i, msg in enumerate(messages):
        md += _render_message(msg, i)
    return md


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
@router.post("/conversation/export")
async def export_conversation(req: ExportRequest) -> dict:
    """Generate Markdown from a list of conversation messages.

    Args:
        req: The request containing the messages and an optional title.

    Returns:
        A dict following the unified response contract with the generated
        ``markdown`` in ``data``.

    Raises:
        HTTPException: If the Markdown generation fails.
    """
    try:
        md = conversation_to_markdown(req.messages, req.title)
        return validate_response(
            make_success_response(
                message="Conversación exportada.",
                data={"markdown": md},
            )
        )
    except Exception as exc:
        logger.error("Error exporting conversation: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=make_error_response(message="Error al exportar la conversación."),
        )