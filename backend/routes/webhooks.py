"""Webhook inbound endpoint: raw-body reception per trigger slug.

Thin HTTP layer for inbound events. Reads the raw body, verifies the
HMAC signature with a 5-minute timestamp and answers 202 without
waiting for the workflow.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.agent.utils import trigger_db, trigger_runs_db
from backend.agent.utils.contract import (
    make_error_response,
    make_success_response,
    validate_response,
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
    secret: str | None, timestamp: str | None, raw_body: bytes | None, signature: str | None
) -> bool:
    """Verify the HMAC signature of an inbound event.

    The HMAC key is ``sha256(secret)``: the caller hashes the plain
    secret shown once, then signs ``timestamp.body``. The server
    stores only the hash and uses it directly as the key.

    Args:
        secret: Stored secret hash used as HMAC key.
        timestamp: Unix seconds sent by the caller.
        raw_body: Raw request body.
        signature: Hex signature sent by the caller.

    Returns:
        ``True`` when the signature matches and the timestamp is fresh.
        It never raises.
    """
    try:
        if not secret or not isinstance(secret, str):
            return False
        if not isinstance(signature, str) or not signature:
            return False
        if raw_body is None:
            return False
        if not isinstance(raw_body, (bytes, bytearray)):
            return False
        ts = int(timestamp)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if abs(int(time.time()) - ts) > _MAX_SKEW_SECONDS:
        return False
    try:
        expected = hmac.new(
            secret.encode("utf-8"),
            str(timestamp).encode("utf-8") + b"." + bytes(raw_body),
            hashlib.sha256,
        ).hexdigest()
    except Exception:
        return False
    try:
        return hmac.compare_digest(expected, signature)
    except Exception:
        return False


def map_payload(raw_body: bytes | None) -> dict[str, Any]:
    """Map the raw body to a workflow input dict.

    Convention: JSON object returns as-is; JSON array, string,
    number or null returns as ``{"value": parsed}``; non-JSON
    text returns as ``{"text": raw}``; empty body returns as
    ``{"text": ""}``.

    Args:
        raw_body: Raw request body.

    Returns:
        A dict ready to be used as workflow input. It never raises.
    """
    try:
        if not raw_body:
            return {"text": ""}
        if not isinstance(raw_body, (bytes, bytearray)):
            return {"text": ""}
        parsed: Any = json.loads(bytes(raw_body).decode("utf-8"))
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}
    except (ValueError, UnicodeDecodeError) as exc:
        log_error(str(exc), source="webhooks.py:map_payload")
        try:
            return {"text": raw_body.decode("utf-8", errors="replace")}
        except Exception as inner_exc:
            log_error(str(inner_exc), source="webhooks.py:map_payload")
            return {"text": ""}


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
    if not hits and slug in _rate_hits and len(_rate_hits) > 1000:
        _rate_hits.pop(slug, None)
        return True, 0
    if len(hits) >= _RATE_LIMIT_PER_MINUTE:
        retry_after = int(_RATE_WINDOW_SECONDS - (now - hits[0])) + 1
        _rate_hits[slug] = hits
        return False, max(retry_after, 1)
    hits.append(now)
    _rate_hits[slug] = hits
    if not hits:
        _rate_hits.pop(slug, None)
    return True, 0


async def _launch_workflow(
    event_id: str, workflow_name: str, workflow_input: dict[str, Any]
) -> None:
    """Launch the mapped workflow in the background.

    Args:
        event_id: Delivery identifier for tracing.
        workflow_name: Workflow to execute.
        workflow_input: Mapped payload (kept for tracing).

    Returns:
        Nothing. It never raises.
    """
    try:
        from backend.agent.utils import trigger_steps_db
        from backend.agent.utils.workflow_service import workflow_service

        attempt = 1
        try:
            existing = trigger_runs_db.get_run(event_id)
            if isinstance(existing, dict):
                attempt = int(existing.get("attempt") or 1)
        except Exception:
            attempt = 1
        received_id = trigger_steps_db.open_step(event_id, attempt, 1, 0, "received", "received")
        trigger_steps_db.commit_step(received_id, "received")
        verified_id = trigger_steps_db.open_step(event_id, attempt, 2, 0, "verified", "verified")
        trigger_steps_db.commit_step(verified_id, "verified")
        mapped_id = trigger_steps_db.open_step(event_id, attempt, 3, 0, "mapped", "mapped")
        trigger_steps_db.commit_step(mapped_id, "mapped")
        launched_id = trigger_steps_db.open_step(event_id, attempt, 4, 0, "launched", "launched")
        result = await workflow_service.start_run(workflow_name, source="webhook")
        if isinstance(result, dict) and result.get("ok"):
            run_id = str(result.get("run_id") or "")
            if run_id:
                trigger_runs_db.set_workflow_run(event_id, run_id)
            trigger_steps_db.commit_step(launched_id, run_id or "launched")
            trigger_runs_db.finish_run(event_id, "notified", run_id or "ok", None, run_id or None)
        else:
            message = (
                str(result.get("message") or "No se pudo lanzar el workflow.")
                if isinstance(result, dict)
                else "No se pudo lanzar el workflow."
            )
            log_error(message, source="webhooks.py:_launch_workflow")
            trigger_steps_db.fail_step(launched_id, message)
            trigger_runs_db.finish_run(event_id, "error", None, message)
        try:
            from backend.agent.utils import trigger_notify

            notified_id = trigger_steps_db.open_step(event_id, attempt, 5, 0, "notified", "notified")
            trigger_notify.notify_finished(event_id)
            trigger_steps_db.commit_step(notified_id, "notified")
        except Exception as exc:
            log_error(str(exc), source="webhooks.py:_launch_workflow")
    except Exception as exc:
        log_error(str(exc), source="webhooks.py:_launch_workflow")


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
        conflict, 422 when the mapped workflow is invalid,
        429 when the rate limit is exceeded, 500 on
        internal error. It never raises.
    """
    try:
        raw_body = await request.body()
        allowed, retry_after = check_rate_limit(slug)
        if not allowed:
            response = JSONResponse(
                status_code=429,
                content=validate_response(make_error_response("Límite excedido. Intentá más tarde.")),
            )
            response.headers["Retry-After"] = str(retry_after)
            return response
        trigger = trigger_db.get_trigger(slug)
        if trigger is None:
            return JSONResponse(
                status_code=404,
                content=validate_response(make_error_response("Trigger no encontrado.")),
            )
        secret_hash = trigger_db.get_trigger_secret(slug)
        if not secret_hash:
            return JSONResponse(
                status_code=404,
                content=validate_response(make_error_response("Trigger no encontrado.")),
            )
        if not trigger.get("enabled"):
            return JSONResponse(
                status_code=403,
                content=validate_response(make_error_response("Trigger deshabilitado.")),
            )
        signature = request.headers.get(_SIGNATURE_HEADER, "")
        timestamp = request.headers.get(_TIMESTAMP_HEADER, "")
        if not verify_signature(secret_hash, timestamp, raw_body, signature):
            return JSONResponse(
                status_code=401,
                content=validate_response(make_error_response("Firma inválida.")),
            )
        workflow_name = str(trigger.get("workflow_name") or "")
        if not workflow_name:
            return JSONResponse(
                status_code=422,
                content=validate_response(make_error_response("Workflow del trigger inválido.")),
            )
        try:
            from backend.agent.utils.workflow_loader import load_workflow

            loaded = load_workflow(workflow_name)
            if loaded.get("status") != "success":
                return JSONResponse(
                    status_code=422,
                    content=validate_response(make_error_response("Workflow del trigger inválido.")),
                )
        except Exception as exc:
            log_error(str(exc), source="webhooks.py:receive_webhook")
            return JSONResponse(
                status_code=422,
                content=validate_response(make_error_response("Workflow del trigger inválido.")),
            )
        workflow_input = map_payload(raw_body)
        idempotency_key = request.headers.get(_IDEMPOTENCY_HEADER, "")
        payload_hash = hashlib.sha256(raw_body).hexdigest()
        if idempotency_key:
            existing = trigger_runs_db.get_run_by_key(slug, idempotency_key)
            if existing is not None:
                if existing.get("payload_hash") != payload_hash:
                    return JSONResponse(
                        status_code=409,
                        content=validate_response(
                            make_error_response(
                                "Clave repetida con otro contenido."
                            )
                        ),
                    )
                return JSONResponse(
                    status_code=202,
                    content=validate_response(
                        make_success_response(
                            message="Evento aceptado.",
                            data={
                                "slug": slug,
                                "event_id": existing.get("event_id"),
                                "duplicate": True,
                            },
                            usage=zero_usage(),
                        )
                    ),
                )
            event_id = trigger_runs_db.create_run(
                slug,
                workflow_name,
                idempotency_key,
                payload_hash,
            )
            if not event_id:
                retry_existing = trigger_runs_db.get_run_by_key(slug, idempotency_key)
                if retry_existing is not None:
                    if retry_existing.get("payload_hash") != payload_hash:
                        return JSONResponse(
                            status_code=409,
                            content=validate_response(
                                make_error_response(
                                    "Clave repetida con otro contenido."
                                )
                            ),
                        )
                    return JSONResponse(
                        status_code=202,
                        content=validate_response(
                            make_success_response(
                                message="Evento aceptado.",
                                data={
                                    "slug": slug,
                                    "event_id": retry_existing.get("event_id"),
                                    "duplicate": True,
                                },
                                usage=zero_usage(),
                            )
                        ),
                    )
        else:
            event_id = trigger_runs_db.create_run(
                slug, workflow_name, None, payload_hash
            )
        if not event_id:
            return JSONResponse(
                status_code=500,
                content=validate_response(make_error_response("Error interno. Intentá más tarde.")),
            )
        asyncio.create_task(_launch_workflow(event_id, workflow_name, workflow_input))
        return JSONResponse(
            status_code=202,
            content=validate_response(
                make_success_response(
                    message="Evento aceptado.",
                    data={
                        "slug": slug,
                        "event_id": event_id,
                        "bytes": len(raw_body),
                        "input": workflow_input,
                    },
                    usage=zero_usage(),
                )
            ),
        )
    except Exception as exc:
        log_error(str(exc), source="webhooks.py:receive_webhook")
        return JSONResponse(
            status_code=500,
            content=validate_response(make_error_response("Error interno. Intentá más tarde.")),
        )
