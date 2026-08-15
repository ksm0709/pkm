"""SMTP delivery for feedback captured by the web app."""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import parseaddr

_logger = logging.getLogger(__name__)

DEFAULT_RECIPIENT = "ksm07091@gmail.com"


@dataclass(frozen=True)
class FeedbackEmailResult:
    """Outcome returned to the web route without exposing SMTP credentials."""

    status: str
    recipient: str | None = None


def _setting(name: str) -> str:
    return os.environ.get(name, "").strip()


def _enabled(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _address(value: str) -> str | None:
    if "\r" in value or "\n" in value:
        return None
    _, address = parseaddr(value)
    return address if address and "@" in address else None


def send_feedback_email(
    *,
    vault_name: str,
    title: str,
    description: str,
    feedback_type: str,
    created_at: str,
) -> FeedbackEmailResult:
    """Send one feedback record through configured SMTP, without raising on failure."""
    host = _setting("PKM_FEEDBACK_SMTP_HOST")
    username = _setting("PKM_FEEDBACK_SMTP_USERNAME")
    password = _setting("PKM_FEEDBACK_SMTP_PASSWORD")
    recipient = _setting("PKM_FEEDBACK_EMAIL_TO") or DEFAULT_RECIPIENT
    sender = _setting("PKM_FEEDBACK_EMAIL_FROM") or username

    if not host or not username or not password:
        return FeedbackEmailResult(status="not_configured")
    recipient_address = _address(recipient)
    sender_address = _address(sender)
    if recipient_address is None or sender_address is None:
        _logger.error("Feedback email settings contain an invalid sender or recipient")
        return FeedbackEmailResult(status="failed")

    try:
        port = int(_setting("PKM_FEEDBACK_SMTP_PORT") or "587")
    except ValueError:
        _logger.error("PKM_FEEDBACK_SMTP_PORT must be an integer")
        return FeedbackEmailResult(status="failed")

    message = EmailMessage()
    message["Subject"] = f"[PKM feedback] {title}"
    message["From"] = sender_address
    message["To"] = recipient_address
    message.set_content(
        "\n".join(
            [
                "A new PKM web feedback entry was saved.",
                "",
                f"Vault: {vault_name}",
                f"Type: {feedback_type}",
                f"Created: {created_at}",
                "",
                f"Title: {title}",
                "",
                description,
            ]
        )
    )

    try:
        if _enabled(_setting("PKM_FEEDBACK_SMTP_USE_SSL")):
            with smtplib.SMTP_SSL(
                host, port, timeout=10, context=ssl.create_default_context()
            ) as smtp:
                smtp.login(username, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                if not _setting("PKM_FEEDBACK_SMTP_STARTTLS") or _enabled(
                    _setting("PKM_FEEDBACK_SMTP_STARTTLS")
                ):
                    smtp.starttls(context=ssl.create_default_context())
                smtp.login(username, password)
                smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        _logger.warning("Feedback email delivery failed: %s", error)
        return FeedbackEmailResult(status="failed")

    return FeedbackEmailResult(status="sent", recipient=recipient_address)
