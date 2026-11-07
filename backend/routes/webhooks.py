"""Webhook inbound endpoint: raw-body reception per trigger slug.

Thin HTTP layer for inbound events. This step only reads the raw body
and answers 202 without waiting for the workflow; verification,
idempotency and rate-limit come in later tasks.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.agent.utils.contract import (
    make_error_response,
    make_success_response,
    zero_usage,
)
from backend.agent.utils.error_logger import log_error

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/{slug}")
async def receive_webhook(slug: str, request: Request) -> JSONResponse:
    """Receive an inbound event for a trigger.

    Args:
        slug: Trigger identifier.
        request: Inbound request with the raw body.

    Returns:
        202 JSON response acknowledging reception.
    """
    try:
        raw_body = await request.body()
        return JSONResponse(
            status_code=202,
            content=make_success_response(
                message="Evento aceptado.",
                data={"slug": slug, "bytes": len(raw_body)},
                usage=zero_usage(),
            ),
        )
    except Exception as exc:
        log_error(str(exc), source="webhooks.py:receive_webhook")
        return JSONResponse(
            status_code=500,
            content=make_error_response("Error interno. Intentá más tarde."),
        )
