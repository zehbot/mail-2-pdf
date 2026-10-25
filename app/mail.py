"""IMAP access: find unseen messages matching the configured rules."""

from __future__ import annotations

import email
import imaplib
import logging
from dataclasses import dataclass
from email import policy
from email.header import decode_header, make_header
from typing import Iterator, Optional

from .config import Settings
from .filters import (
    filename_matches,
    has_suffix,
    looks_like_pdf,
    parse_address,
    sender_matches,
    subject_matches,
)

log = logging.getLogger(__name__)


@dataclass
class Candidate:
    """A message that passed every filter and carries a usable attachment."""

    uid: str
    message_id: str
    sender: str
    subject: str
    filename: str
    payload: bytes


def _decode(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value))).strip()
    except Exception:  # malformed headers must not kill the loop
        return value.strip()


def connect(settings: Settings) -> imaplib.IMAP4:
    """Open an authenticated IMAP connection (implicit TLS or STARTTLS)."""
    if settings.imap_ssl:
        client: imaplib.IMAP4 = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
    else:
        client = imaplib.IMAP4(settings.imap_host, settings.imap_port)
        if settings.imap_starttls:
            client.starttls()
    client.login(settings.imap_user, settings.imap_password)
    return client


def _iter_attachments(message: email.message.EmailMessage) -> Iterator[tuple[str, bytes]]:
    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = part.get_filename()
        if not filename:
            continue
        decoded_name = _decode(filename)
        payload = part.get_payload(decode=True)
        if payload:
            yield decoded_name, payload


def find_candidates(client: imaplib.IMAP4, settings: Settings) -> list[Candidate]:
    """Collect unseen messages that match sender, subject and attachment rules."""
    status, _ = client.select(settings.imap_mailbox, readonly=False)
    if status != "OK":
        raise RuntimeError(f"cannot select mailbox {settings.imap_mailbox!r}")

    status, data = client.search(None, "UNSEEN")
    if status != "OK":
        raise RuntimeError("IMAP search failed")

    numbers = data[0].split() if data and data[0] else []

    found: list[Candidate] = []
    for number in numbers:
        status, fetched = client.fetch(number, "(RFC822)")
        if status != "OK" or not fetched or not isinstance(fetched[0], tuple):
            log.warning("could not fetch message %s", number.decode(errors="replace"))
            continue

        raw = fetched[0][1]
        message = email.message_from_bytes(raw, policy=policy.default)
        sender = parse_address(_decode(message.get("From", "")))
        subject = _decode(message.get("Subject", ""))
        message_id = (message.get("Message-ID") or "").strip()

        if not sender_matches(sender, settings.sender_patterns):
            log.debug("skip %s: sender not allowed (%s)", message_id or "?", sender)
            continue
        try:
            if not subject_matches(subject, settings.subject_regex):
                log.debug("skip %s: subject does not match", message_id or "?")
                continue
        except ValueError as exc:
            log.error("%s", exc)
            continue

        for filename, payload in _iter_attachments(message):
            if not has_suffix(filename, settings.attachment_suffixes):
                log.debug("skip attachment %s: suffix not allowed", filename)
                continue
            try:
                if not filename_matches(filename, settings.attachment_name_regex):
                    log.debug("skip attachment %s: name does not match", filename)
                    continue
            except ValueError as exc:
                log.error("%s", exc)
                continue
            if len(payload) > settings.max_attachment_bytes:
                log.warning(
                    "skip attachment %s: %d bytes exceed limit", filename, len(payload)
                )
                continue
            if filename.lower().endswith(".pdf") and not looks_like_pdf(payload):
                log.warning("skip attachment %s: not a PDF (magic bytes)", filename)
                continue
            found.append(
                Candidate(
                    uid=number.decode(),
                    message_id=message_id or f"uid:{number.decode()}",
                    sender=sender,
                    subject=subject,
                    filename=filename,
                    payload=payload,
                )
            )
    log.info(
        "%d ungelesene Nachricht(en) geprüft, %d Treffer",
        len(numbers),
        len(found),
    )
    return found


def mark_seen(client: imaplib.IMAP4, candidate: Candidate) -> None:
    """Flag the message as seen so it is not processed twice."""
    client.store(candidate.uid, "+FLAGS", "\\Seen")
