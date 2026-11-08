"""Encrypted storage for multiple IMAP/SMTP email accounts.

Accounts are configured from the UI (email + password + optional alias) and
stored encrypted (Fernet, reversible) in the ``email_accounts`` table. No
``EMAIL_*`` environment variables are used. The ``account`` selector accepted
by the email tools can be either the alias or the email address.
"""

from __future__ import annotations

import imaplib
import logging
import sqlite3
from datetime import datetime
from typing import Any

from backend.agent.utils.db import get_connection
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.queries import load_query

logger = logging.getLogger(__name__)


def _load_fernet() -> Any:
    """Return the shared Fernet instance used for secrets.

    Reuses the same secret resolution as provider keys so there is a
    single encryption root (``APP_SECRET_KEY`` or generated
    ``.secret_key``).

    Returns:
        A ``Fernet`` instance, or ``None`` if cryptography is missing.

    Raises:
        No exception escapes: failures are logged and ``None`` returned.
    """
    try:
        from backend.agent.utils.provider_keys import _load_fernet as _provider_fernet

        return _provider_fernet()
    except Exception as e:
        log_error(str(e), source="email_accounts.py:_load_fernet")
        return None


def _normalize_alias(alias: str | None, email: str) -> str:
    """Normalize the alias, generating it from the email when missing.

    Alias is verbatim as typed by the user (only stripped, case kept).
    Email local part fallback is lowercased.

    Args:
        alias: Optional alias provided from the UI.
        email: Full email address the account belongs to.

    Returns:
        Alias stripped of whitespace, case preserved.

    Raises:
        ValueError: If neither alias nor email provide a usable value.
    """
    cleaned = (alias or "").strip()
    if cleaned:
        return cleaned
    local = (email or "").strip().lower().split("@")[0]
    if not local:
        raise ValueError("Alias vacío y email inválido.")
    return local


def detect_email_settings(email: str) -> dict[str, Any]:
    """Detect IMAP/SMTP settings for an email address without user input.

    Single source of truth lives in ``email_domains._PRESETS`` (verified
    against Thunderbird ISPDB). No network call is made here; the
    connection is validated on save/use.

    Args:
        email: Full email address (e.g. ``"forge@tudominio.com"``).

    Returns:
        Dict with ``imap_server``, ``imap_port``, ``smtp_server``,
        ``smtp_port`` and ``provider``.

    Raises:
        ValueError: If the email has no valid domain part.
    """
    from backend.agent.utils.email_domains import _PRESETS as _DOMAIN_PRESETS

    address = (email or "").strip().lower()
    if "@" not in address:
        raise ValueError(f"Email inválido: {email!r}")
    domain = address.split("@", 1)[1].strip()
    if not domain or "." not in domain:
        raise ValueError(f"Email inválido: {email!r}")
    preset = _DOMAIN_PRESETS.get(domain)
    if preset is not None:
        return dict(preset)
    return {
        "imap_server": f"mail.{domain}",
        "imap_port": 993,
        "smtp_server": f"smtp.{domain}",
        "smtp_port": 587,
        "provider": "custom",
    }


def _connect() -> sqlite3.Connection | None:
    """Open a short-lived connection to the agent DB and ensure schema.

    Returns:
        A new ``sqlite3.Connection``, or ``None`` on failure.

    Raises:
        No exception escapes: failures are logged and ``None`` returned.
    """
    try:
        conn = get_connection()
        from backend.agent.ddl_setup import setup_database

        setup_database(conn)
        return conn
    except Exception as e:
        log_error(str(e), source="email_accounts.py:_connect")
        return None


def save_account(email: str, password: str, alias: str | None = None) -> dict[str, Any]:
    """Encrypt and persist an email account from the UI.

    One row per mailbox (``email`` is the primary key). When the requested
    alias is already used by another mailbox it is suffixed with the email
    domain to avoid overwriting a different account.

    Args:
        email: Full email address of the mailbox.
        password: Plain-text password or app password (never stored clear).
        alias: Optional alias to select the account later. When empty it
            is generated from the email local part.

    Returns:
        Contract dict ``{"status": "success"|"error", "message": ...}``
        with the resolved alias on success.

    Raises:
        No exception escapes: failures are returned as error dicts.
    """
    try:
        address = (email or "").strip().lower()
        if not address or "@" not in address:
            return {"status": "error", "message": f"Email inválido: {email!r}."}
        if not password or not password.strip():
            return {"status": "error", "message": "La contraseña no puede estar vacía."}
        resolved_alias = _normalize_alias(alias, address)
        domain = address.split("@", 1)[1]
        try:
            from backend.agent.utils.email_domains import detect_domain_settings, upsert_domain

            settings, _source = detect_domain_settings(domain, address)
        except Exception:
            settings = detect_email_settings(address)
            try:
                from backend.agent.utils.email_domains import upsert_domain as _upsert_fallback

                _upsert_fallback(domain, settings, "custom")
            except Exception:
                pass
        fernet = _load_fernet()
        if fernet is None:
            return {
                "status": "error",
                "message": "Cifrado no disponible (falta el paquete 'cryptography').",
            }
        last_status = "pending"
        last_error = None
        try:
            mail = imaplib.IMAP4_SSL(
                str(settings.get("imap_server", "")), int(settings.get("imap_port", 993)), timeout=10
            )
            try:
                mail.login(address, password.strip())
                last_status = "ok"
            finally:
                try:
                    mail.logout()
                except Exception:
                    pass
        except Exception as conn_e:
            last_status = "error"
            last_error = str(conn_e)[:200]
        encrypted = fernet.encrypt(password.strip().encode("utf-8")).decode("ascii")
        now = datetime.now().isoformat()
        conn = _connect()
        if conn is None:
            return {"status": "error", "message": "No se pudo abrir la base de datos."}
        try:
            with conn:
                existing = conn.execute(
                    load_query("email_accounts/get_by_alias_or_email.sql"),
                    (resolved_alias, resolved_alias),
                ).fetchone()
                if existing is not None and str(existing["email"]).lower() != address:
                    full_domain = address.split("@", 1)[1]
                    resolved_alias = f"{resolved_alias}-{full_domain}"
                conn.execute(
                    load_query("email_accounts/upsert.sql"),
                    (
                        address,
                        resolved_alias,
                        encrypted,
                        settings["imap_server"],
                        int(settings["imap_port"]),
                        settings["smtp_server"],
                        int(settings["smtp_port"]),
                        str(settings["provider"]),
                        last_status,
                        last_error,
                        now,
                    ),
                )
        finally:
            conn.close()
        return {"status": "success", "message": f"Cuenta {resolved_alias} guardada.", "alias": resolved_alias}
    except Exception as e:
        log_error(str(e), source="email_accounts.py:save_account")
        return {"status": "error", "message": f"Error guardando la cuenta: {e}"}


def resolve_account(account: str = "") -> dict[str, Any] | None:
    """Resolve an account selector to decrypted IMAP/SMTP credentials.

    Backend-only helper: the returned dict contains the plain-text
    password and must never be sent to the frontend or the LLM.

    Args:
        account: Alias or email address. When empty, the first account
            ordered by alias is returned (``default`` compatibility).

    Returns:
        Dict with ``alias``, ``email``, ``password``, ``imap_server``,
        ``imap_port``, ``smtp_server``, ``smtp_port`` and ``provider``,
        or ``None`` when not found or undecryptable.

    Raises:
        No exception escapes: failures are logged and ``None`` returned.
    """
    try:
        key = (account or "").strip().lower()
        fernet = _load_fernet()
        if fernet is None:
            return None
        conn = _connect()
        if conn is None:
            return None
        try:
            if not key:
                rows = conn.execute(load_query("email_accounts/list.sql")).fetchall()
                if not rows:
                    return None
                first_alias = str(rows[0]["alias"])
                row = conn.execute(
                    load_query("email_accounts/get_by_alias_or_email.sql"),
                    (first_alias, first_alias),
                ).fetchone()
            else:
                row = conn.execute(
                    load_query("email_accounts/get_by_alias_or_email.sql"),
                    (key, key),
                ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        password = fernet.decrypt(row["password_encrypted"].encode("ascii")).decode("utf-8")
        return {
            "alias": str(row["alias"]),
            "email": str(row["email"]),
            "password": password,
            "imap_server": str(row["imap_server"] or ""),
            "imap_port": int(row["imap_port"] or 993),
            "smtp_server": str(row["smtp_server"] or ""),
            "smtp_port": int(row["smtp_port"] or 587),
            "provider": str(row["provider"] or ""),
        }
    except Exception as e:
        log_error(str(e), source="email_accounts.py:resolve_account")
        return None


def list_accounts() -> list[dict[str, Any]]:
    """List configured email accounts without passwords.

    Returns:
        List of dicts with ``alias``, ``email``, ``provider`` and
        ``last_status`` ordered by alias. Empty list on failure.

    Raises:
        No exception escapes: failures are logged and ``[]`` returned.
    """
    try:
        conn = _connect()
        if conn is None:
            return []
        try:
            rows = conn.execute(load_query("email_accounts/list.sql")).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        log_error(str(e), source="email_accounts.py:list_accounts")
        return []


def load_email_accounts_text() -> str:
    """Format configured accounts as prompt lines (alias + email, no secrets).

    Returns:
        One ``- alias — email`` line per account, or ``""`` when none.
        Failures return ``""``.

    Raises:
        No exception escapes: failures are logged and ``""`` returned.
    """
    try:
        lines = []
        for item in list_accounts():
            alias = str(item.get("alias", "") or "").strip()
            email = str(item.get("email", "") or "").strip()
            if not email:
                continue
            lines.append(f"- {alias} — {email}" if alias else f"- {email}")
        return "\n".join(lines)
    except Exception as e:
        log_error(str(e), source="email_accounts.py:load_email_accounts_text")
        return ""


def delete_account(alias: str) -> dict[str, Any]:
    """Delete an email account by alias or email.

    Args:
        alias: Alias or email address of the account to delete.

    Returns:
        Contract dict ``{"status": "success"|"error", "message": ...}``.

    Raises:
        No exception escapes: failures are returned as error dicts.
    """
    try:
        cleaned = (alias or "").strip()
        if not cleaned:
            return {"status": "error", "message": "Alias requerido."}
        conn = _connect()
        if conn is None:
            return {"status": "error", "message": "No se pudo abrir la base de datos."}
        try:
            with conn:
                cursor = conn.execute(load_query("email_accounts/delete.sql"), (cleaned, cleaned))
                deleted = cursor.rowcount > 0
        finally:
            conn.close()
        if not deleted:
            return {"status": "error", "message": f"No existe la cuenta '{cleaned}'."}
        return {"status": "success", "message": f"Cuenta {cleaned} eliminada."}
    except Exception as e:
        log_error(str(e), source="email_accounts.py:delete_account")
        return {"status": "error", "message": f"Error eliminando la cuenta: {e}"}
