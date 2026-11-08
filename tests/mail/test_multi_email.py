"""Tests for multi-account email storage without .env usage."""

from __future__ import annotations

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.agent.utils import email_accounts
from backend.agent.utils.queries import load_query


def test_detect_gmail() -> None:
    """Detect Gmail settings from a gmail address.

    Returns:
        None.
    """
    settings = email_accounts.detect_email_settings("Forge@Gmail.com")
    assert settings["imap_server"] == "imap.gmail.com"
    assert settings["imap_port"] == 993
    assert settings["provider"] == "gmail"


def test_detect_custom() -> None:
    """Detect custom domain settings with fallback servers.

    Returns:
        None.
    """
    settings = email_accounts.detect_email_settings("forge@tudominio.com")
    assert settings["imap_server"] == "mail.tudominio.com"
    assert settings["smtp_server"] == "smtp.tudominio.com"
    assert settings["provider"] == "custom"


def test_normalize_alias_optional() -> None:
    """Generate alias from email when alias is missing.

    Returns:
        None.
    """
    assert email_accounts._normalize_alias("", "Forge@Dominio.com") == "forge"
    assert email_accounts._normalize_alias("  Trabajo  ", "a@b.com") == "trabajo"


def test_queries_load() -> None:
    """Load email_accounts queries without error.

    Returns:
        None.
    """
    assert "alias" in load_query("email_accounts/upsert.sql")
    assert "password_encrypted" not in load_query("email_accounts/list.sql")
    assert "alias = ? OR email = ?" in load_query("email_accounts/get_by_alias_or_email.sql")


def test_no_env_usage() -> None:
    """Ensure email tools do not read EMAIL_* from env.

    Returns:
        None.
    """
    for path in (
        os.path.join(_PROJECT_ROOT, "backend", "agent", "tools", "check_email.py"),
        os.path.join(_PROJECT_ROOT, "backend", "agent", "tools", "send_email.py"),
        os.path.join(_PROJECT_ROOT, "backend", "agent", "utils", "email_accounts.py"),
    ):
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()
        assert "EMAIL_IMAP_SERVER" not in content
        assert "EMAIL_USER" not in content
        assert "EMAIL_PASS" not in content
