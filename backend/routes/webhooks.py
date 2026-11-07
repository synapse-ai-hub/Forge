"""Webhook inbound endpoint: raw-body reception per trigger slug.

Thin HTTP layer for inbound events. Reads the raw body, verifies the
HMAC signature with a 5-minute timestamp and answers 202 without
waiting for the workflow.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.agent.utils import trigger_db
from backend.agent.utils.contract import (
    make_error_response,
    make_success_response,
    zero_usage,
)
from backend.agent.utils.error_logger import log_error

router = APIRouter(tags=["webhooks"])

_SIGNATURE_HEADER = "x-trigger-signature"
_TIMESTAMP_HEADER = "x-trigger-timestamp"
_MAX_SKEW_SECONDS = 300


def verify_signature(
    secret_hash: str, timestamp: str, raw_body: bytes, signature: str
) -> bool:
    """Verify the HMAC signature of an inbound event.

    Args:
        secret_hash: Stored hash used as HMAC key.
        timestamp: Unix seconds sent by the caller.
        raw_body: Raw request body.
        signature: Hex signature sent by the caller.

    Returns:
        ``True`` when the signature matches and the timestamp is fresh.
    """
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs(int(time.time()) - ts) > _MAX_SKEW_SECONDS:
        return False
    expected = hmac.new(
        secret_hash.encode("utf-8"),
        timestamp.encode("utf-8") + b"." + raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/webhooks/{slug}")
async def receive_webhook(slug: str, request: Request) -> JSONResponse:
    """Receive an inbound event for a trigger.

    Args:
        slug: Trigger identifier.
        request: Inbound request with the raw body.

    Returns:
        202 JSON response acknowledging reception, 401 when the
        signature is invalid, 404 when the trigger does not exist.
    """
    try:
        raw_body = await request.body()
        trigger = trigger_db.get_trigger(slug)
        if trigger is None:
            return JSONResponse(
                status_code=404,
                content=make_error_response("Trigger no encontrado."),
            )
        secret_hash = trigger_db.get_trigger_secret(slug)
        if not secret_hash:
            return JSONResponse(
                status_code=404,
                content=make_error_response("Trigger no encontrado."),
            )
        signature = request.headers.get(_SIGNATURE_HEADER, "")
        timestamp = request.headers.get(_TIMESTAMP_HEADER, "")
        if not verify_signature(secret_hash, timestamp, raw_body, signature):
            return JSONResponse(
                status_code=401,
                content=make_error_response("Firma inválida."),
            )
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
