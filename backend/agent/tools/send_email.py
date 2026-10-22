"""SendEmailMixin — native tool send_email."""

import asyncio
import base64
import logging
import os
import smtplib
from typing import Any
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)


MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
"""Maximum size in bytes of a single binary attachment."""

MAX_TOTAL_ATTACHMENTS_BYTES = 20 * 1024 * 1024
"""Maximum combined size in bytes of all binary attachments."""


class SendEmailMixin:
    """Native tool ``send_email``.

    Sends an email response via SMTP, using STARTTLS on port 587
    or implicit SSL on port 465.
    """

    async def send_email(self, to: str, subject: str, body: str,
                         in_reply_to: str | None = None,
                         attachments: list[dict] | None = None) -> dict[str, Any]:
            """Send an email response via SMTP.

            Reads SMTP credentials from ``.env`` (EMAIL_SMTP_SERVER,
            EMAIL_SMTP_PORT, EMAIL_USER, EMAIL_PASS). The body is markdown and
            is converted to HTML. If ``in_reply_to`` is provided, sets the
            In-Reply-To header for threading. This is a one-shot send — the
            agent calls it on demand; it does not run in the background.
            Port 465 uses implicit SSL (``SMTP_SSL``); any other port uses
            plain SMTP upgraded with STARTTLS.

            Args:
                to: Recipient email address.
                subject: Email subject line.
                body: Email body in markdown format.
                in_reply_to: Optional Message-ID of the original email being replied to.
                attachments: Optional list of binary attachments. Each item must
                    carry exactly one payload source: ``{"filename": str,
                    "content_base64": str}`` with the file content base64-encoded,
                    or ``{"filename": str, "path": str}`` with an absolute file
                    path to read. Example:
                    ``[{"filename": "reporte.pdf", "content_base64": "..."}]``.

            Returns:
                dict with ``{status, message, data, usage}``. On success
                ``data`` holds ``{"to": str, "subject": str,
                "attachments": list[str]}`` with the attached filenames.

            Raises:
                No exception escapes: every failure is returned as an error
                contract dict.
            """
            try:
                to = (to or "").replace("\r", "").replace("\n", "").strip()
                subject = subject or ""
                body = body or ""

                if not to or "@" not in to:
                    return make_error_response(
                        message=f"Direccion de destino invalida: {to!r}",
                        usage=zero_usage(),
                    )

                smtp_server = os.getenv("EMAIL_SMTP_SERVER")
                raw_port = os.getenv("EMAIL_SMTP_PORT", "587")
                email_user = os.getenv("EMAIL_USER")
                email_pass = os.getenv("EMAIL_PASS")

                missing = [
                    name for name, val in (
                        ("EMAIL_SMTP_SERVER", smtp_server),
                        ("EMAIL_USER", email_user),
                        ("EMAIL_PASS", email_pass),
                    ) if not val
                ]
                if missing:
                    return make_error_response(
                        message=f"Faltan variables de entorno: {', '.join(missing)}",
                        usage=zero_usage(),
                    )

                try:
                    smtp_port = int(raw_port)
                    if not (1 <= smtp_port <= 65535):
                        raise ValueError()
                except (ValueError, TypeError) as e:
                    log_error(str(e), source="tools.py:_smtp_send(port)")
                    smtp_port = 587

                has_attachments = bool(attachments)
                attached_names: list[str] = []
                if has_attachments:
                    outer_msg = MIMEMultipart("mixed")
                    msg = MIMEMultipart("alternative")
                    outer_msg.attach(msg)
                else:
                    outer_msg = MIMEMultipart("alternative")
                    msg = outer_msg

                outer_msg["From"] = email_user
                outer_msg["To"] = to
                outer_msg["Subject"] = subject.replace("\n", " ").replace("\r", " ")
                outer_msg["Date"] = formatdate(localtime=True)
                outer_msg["Message-ID"] = make_msgid()

                if in_reply_to:
                    outer_msg["In-Reply-To"] = in_reply_to
                    outer_msg["References"] = in_reply_to

                html_body = self._markdown_to_html(body)
                html_content = (
                    "<html>\n<head></head>\n<body>\n"
                    f"    {html_body}\n"
                    "</body>\n</html>"
                )
                msg.attach(MIMEText(body, "plain", "utf-8"))
                msg.attach(MIMEText(html_content, "html", "utf-8"))

                if has_attachments:
                    if not isinstance(attachments, list):
                        return make_error_response(
                            message="Adjuntos inválidos: debe ser una lista.",
                            usage=zero_usage(),
                        )
                    total_bytes = 0
                    for attachment in attachments:
                        if not isinstance(attachment, dict):
                            return make_error_response(
                                message="Adjunto inválido: cada item debe ser un objeto.",
                                usage=zero_usage(),
                            )
                        has_b64 = isinstance(attachment.get("content_base64"), str)
                        has_path = isinstance(attachment.get("path"), str)
                        if has_b64 == has_path:
                            return make_error_response(
                                message="Adjunto inválido: usá content_base64 o path (solo uno).",
                                usage=zero_usage(),
                            )
                        raw_name = attachment.get("filename") or (
                            os.path.basename(attachment["path"]) if has_path else "attachment"
                        )
                        filename = os.path.basename(str(raw_name)).replace("\r", "").replace("\n", "").strip()
                        if not filename:
                            return make_error_response(
                                message="Adjunto inválido: filename vacío.",
                                usage=zero_usage(),
                            )
                        try:
                            if has_b64:
                                if len(attachment["content_base64"]) > 14 * 1024 * 1024:
                                    return make_error_response(
                                        message=f"Adjunto {filename!r} demasiado grande.",
                                        usage=zero_usage(),
                                    )
                                content = base64.b64decode(attachment["content_base64"], validate=True)
                            else:
                                real_path = os.path.realpath(attachment["path"])
                                if not os.path.isabs(attachment["path"]) or not os.path.isfile(real_path):
                                    return make_error_response(
                                        message=f"Adjunto {filename!r}: ruta inválida.",
                                        usage=zero_usage(),
                                    )
                                if os.path.getsize(real_path) > MAX_ATTACHMENT_BYTES:
                                    return make_error_response(
                                        message=f"Adjunto {filename!r} demasiado grande.",
                                        usage=zero_usage(),
                                    )
                                with open(real_path, "rb") as fh:
                                    content = fh.read()
                        except Exception as e:
                            log_error(str(e), source="tools.py:_smtp_send(attachment)")
                            return make_error_response(
                                message=f"Adjunto {filename!r}: no se pudo leer.",
                                usage=zero_usage(),
                            )
                        if not isinstance(content, (bytes, bytearray)) or not content:
                            return make_error_response(
                                message=f"Adjunto {filename!r} vacío.",
                                usage=zero_usage(),
                            )
                        if len(content) > MAX_ATTACHMENT_BYTES:
                            return make_error_response(
                                message=f"Adjunto {filename!r} demasiado grande.",
                                usage=zero_usage(),
                            )
                        total_bytes += len(content)
                        if total_bytes > MAX_TOTAL_ATTACHMENTS_BYTES:
                            return make_error_response(
                                message="Adjuntos demasiado grandes en total.",
                                usage=zero_usage(),
                            )
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(bytes(content))
                        encoders.encode_base64(part)
                        part.add_header(
                            "Content-Disposition", "attachment", filename=filename
                        )
                        outer_msg.attach(part)
                        attached_names.append(filename)

                def _smtp_send() -> None:
                    """Send the message through the SMTP server.

                    Blocking call meant to run in a worker thread via
                    ``asyncio.to_thread``. Uses ``SMTP_SSL`` on port 465
                    and SMTP with STARTTLS otherwise.

                    Returns:
                        None.

                    Raises:
                        smtplib.SMTPException: If the connection, login or
                            delivery fails. ``server.quit()`` errors are
                            logged and swallowed.
                    """
                    server = None
                    try:
                        if smtp_port == 465:
                            server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=30)
                            server.ehlo()
                        else:
                            server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
                            server.ehlo()
                            server.starttls()
                            server.ehlo()
                        server.login(email_user, email_pass)
                        server.sendmail(email_user, [to], outer_msg.as_string())
                    finally:
                        if server:
                            try:
                                server.quit()
                            except Exception as e:
                                log_error(str(e), source="tools.py:_smtp_send(quit)")
                                pass

                await asyncio.to_thread(_smtp_send)

                return make_success_response(
                    message=f"Email enviado a {to}",
                    data={"to": to, "subject": subject, "attachments": attached_names},
                    usage=zero_usage(),
                )
            except Exception as e:
                logger.exception("Error in send_email: %s", e)
                log_error(str(e), source="tools.py:_smtp_send")
                return make_error_response(
                    message=f"Error enviando email: {e}",
                    usage=zero_usage(),
                )
