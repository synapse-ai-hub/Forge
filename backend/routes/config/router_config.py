"""Router permissions panel: read and save what the router may use.

The sidebar "Router" tab shows the same permission cards as the creators
(agents, tools, skills and RAG collections) with a dropdown to add or
remove. What is picked is stored in the single row of the
``router_config`` table and the agent loop reads it on every run. There
is no file fallback: without a row the floor defaults apply.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.agent.loop.helpers import (
    load_router_selection_with_source,
    save_router_selection,
)
from backend.agent.utils.error_logger import log_error

router = APIRouter()

_SELECTION_KEYS = ("agentes", "tools", "skills", "rag")


class RouterSelection(BaseModel):
    """Pick lists of the sidebar "Router" tab.

    All four lists are required: a partial body is rejected with 422
    instead of silently wiping the missing dimensions.
    """

    agentes: list[str]
    tools: list[str]
    skills: list[str]
    rag: list[str]


@router.get("/router")
async def get_router() -> JSONResponse:
    """Return the current router selection and where it comes from.

    Returns:
        JSON response with ``selection`` (``agentes``, ``tools``,
        ``skills`` and ``rag`` lists) and ``source`` (``"db"`` when a
        row exists, ``"floor"`` when nothing is stored).
    """
    try:
        selection, source = load_router_selection_with_source()
        if selection is None:
            selection = {"agentes": [], "tools": [], "skills": [], "rag": []}
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "selection": selection,
                "source": source,
            },
        )
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config/router_config.py:get_router")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Error leyendo la configuración del router."},
        )


@router.put("/router")
async def put_router(selection: RouterSelection) -> JSONResponse:
    """Save the router selection picked in the sidebar panel.

    An empty selection (all four lists empty) means the floor defaults.

    Args:
        selection: The four pick lists (``agentes``, ``tools``,
            ``skills`` and ``rag``).

    Returns:
        JSON response with the operation result.
    """
    try:
        data = {key: getattr(selection, key) for key in _SELECTION_KEYS}
        if not save_router_selection(data):
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "No se pudo guardar la configuración del router."},
            )
        return JSONResponse(
            status_code=200,
            content={"status": "success", "message": "Configuración del router guardada."},
        )
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config/router_config.py:put_router")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Error guardando la configuración del router."},
        )
