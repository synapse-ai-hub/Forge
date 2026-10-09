"""SendEmailMixin — native tool send_email."""

import asyncio
import logging
import os
import re
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)


class SendEmailMixin:
    async def send_email(self, to: str, subject: str, body: str,
                             in_reply_to: str | None = None,
                             attachments: list[dict] | None = None) -> dict:
            """Send an email response via SMTP with STARTTLS.

            Reads SMTP credentials from ``.env`` (EMAIL_SMTP_SERVER,
            EMAIL_SMTP_PORT, EMAIL_USER, EMAIL_PASS). The body is markdown and
            is converted to HTML. If ``in_reply_to`` is provided, sets the
            In-Reply-To header for threading. This is a one-shot send — the
            agent calls it on demand; it does not run in the background.

            Args:
                to: Recipient email address.
                subject: Email subject line.
                body: Email body in markdown format.
                in_reply_to: Optional Message-ID of the original email being replied to.
                attachments: Optional list of ``{"filename": str, "content": bytes}`` dicts.

            Returns:
                dict with ``{status, message, data, usage}``.
            """
            try:
            

                to = (to or "").strip()
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
                    for attachment in attachments:
                        if not isinstance(attachment, dict):
                            continue
                        filename = attachment.get("filename", "attachment")
                        content = attachment.get("content")
                        if content is None:
                            continue
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(content)
                        encoders.encode_base64(part)
                        part.add_header(
                            "Content-Disposition", "attachment", filename=filename
                        )
                        outer_msg.attach(part)

                def _smtp_send() -> None:
                    server = None
                    try:
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
                    data={"to": to, "subject": subject},
                    usage=zero_usage(),
                )
            except Exception as e:
                logger.exception("Error in send_email: %s", e)
                log_error(str(e), source="tools.py:_smtp_send")
                return make_error_response(
                    message=f"Error enviando email: {e}",
                    usage=zero_usage(),
                )
