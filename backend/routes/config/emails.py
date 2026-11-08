"""Email account endpoints: list, save and delete IMAP/SMTP accounts."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.agent.utils.error_logger import log_error

router = APIRouter()


@router.get("/emails")
async def list_email_accounts() -> JSONResponse:
    """List configured email accounts without passwords.

    Returns:
        JSON response with the account list.
    """
    from backend.agent.utils import email_accounts

    try:
        accounts = await asyncio.to_thread(email_accounts.list_accounts)
        return JSONResponse(status_code=200, content={"status": "success", "emails": accounts})
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config/emails.py:list_email_accounts")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Error listando cuentas: {exc}"},
        )


@router.put("/emails")
async def save_email_account(data: dict[str, Any]) -> JSONResponse:
    """Validate and store (encrypted) an email account.

    Body: ``{"email": "...", "password": "...", "alias": "..."}``.
    Alias is optional; when empty it is generated from the email.

    Args:
        data: Request body with email, password and optional alias.

    Returns:
        JSON response with the result.
    """
    from backend.agent.utils import email_accounts

    try:
        email = (data or {}).get("email", "")
        password = (data or {}).get("password", "")
        alias = (data or {}).get("alias", "")
        result = await asyncio.to_thread(email_accounts.save_account, email, password, alias)
        if result.get("status") != "success":
            return JSONResponse(status_code=400, content=result)
        return JSONResponse(status_code=200, content=result)
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config/emails.py:save_email_account")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Error guardando cuenta: {exc}"},
        )


@router.delete("/emails/{alias}")
async def delete_email_account(alias: str) -> JSONResponse:
    """Remove a stored email account by alias.

    Args:
        alias: Alias of the account to delete.

    Returns:
        JSON response with the result.
    """
    from backend.agent.utils import email_accounts

    try:
        result = await asyncio.to_thread(email_accounts.delete_account, alias)
        if result.get("status") != "success":
            return JSONResponse(status_code=400, content=result)
        return JSONResponse(status_code=200, content=result)
    except Exception as exc:
        log_error(str(exc), source="backend/routes/config/emails.py:delete_email_account")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Error eliminando cuenta: {exc}"},
        )
