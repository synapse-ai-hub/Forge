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

from backend.agent.utils import trigger_db, trigger_runs_db
from backend.agent.utils.contract import (
    make_error_response,
    make_success_response,
    zero_usage,
)
from backend.agent.utils.error_logger import log_error

router = APIRouter(tags=["webhooks"])

_SIGNATURE_HEADER = "x-trigger-signature"
_TIMESTAMP_HEADER = "x-trigger-timestamp"
_IDEMPOTENCY_HEADER = "x-idempotency-key"
_MAX_SKEW_SECONDS = 300
_RATE_LIMIT_PER_MINUTE = 60
_RATE_WINDOW_SECONDS = 60

_rate_hits: dict[str, list[float]] = {}


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


def check_rate_limit(slug: str) -> tuple[bool, int]:
    """Check the per-minute rate limit of a trigger.

    Args:
        slug: Trigger identifier.

    Returns:
        A tuple with whether the call is allowed and the seconds to
        wait before retrying when it is not.
    """
    now = time.time()
    hits = _rate_hits.get(slug, [])
    hits = [t for t in hits if now - t < _RATE_WINDOW_SECONDS]
    if len(hits) >= _RATE_LIMIT_PER_MINUTE:
        retry_after = int(_RATE_WINDOW_SECONDS - (now - hits[0])) + 1
        _rate_hits[slug] = hits
        return False, max(retry_after, 1)
    hits.append(now)
    _rate_hits[slug] = hits
    return True, 0


@router.post("/webhooks/{slug}")
async def receive_webhook(slug: str, request: Request) -> JSONResponse:
    """Receive an inbound event for a trigger.

    Args:
        slug: Trigger identifier.
        request: Inbound request with the raw body.

    Returns:
        202 JSON response acknowledging reception, 401 when the
        signature is invalid, 403 when the trigger is disabled,
        404 when the trigger does not exist, 409 on idempotency
        conflict, 429 when the rate limit is exceeded, 500 on
        internal error. It never raises.
    """
    try:
        raw_body = await request.body()
        allowed, retry_after = check_rate_limit(slug)
        if not allowed:
            response = JSONResponse(
                status_code=429,
                content=make_error_response("Límite excedido. Intentá más tarde."),
            )
            response.headers["Retry-After"] = str(retry_after)
            return response
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
        if not trigger.get("enabled"):
            return JSONResponse(
                status_code=403,
                content=make_error_response("Trigger deshabilitado."),
            )
        signature = request.headers.get(_SIGNATURE_HEADER, "")
        timestamp = request.headers.get(_TIMESTAMP_HEADER, "")
        if not verify_signature(secret_hash, timestamp, raw_body, signature):
            return JSONResponse(
                status_code=401,
                content=make_error_response("Firma inválida."),
            )
        idempotency_key = request.headers.get(_IDEMPOTENCY_HEADER, "")
        payload_hash = hashlib.sha256(raw_body).hexdigest()
        if idempotency_key:
            existing = trigger_runs_db.get_run_by_key(slug, idempotency_key)
            if existing is not None:
                if existing.get("payload_hash") != payload_hash:
                    return JSONResponse(
                        status_code=409,
                        content=make_error_response(
                            "Clave repetida con otro contenido."
                        ),
                    )
                return JSONResponse(
                    status_code=202,
                    content=make_success_response(
                        message="Evento aceptado.",
                        data={
                            "slug": slug,
                            "event_id": existing.get("event_id"),
                            "duplicate": True,
                        },
                        usage=zero_usage(),
                    ),
                )
            event_id = trigger_runs_db.create_run(
                slug,
                str(trigger.get("workflow_name") or ""),
                idempotency_key,
                payload_hash,
            )
        else:
            event_id = trigger_runs_db.create_run(
                slug, str(trigger.get("workflow_name") or ""), None, payload_hash
            )
        if not event_id:
            return JSONResponse(
                status_code=500,
                content=make_error_response("Error interno. Intentá más tarde."),
            )
        return JSONResponse(
            status_code=202,
            content=make_success_response(
                message="Evento aceptado.",
                data={"slug": slug, "event_id": event_id, "bytes": len(raw_body)},
                usage=zero_usage(),
            ),
        )
    except Exception as exc:
        log_error(str(exc), source="webhooks.py:receive_webhook")
        return JSONResponse(
            status_code=500,
            content=make_error_response("Error interno. Intentá más tarde."),
        )
