"""Cache and autodetection of email domain settings.

First lookup is always the ``email_domains`` DB table. On miss the
Thunderbird ISPDB, the provider autoconfig URLs and the local presets
are tried in order, then the result is cached for the next account of
the same domain. The user never enters ports.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import sqlite3
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

from backend.agent.utils.db import get_connection
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.queries import load_query

logger = logging.getLogger(__name__)

_PRESETS: dict[str, dict[str, Any]] = {
    "gmail.com": {
        "imap_server": "imap.gmail.com",
        "imap_port": 993,
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "provider": "gmail",
    },
    "googlemail.com": {
        "imap_server": "imap.gmail.com",
        "imap_port": 993,
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "provider": "gmail",
    },
    "outlook.com": {
        "imap_server": "outlook.office365.com",
        "imap_port": 993,
        "smtp_server": "smtp-mail.outlook.com",
        "smtp_port": 587,
        "provider": "outlook",
    },
    "hotmail.com": {
        "imap_server": "outlook.office365.com",
        "imap_port": 993,
        "smtp_server": "smtp-mail.outlook.com",
        "smtp_port": 587,
        "provider": "outlook",
    },
    "live.com": {
        "imap_server": "outlook.office365.com",
        "imap_port": 993,
        "smtp_server": "smtp-mail.outlook.com",
        "smtp_port": 587,
        "provider": "outlook",
    },
    "yahoo.com": {
        "imap_server": "imap.mail.yahoo.com",
        "imap_port": 993,
        "smtp_server": "smtp.mail.yahoo.com",
        "smtp_port": 465,
        "provider": "yahoo",
    },
    "icloud.com": {
        "imap_server": "imap.mail.me.com",
        "imap_port": 993,
        "smtp_server": "smtp.mail.me.com",
        "smtp_port": 587,
        "provider": "icloud",
    },
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
        log_error(str(e), source="email_domains.py:_connect")
        return None


def get_domain(domain: str) -> dict[str, Any] | None:
    """Get cached settings for a domain.

    Args:
        domain: Email domain lowercased without whitespace.

    Returns:
        Dict with ``domain``, ``imap_server``, ``imap_port``,
        ``smtp_server``, ``smtp_port``, ``provider`` and ``source``,
        or ``None`` on miss.

    Raises:
        No exception escapes: failures are logged and ``None`` returned.
    """
    try:
        cleaned = (domain or "").strip().lower()
        if not cleaned:
            return None
        conn = _connect()
        if conn is None:
            return None
        try:
            row = conn.execute(load_query("email_domains/get.sql"), (cleaned,)).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return {
            "domain": str(row["domain"]),
            "imap_server": str(row["imap_server"] or ""),
            "imap_port": int(row["imap_port"] or 993),
            "smtp_server": str(row["smtp_server"] or ""),
            "smtp_port": int(row["smtp_port"] or 587),
            "provider": str(row["provider"] or ""),
            "source": str(row["source"] or ""),
        }
    except Exception as e:
        log_error(str(e), source="email_domains.py:get_domain")
        return None


def upsert_domain(domain: str, settings: dict[str, Any], source: str = "preset") -> bool:
    """Cache settings for a domain.

    Args:
        domain: Email domain lowercased.
        settings: Dict with ``imap_server``, ``imap_port``,
            ``smtp_server``, ``smtp_port`` and ``provider``.
        source: Where settings came from (``ispdb``, ``autoconfig``,
            ``preset``, ``custom``).

    Returns:
        ``True`` on success, ``False`` otherwise.

    Raises:
        No exception escapes: failures are logged and ``False`` returned.
    """
    try:
        cleaned = (domain or "").strip().lower()
        if not cleaned or not settings:
            return False
        now = datetime.now(timezone.utc).isoformat()
        conn = _connect()
        if conn is None:
            return False
        try:
            with conn:
                conn.execute(
                    load_query("email_domains/upsert.sql"),
                    (
                        cleaned,
                        str(settings.get("imap_server", "")),
                        int(settings.get("imap_port", 993)),
                        str(settings.get("smtp_server", "")),
                        int(settings.get("smtp_port", 587)),
                        str(settings.get("provider", "custom")),
                        str(source or "custom"),
                        now,
                    ),
                )
        finally:
            conn.close()
        return True
    except Exception as e:
        log_error(str(e), source="email_domains.py:upsert_domain")
        return False


def _fetch_xml(url: str, timeout: int = 8) -> str | None:
    """Fetch an autoconfig XML document.

    Args:
        url: Full URL of the XML document.
        timeout: Timeout in seconds for the request.

    Returns:
        Raw XML text, or ``None`` on failure.

    Raises:
        No exception escapes: failures return ``None``.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return None
        hostname = parsed.hostname or ""
        if hostname.lower() in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return None
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
                return None
        except ValueError:
            try:
                for res in socket.getaddrinfo(hostname, None):
                    resolved_ip = ipaddress.ip_address(res[4][0])
                    if (
                        resolved_ip.is_private
                        or resolved_ip.is_loopback
                        or resolved_ip.is_link_local
                        or resolved_ip.is_multicast
                    ):
                        return None
            except Exception:
                return None
    except Exception:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "synapseForge/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            raw = resp.read()
            return raw.decode("utf-8", errors="replace")
    except Exception:
        return None


def _parse_autoconfig_xml(xml_text: str) -> dict[str, Any] | None:
    """Parse a Thunderbird autoconfig XML into IMAP/SMTP settings.

    Args:
        xml_text: Raw XML text of a ``clientConfig`` document.

    Returns:
        Dict with ``imap_server``, ``imap_port``, ``smtp_server``,
        ``smtp_port`` and ``provider``, or ``None`` when not parseable.

    Raises:
        No exception escapes: failures return ``None``.
    """
    try:
        root = ET.fromstring(xml_text)
        provider = ""
        display = root.find(".//displayShortName")
        if display is not None and display.text:
            provider = display.text.strip().lower()
        imap_host = ""
        imap_port = 993
        smtp_host = ""
        smtp_port = 587
        for server in root.findall(".//incomingServer"):
            if (server.get("type") or "").lower() == "imap":
                host = server.findtext("hostname") or ""
                port = server.findtext("port") or "993"
                if host:
                    imap_host = host.strip()
                    try:
                        imap_port = int(port.strip())
                    except ValueError:
                        imap_port = 993
                    break
        for server in root.findall(".//outgoingServer"):
            if (server.get("type") or "").lower() == "smtp":
                host = server.findtext("hostname") or ""
                port = server.findtext("port") or "587"
                if host:
                    smtp_host = host.strip()
                    try:
                        smtp_port = int(port.strip())
                    except ValueError:
                        smtp_port = 587
                    break
        if not imap_host or not smtp_host:
            return None
        return {
            "imap_server": imap_host,
            "imap_port": imap_port,
            "smtp_server": smtp_host,
            "smtp_port": smtp_port,
            "provider": provider or "custom",
        }
    except Exception:
        return None


def fetch_ispdb(domain: str) -> dict[str, Any] | None:
    """Fetch domain settings from the Thunderbird ISPDB.

    Args:
        domain: Email domain (e.g. ``"gmail.com"``).

    Returns:
        Settings dict, or ``None`` on miss.

    Raises:
        No exception escapes: failures return ``None``.
    """
    try:
        cleaned = (domain or "").strip().lower()
        if not cleaned:
            return None
        xml_text = _fetch_xml(f"https://autoconfig.thunderbird.net/v1.1/{cleaned}")
        if not xml_text:
            return None
        return _parse_autoconfig_xml(xml_text)
    except Exception:
        return None


def fetch_provider_autoconfig(email: str) -> dict[str, Any] | None:
    """Fetch settings from the provider autoconfig URLs.

    Args:
        email: Full email address used as ``emailaddress`` query param.

    Returns:
        Settings dict, or ``None`` when the provider publishes nothing.

    Raises:
        No exception escapes: failures return ``None``.
    """
    try:
        address = (email or "").strip().lower()
        if "@" not in address:
            return None
        domain = address.split("@", 1)[1]
        query = urllib.parse.urlencode({"emailaddress": address})
        urls = [
            f"https://autoconfig.{domain}/mail/config-v1.1.xml?{query}",
            f"https://{domain}/.well-known/autoconfig/mail/config-v1.1.xml",
        ]
        for url in urls:
            xml_text = _fetch_xml(url)
            if not xml_text:
                continue
            settings = _parse_autoconfig_xml(xml_text)
            if settings is not None:
                return settings
        return None
    except Exception:
        return None


def detect_domain_settings(domain: str, email: str = "") -> tuple[dict[str, Any], str]:
    """Detect settings for a domain with DB cache first.

    Order: DB cache → ISPDB → provider autoconfig → presets →
    custom ``mail.<domain>`` fallback. The result is cached in DB.

    Args:
        domain: Email domain to detect.
        email: Optional full email address for provider autoconfig.

    Returns:
        Tuple ``(settings, source)`` where source is one of
        ``db``, ``ispdb``, ``autoconfig``, ``preset`` or ``custom``.

    Raises:
        ValueError: If the domain is empty.
    """
    cleaned = (domain or "").strip().lower()
    if not cleaned:
        raise ValueError("Dominio vacío.")
    cached = get_domain(cleaned)
    if cached is not None and cached.get("imap_server"):
        settings = {
            "imap_server": cached["imap_server"],
            "imap_port": cached["imap_port"],
            "smtp_server": cached["smtp_server"],
            "smtp_port": cached["smtp_port"],
            "provider": cached["provider"],
        }
        return settings, "db"
    ispdb = fetch_ispdb(cleaned)
    if ispdb is not None:
        upsert_domain(cleaned, ispdb, "ispdb")
        return ispdb, "ispdb"
    if email:
        provider_settings = fetch_provider_autoconfig(email)
        if provider_settings is not None:
            upsert_domain(cleaned, provider_settings, "autoconfig")
            return provider_settings, "autoconfig"
    preset = _PRESETS.get(cleaned)
    if preset is not None:
        upsert_domain(cleaned, preset, "preset")
        return dict(preset), "preset"
    fallback = {
        "imap_server": f"mail.{cleaned}",
        "imap_port": 993,
        "smtp_server": f"smtp.{cleaned}",
        "smtp_port": 587,
        "provider": "custom",
    }
    upsert_domain(cleaned, fallback, "custom")
    return fallback, "custom"
