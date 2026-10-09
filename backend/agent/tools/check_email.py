"""CheckEmailMixin — native tool check_email."""

import imaplib
import logging
import os

from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.agent.utils.email_parser import is_older_than, parse_email, parse_relative_date
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)


class CheckEmailMixin:
    async def check_email(self, folder: str = "INBOX", sender: str | None = None, date: str = "1h", mark_read: bool = True) -> dict:
            """Check the IMAP mailbox for unseen emails and return them parsed.

            Connects via IMAP (SSL), searches for UNSEEN messages in the given
            folder (optionally filtered by sender and age), parses each one, and
            returns the structured results. This is a one-shot check — no polling
            loop. The agent calls this tool on demand; it does not run in the
            background.

            Args:
                folder: IMAP folder to check (default ``"INBOX"``).
                sender: Optional sender address to filter UNSEEN messages.
                date: Relative age filter: ``1h``-``23h`` (hours), ``<n>d``
                    (days), ``<n>m`` (months), ``<n>y`` (years) or ``all``
                    (no date filter). Default ``"1h"``.
                mark_read: When ``True`` (default) fetched messages are marked
                    as read. When ``False`` they are peeked (``BODY.PEEK[]``)
                    and stay unseen.

            Returns:
                dict with ``{status, message, data, usage}``.
                ``data`` contains a list of parsed emails, each with
                ``message_id``, ``sender``, ``subject``, ``date`` (raw header),
                ``date_local`` (server local time), ``body``
                and ``attachments`` (list of filenames).
            """
            try:
                cutoff, date_error = parse_relative_date(date)
                if date_error:
                    return make_error_response(
                        message=date_error,
                        usage=zero_usage(),
                    )

                server = os.getenv("EMAIL_IMAP_SERVER", "")
                port = int(os.getenv("EMAIL_IMAP_PORT", "993"))
                user = os.getenv("EMAIL_USER", "")
                password = os.getenv("EMAIL_PASS", "")

                if not all([server, user, password]):
                    return make_error_response(
                        message=(
                            "Faltan credenciales de email en .env "
                            "(EMAIL_IMAP_SERVER, EMAIL_USER, EMAIL_PASS)."
                        ),
                        usage=zero_usage(),
                    )

                mail = imaplib.IMAP4_SSL(server, port, timeout=15)
                try:
                    mail.login(user, password)
                    typ_select, _ = mail.select(folder)
                    if typ_select != "OK":
                        return make_error_response(
                            message=f"No se pudo seleccionar la carpeta '{folder}'.",
                            usage=zero_usage(),
                        )

                    since = f' SINCE {cutoff.strftime("%d-%b-%Y")}' if cutoff else ""
                    if sender:
                        search_criteria = f'(UNSEEN{since} FROM "{sender}")'
                    else:
                        search_criteria = f"(UNSEEN{since})"

                    typ, data = mail.search(None, search_criteria)
                    if typ != "OK" or not data or not data[0]:
                        return make_success_response(
                            message="No hay mensajes no leidos.",
                            data=[],
                            usage=zero_usage(),
                        )

                    msg_ids = data[0].split()
                    results: list[dict] = []
                    fetch_part = "(BODY[])" if mark_read else "(BODY.PEEK[])"
                    for msg_id in msg_ids:
                        try:
                            typ_fetch, fetch_data = mail.fetch(msg_id, fetch_part)
                            if typ_fetch != "OK" or not fetch_data:
                                continue
                            raw_email = None
                            for item in fetch_data:
                                if isinstance(item, tuple):
                                    raw_email = item[1]
                                    break
                            if not raw_email:
                                continue
                            parsed = parse_email(raw_email)
                            if cutoff and is_older_than(parsed.get("date_parsed"), cutoff):
                                continue
                            results.append({
                                "message_id": parsed.get("message_id", ""),
                                "sender": parsed.get("sender", ""),
                                "subject": parsed.get("subject", ""),
                                "date": parsed.get("date", ""),
                                "date_local": parsed.get("date_local", ""),
                                "body": parsed.get("body", ""),
                                "attachments": [
                                    a.get("filename", "")
                                    for a in parsed.get("attachments", [])
                                ],
                            })
                        except Exception as e:
                            logger.warning("Error procesando mail %s: %s", msg_id, e)
                            log_error(str(e), source="tools.py:check_email")
                            continue
                finally:
                    try:
                        mail.logout()
                    except Exception as e:
                        log_error(str(e), source="tools.py:check_email(logout)")
                        pass

                return make_success_response(
                    message=f"{len(results)} mensaje(s) no leido(s) encontrado(s).",
                    data=results,
                    usage=zero_usage(),
                )
            except Exception as e:
                logger.exception("Error in check_email: %s", e)
                log_error(str(e), source="tools.py:check_email")
                return make_error_response(
                    message=f"Error checking email: {e}",
                    usage=zero_usage(),
                )
