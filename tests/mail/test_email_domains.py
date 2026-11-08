"""Tests for email domain cache-first detection."""

from __future__ import annotations

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.agent.utils import email_domains


def test_preset_gmail() -> None:
    """Detect gmail preset without network.

    Returns:
        None.
    """
    settings, source = email_domains.detect_domain_settings("gmail.com", "a@gmail.com")
    assert settings["imap_server"] == "imap.gmail.com"
    assert source in ("db", "ispdb", "preset")


def test_custom_fallback() -> None:
    """Fallback to mail.<domain> for unknown domains.

    Returns:
        None.
    """
    settings, source = email_domains.detect_domain_settings("midominio-test-xyz.com", "")
    assert settings["imap_server"] == "mail.midominio-test-xyz.com"
    assert source in ("db", "preset", "custom")


def test_parse_ispdb_xml() -> None:
    """Parse ISPDB XML sample.

    Returns:
        None.
    """
    xml_text = """<clientConfig version="1.1"><emailProvider id="test"><incomingServer type="imap"><hostname>imap.test.com</hostname><port>993</port></incomingServer><outgoingServer type="smtp"><hostname>smtp.test.com</hostname><port>587</port></outgoingServer></emailProvider></clientConfig>"""
    settings = email_domains._parse_autoconfig_xml(xml_text)
    assert settings is not None
    assert settings["imap_server"] == "imap.test.com"
    assert settings["smtp_server"] == "smtp.test.com"
