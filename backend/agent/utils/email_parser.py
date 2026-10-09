"""Email parser utilities for processing raw RFC 2822 email messages.

Parses raw email bytes from IMAP into structured Python objects.
Handles multipart messages, MIME headers, and attachments.
"""

import email
import email.message
from email.header import decode_header
from email.utils import parsedate_to_datetime
import calendar
import os
import re
import sys
from datetime import datetime, timedelta, timezone

_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


from backend.agent.utils.error_logger import log_error


def decode_mime_header(value: str | None) -> str:
    """Decode a MIME encoded-header into plain text.

    Args:
        value: Raw header value (may be encoded with =?charset?).

    Returns:
        Decoded plain text string.
    """
    if not value:
        return ""
    parts = decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            try:
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            except (LookupError, UnicodeDecodeError) as e:
                log_error(str(e), source="email_parser.py:decode_mime_header")
                decoded.append(part.decode("utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded).strip()


def parse_email(raw_bytes: bytes) -> dict:
    """Parse raw email bytes into a structured dictionary.

    Extracts sender, subject, date, body (plain text), and attachment info
    from a raw RFC 2822 message.

    Args:
        raw_bytes: Raw email bytes as returned by IMAP BODY[] fetch.

    Returns:
        Dictionary with keys:
            - message_id (str)
            - sender (str)
            - subject (str)
            - date (str)
            - date_parsed (datetime or None)
            - body (str): plain text body
            - attachments (list[dict]): each with filename, size_bytes, content_type, data
    """
    msg = email.message_from_bytes(raw_bytes)

    # ── Headers ──
    message_id = msg.get("Message-ID", "")
    sender = msg.get("From", "")
    subject = decode_mime_header(msg.get("Subject", ""))
    date_str = msg.get("Date", "")

    try:
        date_parsed = parsedate_to_datetime(date_str) if date_str else None
    except (ValueError, TypeError) as e:
        log_error(str(e), source="email_parser.py:parse_email(date)")
        date_parsed = None

    # ── Body (plain text) ──
    body = _extract_plain_text(msg)

    # ── Attachments ──
    attachments = _extract_attachments(msg)

    return {
        "message_id": message_id,
        "sender": sender,
        "subject": subject,
        "date": date_str,
        "date_parsed": date_parsed,
        "body": body,
        "attachments": attachments,
    }


def _shift_months(moment: datetime, months: int) -> datetime:
    """Shift a datetime by a number of months, clamping the day.

    Args:
        moment: Reference datetime.
        months: Months to shift (negative = past).

    Returns:
        Shifted datetime with the day clamped to the target month length.
    """
    total = moment.year * 12 + (moment.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    last_day = calendar.monthrange(year, month)[1]
    return moment.replace(year=year, month=month, day=min(moment.day, last_day))


def parse_relative_date(value: str | None) -> tuple[datetime | None, str | None]:
    """Parse a relative date filter into a UTC cutoff.

    Accepted values: ``1h``-``23h`` (hours), ``<n>d`` (days),
    ``<n>m`` (months), ``<n>y`` (years) or ``all`` (no date filter).

    Args:
        value: Raw filter value (defaults to ``1h`` when empty).

    Returns:
        Tuple ``(cutoff, error)``: ``cutoff`` is a timezone-aware UTC
        datetime (``None`` means no date filter); ``error`` is a friendly
        message when the value is invalid (``None`` when valid).
    """
    raw = (value or "1h").strip().lower()
    if raw == "all":
        return None, None
    match = re.match(r"^(\d+)([hdmy])$", raw)
    if not match:
        return None, (
            "Filtro de fecha inválido. Usá '1h'-'23h', '<n>d', '<n>m', '<n>y' o 'all'."
        )
    amount = int(match.group(1))
    unit = match.group(2)
    if amount < 1:
        return None, (
            "Filtro de fecha inválido. Usá '1h'-'23h', '<n>d', '<n>m', '<n>y' o 'all'."
        )
    if unit == "h" and amount > 23:
        return None, (
            "El rango en horas es de 1h a 23h. Para más, usá días ('1d', ...)."
        )
    now = datetime.now(timezone.utc)
    if unit == "h":
        return now - timedelta(hours=amount), None
    if unit == "d":
        return now - timedelta(days=amount), None
    if unit == "m":
        return _shift_months(now, -amount), None
    return _shift_months(now, -amount * 12), None


def is_older_than(value: datetime | None, cutoff: datetime) -> bool:
    """Check whether an email date is older than the cutoff.

    Naive datetimes are assumed to be UTC.

    Args:
        value: Email date (``None`` means unknown, never older).
        cutoff: Cutoff datetime.

    Returns:
        True when ``value`` is older than ``cutoff``.
    """
    if value is None:
        return False
    seen = value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    limit = cutoff.astimezone(timezone.utc).replace(tzinfo=None) if cutoff.tzinfo else cutoff
    return seen < limit


def _extract_plain_text(msg: email.message.Message) -> str:
    """Extract plain text body from an email message.

    Args:
        msg: Parsed email.message.Message object.

    Returns:
        Plain text body string, empty if not found.
    """
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="replace")
        return ""
    payload = msg.get_payload(decode=True)
    if payload:
        return payload.decode("utf-8", errors="replace")
    return ""


def _extract_attachments(msg: email.message.Message) -> list[dict]:
    """Extract attachment info and binary data from an email message.

    Args:
        msg: Parsed email.message.Message object.

    Returns:
        List of dictionaries with filename, size_bytes, content_type, and data (bytes).
    """
    attachments = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = part.get_filename()
        if not filename:
            continue
        decoded_name = decode_mime_header(filename)
        payload = part.get_payload(decode=True)
        attachments.append({
            "filename": decoded_name,
            "size_bytes": len(payload) if payload else 0,
            "content_type": part.get_content_type(),
            "data": payload,
        })
    return attachments


if __name__ == '__main__':
    print('email_parser module — parseo de correos RFC 2822.')
    print('  parse_raw_email(data), extract_attachments(msg) disponibles.')
