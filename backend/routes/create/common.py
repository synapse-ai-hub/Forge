"""Shared router, request models and helpers of the creation endpoints.

The four creators (skill, tool, agent, workflow) run on the agent loop with a
creator system prompt and a fixed set of native tools. This module holds what
they share: the router, the SSE helper, the request models, the tool
permissions of the creators and the outcome scan that detects the created or
modified item at the end of a turn.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from backend.agent.utils.config_dir import get_agents_dir, get_skills_dir, get_tools_dir, get_workflows_dir
from backend.agent.utils.contract import zero_usage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/create", tags=["create"])
"""Shared router where the creation endpoints register their routes."""

_AGENT_TOOLS_PERMS: dict[str, str] = {
    "read": "allow",
    "write": "allow",
    "edit": "allow",
    "shell": "allow",
    "list_dir": "allow",
    "glob": "allow",
    "grep": "allow",
    "websearch": "allow",
    "webfetch": "allow",
    "query_model_capabilities": "allow",
    "skill": "allow",
}
"""Native tools enabled for the creators (read/explore + web + file edition).

The ``skill`` tool is enabled so creators can load their internal skills
(allowed list arrives later via ``skill_permissions``); without explicit
skill permissions every ``skill()`` call is denied by name.
"""

_TOOLS_DIR = get_tools_dir()
_SKILLS_DIR = get_skills_dir()
_AGENTS_DIR = get_agents_dir()
_WORKFLOWS_DIR = get_workflows_dir()


class CreateToolRequest(BaseModel):
    """Request to create or modify an external tool."""

    descripcion: str
    name: str | None = None
    creator_id: str | None = None
    parametros: list[dict[str, Any]] | None = None
    datos: list[dict[str, Any]] | None = None
    model: str | None = None
    provider: str | None = None


class CreateAgentRequest(BaseModel):
    """Request to create or modify a specialized agent."""

    descripcion: str
    name: str | None = None
    creator_id: str | None = None
    agentes: list[str] | None = None
    tools: list[str] | None = None
    skills: list[str] | None = None
    rag: list[str] | None = None
    tool_args: dict[str, dict[str, Any]] | None = None
    model: str | None = None
    provider: str | None = None


class VerifyCreatorRequest(BaseModel):
    """Request to verify a creator conversation on demand."""

    creator_id: str


def _sse(event: dict[str, Any]) -> str:
    """Serialize one SSE event.

    Args:
        event: The event dict with ``type`` and ``content``.

    Returns:
        The ``data: {...}\\n\\n`` line.
    """
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def error_response(message: str, status_code: int = 400) -> JSONResponse:
    """Build a JSON error response for a rejected creator request.

    Args:
        message: Human-readable error message.
        status_code: HTTP status code.

    Returns:
        A ``JSONResponse`` with the error contract.
    """
    return JSONResponse(
        status_code=status_code,
        content={"status": "error", "message": message, "data": None, "usage": None},
    )


def prompt_error_stream() -> StreamingResponse:
    """Stream a user-friendly error when a creator prompt cannot be loaded.

    The frontend opens an SSE stream for creator turns, so a JSON error
    would show nothing. This yields the same message the chat shows when
    the loop fails, as an ``error`` event plus ``[DONE]``.

    Returns:
        A ``StreamingResponse`` with the error event and ``[DONE]``.
    """
    async def _events():
        yield _sse({
            "type": "error",
            "content": "En este momento no se puede ejecutar la solicitud. Por favor, intentá más tarde.",
        })
        yield "data: [DONE]\n\n"

    return StreamingResponse(_events(), media_type="text/event-stream")


def _touched(path: Path, since_ts: float) -> bool:
    """Check whether a path exists and was modified after a timestamp.

    Args:
        path: File or directory to check.
        since_ts: Reference timestamp (seconds since the epoch).

    Returns:
        True when the path exists and its mtime is not older than the reference.
    """
    try:
        return path.exists() and path.stat().st_mtime >= since_ts - 1.0
    except OSError:
        return False


def find_created_item(kind: str, name: str | None, since_ts: float) -> dict | None:
    """Detect the item a creator turn created or modified.

    Looks for the expected path first (by name) and falls back to the newest
    item of the kind touched during the turn. Only items modified after
    ``since_ts`` count: a turn that only asks questions emits no outcome.

    Args:
        kind: ``"tool"``, ``"skill"``, ``"agent"`` or ``"workflow"``.
        name: Item name suggested by the user (may be None).
        since_ts: Turn start timestamp (seconds since the epoch).

    Returns:
        ``{"item_name", "path"}`` when something was touched this turn,
        otherwise None. Never raises.
    """
    try:
        clean = (name or "").strip()
        if kind == "tool":
            if clean:
                candidate = _TOOLS_DIR / f"{clean}.py"
                if _touched(candidate, since_ts):
                    return {"item_name": clean, "path": str(candidate)}
            newest: Path | None = None
            newest_mtime = since_ts - 1.0
            try:
                for entry in _TOOLS_DIR.iterdir():
                    if not entry.is_file() or entry.suffix != ".py":
                        continue
                    mtime = entry.stat().st_mtime
                    if mtime >= since_ts - 1.0 and mtime > newest_mtime:
                        newest, newest_mtime = entry, mtime
            except OSError:
                pass
            if newest is not None:
                return {"item_name": newest.stem, "path": str(newest)}
            return None
        if kind == "skill":
            if clean:
                candidate = _SKILLS_DIR / clean / "SKILL.md"
                if _touched(candidate, since_ts):
                    return {"item_name": clean, "path": str(candidate.parent)}
            newest_dir: Path | None = None
            newest_mtime = since_ts - 1.0
            try:
                for entry in _SKILLS_DIR.iterdir():
                    if not entry.is_dir():
                        continue
                    skill_md = entry / "SKILL.md"
                    if not skill_md.is_file():
                        continue
                    mtime = skill_md.stat().st_mtime
                    if mtime >= since_ts - 1.0 and mtime > newest_mtime:
                        newest_dir, newest_mtime = entry, mtime
            except OSError:
                pass
            if newest_dir is not None:
                return {"item_name": newest_dir.name, "path": str(newest_dir)}
            return None
        if kind == "agent":
            if clean:
                candidate = _AGENTS_DIR / f"{clean}.md"
                if _touched(candidate, since_ts):
                    return {"item_name": clean, "path": str(candidate)}
            newest_md: Path | None = None
            newest_mtime = since_ts - 1.0
            try:
                for entry in _AGENTS_DIR.iterdir():
                    if not entry.is_file() or entry.suffix != ".md":
                        continue
                    mtime = entry.stat().st_mtime
                    if mtime >= since_ts - 1.0 and mtime > newest_mtime:
                        newest_md, newest_mtime = entry, mtime
            except OSError:
                pass
            if newest_md is not None:
                return {"item_name": newest_md.stem, "path": str(newest_md)}
            return None
        if kind == "workflow":
            from backend.agent.utils.workflows_helpers import _workflow_file_path

            if clean:
                try:
                    candidate = _workflow_file_path(clean)
                except ValueError:
                    candidate = None
                if candidate is not None and _touched(candidate, since_ts):
                    return {"item_name": clean, "path": str(candidate)}
            newest_yaml: Path | None = None
            newest_mtime = since_ts - 1.0
            try:
                for entry in _WORKFLOWS_DIR.iterdir():
                    if not entry.is_file() or entry.suffix != ".yaml":
                        continue
                    mtime = entry.stat().st_mtime
                    if mtime >= since_ts - 1.0 and mtime > newest_mtime:
                        newest_yaml, newest_mtime = entry, mtime
            except OSError:
                pass
            if newest_yaml is not None:
                return {"item_name": newest_yaml.stem, "path": str(newest_yaml)}
            return None
        return None
    except Exception as exc:
        logger.warning("Outcome scan failed for %s '%s': %s", kind, name, exc)
        return None


def current_timestamp() -> float:
    """Return the current time in seconds since the epoch.

    Args:
        None.

    Returns:
        The current timestamp (used as the outcome scan reference).
    """
    return time.time()


_RESULT_EVENT = {
    "tool": "tool_result_final",
    "skill": "skill_result_final",
    "agent": "agent_result_final",
    "workflow": "workflow_result_final",
}
"""Terminal event type of each creator (kept for the UI and Telegram)."""

_RESULT_ITEM_KEY = {
    "tool": "tool",
    "skill": "skill",
    "agent": "agent",
    "workflow": "workflow",
}
"""``data`` key holding the item name in each terminal event."""

_RESULT_PATH_KEY = {
    "tool": "tool_path",
    "skill": "skill_path",
    "agent": "agent_path",
    "workflow": "workflow_path",
}
"""``data`` key holding the item path in each terminal event."""


async def stream_creator_turn(
    kind: str,
    creator_id: str,
    user_message: str,
    system_prompt: str,
    session_manager,
    user_setup: dict | None = None,
    parameters: dict | None = None,
    file_contents: list[tuple[str, str]] | None = None,
):
    """Run one creator turn on the agent loop and stream it as SSE.

    The turn runs exactly like a chat turn (same loop, same events) with a
    creator system prompt and the creator tool permissions. When the turn
    ends, the outcome scan looks for the created or modified item: only when
    something was touched during the turn a terminal
    ``{kind}_result_final`` event is appended (a turn that only asks
    questions emits none).

    Args:
        kind: ``"tool"``, ``"skill"``, ``"agent"`` or ``"workflow"``.
        creator_id: Creator conversation id (persists in ``creators``).
        user_message: Raw user message (with the setup form prepended on
            the first turn).
        system_prompt: Rendered creator system prompt.
        session_manager: Creator session manager of this kind.
        user_setup: Setup form stored as JSON on the first user row.
        parameters: Optional ``{"model", "provider"}`` override chosen by
            the user for this turn.
        file_contents: Optional ``(filename, text)`` attachments.

    Yields:
        Serialized SSE lines (``data: {...}\\n\\n``) plus ``data: [DONE]``.
    """
    from backend.agent.loop.agent_loop import AgentLoop
    from backend.instances import agent

    start_ts = current_timestamp()
    item_name = (user_setup or {}).get("name")
    existed_before = _exact_path(kind, item_name).exists() if item_name else False
    try:
        tools = list(agent.tools.tools_registry(_AGENT_TOOLS_PERMS))
    except Exception as exc:
        logger.exception("Error obteniendo tools del creador: %s", exc)
        yield _sse({"type": "error", "content": "No se pudieron cargar las herramientas del creador."})
        yield "data: [DONE]\n\n"
        return

    loop = AgentLoop(agent, session_manager)
    async for event in loop.run(
        session_id=creator_id,
        user_message=user_message,
        file_contents=file_contents,
        system_prompt=system_prompt,
        tool_permissions=dict(_AGENT_TOOLS_PERMS),
        parameters=parameters,
        agent_name=f"creator_{kind}",
        is_creator=True,
        user_setup=user_setup,
    ):
        yield event

    found = find_created_item(kind, item_name, start_ts)
    if found is not None:
        item = found["item_name"]
        action = "modificada" if existed_before else "creada"
        label = {"tool": "Tool", "skill": "Skill", "agent": "Agente", "workflow": "Workflow"}[kind]
        message = f"{label} '{item}' {action} exitosamente."
        try:
            from backend.agent.utils.creators import add_row

            add_row(
                creator_id, kind, "result", status="success", message=message,
                action="iterate" if existed_before else "create", item_name=item,
            )
        except Exception as exc:
            logger.warning("No se pudo guardar el resultado del creador: %s", exc)
        yield _sse({
            "type": _RESULT_EVENT[kind],
            "content": {
                "status": "success",
                "message": message,
                "data": {
                    "exist": "Sí",
                    _RESULT_ITEM_KEY[kind]: item,
                    _RESULT_PATH_KEY[kind]: found["path"],
                },
            },
        })
    yield "data: [DONE]\n\n"


def _exact_path(kind: str, item_name: str | None) -> Path:
    """Return the expected path of a creator item by name.

    Args:
        kind: Creator kind.
        item_name: Item name (may be None or blank).

    Returns:
        The expected path, or an empty path when the name is unusable.
    """
    clean = (item_name or "").strip()
    if not clean:
        return Path("")
    if kind == "tool":
        return _TOOLS_DIR / f"{clean}.py"
    if kind == "skill":
        return _SKILLS_DIR / clean / "SKILL.md"
    if kind == "agent":
        return _AGENTS_DIR / f"{clean}.md"
    if kind == "workflow":
        from backend.agent.utils.workflows_helpers import _workflow_file_path

        try:
            return _workflow_file_path(clean)
        except ValueError:
            return Path("")
    return Path("")


async def verify_creator_conversation(kind: str, session_manager: Any,
                                     creator_id: str | None) -> JSONResponse:
    """Verify a creator conversation on demand (Verificar button).

    Evaluates the full context (request, history, created items) with the
    decision model when enabled, otherwise with an LLM with JSON output.
    The verdict is persisted as a ``"decisor"`` row in ``creators`` and,
    when it is done, the step frontier of the conversation is deleted.

    Args:
        kind: Creator kind (only used for the error messages).
        session_manager: ``CreatorSessionManager`` of the kind.
        creator_id: Creator conversation id.

    Returns:
        A ``JSONResponse`` with ``{"done", "reason"}``.
    """
    from backend.agent.utils.creators import is_valid_id
    from backend.agent.utils.decision import verify_creator

    if not creator_id or not is_valid_id(creator_id):
        return error_response("Falta el identificador de la conversación.")
    if not session_manager.has_rows(creator_id):
        return error_response("La conversación no existe.")
    try:
        result = await verify_creator(session_manager, creator_id)
    except Exception as exc:
        logger.exception("Error verificando el creador de %s: %s", kind, exc)
        return error_response("No se pudo verificar la conversación.", status_code=500)
    return JSONResponse(status_code=200, content={
        "status": "success",
        "message": result.get("reason") or "",
        "data": {"done": bool(result.get("done"))},
        "usage": zero_usage(),
    })
