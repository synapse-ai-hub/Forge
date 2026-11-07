"""Trigger management endpoints: create triggers mapped to workflows.

Thin HTTP layer for trigger CRUD. Secrets are shown only once at
creation and rotation time, never in listings.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.agent.utils import trigger_db, trigger_runs_db
from backend.agent.utils.contract import (
    make_error_response,
    make_success_response,
    validate_response,
    zero_usage,
)
from backend.agent.utils.error_logger import log_error

router = APIRouter(tags=["triggers"])


class TriggerCreate(BaseModel):
    """Payload to create a trigger.

    Attributes:
        slug: Trigger identifier.
        workflow_name: Workflow the trigger launches.
    """

    slug: str
    workflow_name: str


@router.post("/triggers")
async def create_trigger(payload: TriggerCreate) -> JSONResponse:
    """Create a trigger mapped to an existing workflow.

    Args:
        payload: Slug and workflow name.

    Returns:
        201 with the trigger and plain secret shown once, 409 when
        the slug exists, 422 when the workflow is invalid, 500 on
        internal error. It never raises.

    Raises:
        Nothing. All errors are captured and returned as JSON.
    """
    try:
        slug = payload.slug.strip()
        workflow_name = payload.workflow_name.strip()
        if not slug or not workflow_name:
            return JSONResponse(
                status_code=422,
                content=validate_response(
                    make_error_response("Workflow no disponible.", usage=zero_usage())
                ),
            )
        result = trigger_db.create_trigger(slug, workflow_name)
        if result is None:
            return JSONResponse(
                status_code=500,
                content=validate_response(
                    make_error_response(
                        "Error interno. Intentá más tarde.", usage=zero_usage()
                    )
                ),
            )
        if result.get("error") == "duplicate":
            return JSONResponse(
                status_code=409,
                content=validate_response(
                    make_error_response("Ya existe ese trigger.", usage=zero_usage())
                ),
            )
        if result.get("error") == "workflow_not_found":
            return JSONResponse(
                status_code=422,
                content=validate_response(
                    make_error_response("Workflow no disponible.", usage=zero_usage())
                ),
            )
        return JSONResponse(
            status_code=201,
            content=validate_response(
                make_success_response(
                    message="Trigger creado.",
                    data=result,
                    usage=zero_usage(),
                )
            ),
        )
    except Exception as exc:
        log_error(str(exc), source="triggers.py:create_trigger")
        return JSONResponse(
            status_code=500,
            content=validate_response(
                make_error_response(
                    "Error interno. Intentá más tarde.", usage=zero_usage()
                )
            ),
        )


class TriggerEnabled(BaseModel):
    """Payload to enable or disable a trigger.

    Attributes:
        enabled: True to accept events, False to reject them.
    """

    enabled: bool


@router.get("/triggers")
async def list_triggers(limit: int = 50, offset: int = 0) -> JSONResponse:
    """List triggers without exposing secrets.

    Args:
        limit: Maximum number of triggers.
        offset: Number of triggers to skip.

    Returns:
        200 with the triggers, 500 on internal error. It never raises.

    Raises:
        Nothing. All errors are captured and returned as JSON.
    """
    try:
        safe_limit = max(1, min(limit, 100))
        safe_offset = max(0, offset)
        triggers = trigger_db.list_triggers(limit=safe_limit, offset=safe_offset)
        return JSONResponse(
            status_code=200,
            content=validate_response(
                make_success_response(
                    message="Triggers.",
                    data=triggers,
                    usage=zero_usage(),
                )
            ),
        )
    except Exception as exc:
        log_error(str(exc), source="triggers.py:list_triggers")
        return JSONResponse(
            status_code=500,
            content=validate_response(
                make_error_response(
                    "Error interno. Intentá más tarde.", usage=zero_usage()
                )
            ),
        )


@router.get("/triggers/{slug}/runs")
async def list_trigger_runs(
    slug: str, limit: int = 50, offset: int = 0
) -> JSONResponse:
    """List the deliveries of a trigger for audit.

    Args:
        slug: Trigger identifier.
        limit: Maximum number of deliveries.
        offset: Number of deliveries to skip.

    Returns:
        200 with deliveries ordered by date, 404 when the trigger
        does not exist, 500 on internal error. It never raises.

    Raises:
        Nothing. All errors are captured and returned as JSON.
    """
    try:
        normalized = slug.strip()
        if trigger_db.get_trigger(normalized) is None:
            return JSONResponse(
                status_code=404,
                content=validate_response(
                    make_error_response(
                        "Trigger no encontrado.", usage=zero_usage()
                    )
                ),
            )
        safe_limit = max(1, min(limit, 100))
        safe_offset = max(0, offset)
        runs = trigger_runs_db.list_runs(
            normalized, limit=safe_limit, offset=safe_offset
        )
        return JSONResponse(
            status_code=200,
            content=validate_response(
                make_success_response(
                    message="Entregas.",
                    data=runs,
                    usage=zero_usage(),
                )
            ),
        )
    except Exception as exc:
        log_error(str(exc), source="triggers.py:list_trigger_runs")
        return JSONResponse(
            status_code=500,
            content=validate_response(
                make_error_response(
                    "Error interno. Intentá más tarde.", usage=zero_usage()
                )
            ),
        )


@router.patch("/triggers/{slug}")
async def set_trigger_enabled(slug: str, payload: TriggerEnabled) -> JSONResponse:
    """Enable or disable a trigger without deleting its history.

    Args:
        slug: Trigger identifier.
        payload: Desired enabled state.

    Returns:
        200 with the updated trigger, 404 when it does not exist,
        500 on internal error. It never raises.

    Raises:
        Nothing. All errors are captured and returned as JSON.
    """
    try:
        normalized = slug.strip()
        updated = trigger_db.set_enabled(normalized, payload.enabled)
        if not updated:
            existing = trigger_db.get_trigger(normalized)
            if existing is None:
                return JSONResponse(
                    status_code=404,
                    content=validate_response(
                        make_error_response(
                            "Trigger no encontrado.", usage=zero_usage()
                        )
                    ),
                )
            return JSONResponse(
                status_code=500,
                content=validate_response(
                    make_error_response(
                        "Error interno. Intentá más tarde.", usage=zero_usage()
                    )
                ),
            )
        trigger = trigger_db.get_trigger(normalized)
        return JSONResponse(
            status_code=200,
            content=validate_response(
                make_success_response(
                    message="Trigger actualizado.",
                    data=trigger,
                    usage=zero_usage(),
                )
            ),
        )
    except Exception as exc:
        log_error(str(exc), source="triggers.py:set_trigger_enabled")
        return JSONResponse(
            status_code=500,
            content=validate_response(
                make_error_response(
                    "Error interno. Intentá más tarde.", usage=zero_usage()
                )
            ),
        )


@router.post("/triggers/{slug}/rotate")
async def rotate_trigger_secret(slug: str) -> JSONResponse:
    """Rotate the secret of a trigger.

    Args:
        slug: Trigger identifier.

    Returns:
        200 with the new plain secret shown once, 404 when the
        trigger does not exist, 500 on internal error. It never raises.

    Raises:
        Nothing. All errors are captured and returned as JSON.
    """
    try:
        result = trigger_db.rotate_secret(slug.strip())
        if result is None:
            existing = trigger_db.get_trigger(slug.strip())
            if existing is None:
                return JSONResponse(
                    status_code=404,
                    content=validate_response(
                        make_error_response(
                            "Trigger no encontrado.", usage=zero_usage()
                        )
                    ),
                )
            return JSONResponse(
                status_code=500,
                content=validate_response(
                    make_error_response(
                        "Error interno. Intentá más tarde.", usage=zero_usage()
                    )
                ),
            )
        return JSONResponse(
            status_code=200,
            content=validate_response(
                make_success_response(
                    message="Secreto rotado.",
                    data=result,
                    usage=zero_usage(),
                )
            ),
        )
    except Exception as exc:
        log_error(str(exc), source="triggers.py:rotate_trigger_secret")
        return JSONResponse(
            status_code=500,
            content=validate_response(
                make_error_response(
                    "Error interno. Intentá más tarde.", usage=zero_usage()
                )
            ),
        )
