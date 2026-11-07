"""Trigger management endpoints: create triggers mapped to workflows.

Thin HTTP layer for trigger CRUD. Secrets are shown only once at
creation and rotation time, never in listings.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.agent.utils import trigger_db
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
