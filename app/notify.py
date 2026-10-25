"""Send a short confirmation mail back to the sender."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Optional

from .config import Settings

log = logging.getLogger(__name__)


def build_reply(
    settings: Settings,
    sender: str,
    subject: str,
    message_id: Optional[str],
    dry_run: bool = False,
) -> EmailMessage:
    """Assemble the confirmation message (pure, no network - unit-testable)."""
    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.imap_user
    msg["To"] = sender
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="mail-to-pdf")

    prefix = settings.reply_subject_prefix or "Re: "
    clean_subject = subject if subject.lower().startswith(prefix.strip().lower()) else prefix + subject
    if dry_run:
        clean_subject = "[TEST] " + clean_subject
    msg["Subject"] = clean_subject

    if message_id:
        # keep the answer in the same thread
        msg["In-Reply-To"] = message_id
        msg["References"] = message_id

    body = settings.reply_text
    if dry_run:
        body += "\n\nHinweis: Testlauf - es wurde noch keine Datei uebertragen."
    msg.set_content(body)
    return msg


def send_reply(
    settings: Settings,
    sender: str,
    subject: str,
    message_id: Optional[str],
    dry_run: bool = False,
) -> None:
    """Send the confirmation; raises RuntimeError on SMTP problems."""
    msg = build_reply(settings, sender, subject, message_id, dry_run=dry_run)

    if settings.smtp_ssl:
        client: smtplib.SMTP = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30)
    else:
        client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)
        if settings.smtp_starttls:
            client.starttls()

    try:
        if settings.smtp_user:
            client.login(settings.smtp_user, settings.smtp_password)
        client.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        raise RuntimeError(f"SMTP error: {exc}") from exc
    finally:
        try:
            client.quit()
        except Exception:  # noqa: BLE001
            pass
