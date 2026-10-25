"""Unit tests for the matching rules (python -m unittest discover -s tests)."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

# Projektwurzel in den Suchpfad legen, damit auch
# `python3 tests/test_filters.py` das Paket `app` findet.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.filters import (  # noqa: E402  (Import nach sys.path-Anpassung)
    filename_matches,
    has_suffix,
    looks_like_pdf,
    parse_address,
    render_remote_name,
    sanitize_filename,
    sender_matches,
    subject_matches,
)


class SenderTests(unittest.TestCase):
    PATTERNS = ("sekretariat@schule.de", "*@grundschulerothenberg.de", "/^info\\+.*@example\\.org$/")

    def test_exact_match_is_case_insensitive(self):
        self.assertTrue(sender_matches("sekretariat@schule.de", self.PATTERNS))
        self.assertTrue(sender_matches("SEKRETARIAT@SCHULE.DE", self.PATTERNS))

    def test_glob_matches_domain(self):
        self.assertTrue(sender_matches("lehrer@grundschulerothenberg.de", self.PATTERNS))

    def test_regex_pattern(self):
        self.assertTrue(sender_matches("info+x@example.org", self.PATTERNS))

    def test_unknown_sender_is_rejected(self):
        self.assertFalse(sender_matches("spam@evil.example", self.PATTERNS))

    def test_empty_allowlist_never_matches(self):
        self.assertFalse(sender_matches("anyone@example.org", ()))

    def test_header_with_display_name(self):
        self.assertEqual(parse_address("Sekretariat <Sekretariat@Schule.de>"), "sekretariat@schule.de")


class SubjectTests(unittest.TestCase):
    def test_regex_is_case_insensitive(self):
        self.assertTrue(subject_matches("Neuer SPEISEPLAN für KW45", r"speiseplan"))

    def test_no_pattern_matches_everything(self):
        self.assertTrue(subject_matches("irgendwas", None))

    def test_non_matching_subject(self):
        self.assertFalse(subject_matches("Rechnung", r"speiseplan"))

    def test_invalid_regex_raises(self):
        with self.assertRaises(ValueError):
            subject_matches("x", "(")


class AttachmentTests(unittest.TestCase):
    def test_suffix_check(self):
        self.assertTrue(has_suffix("Plan.PDF", (".pdf",)))
        self.assertFalse(has_suffix("Plan.docx", (".pdf",)))

    def test_pdf_magic(self):
        self.assertTrue(looks_like_pdf(b"%PDF-1.7\n..."))
        self.assertFalse(looks_like_pdf(b"PK\x03\x04"))  # a zip renamed to .pdf

    def test_sanitize_strips_traversal(self):
        self.assertEqual(sanitize_filename("../../etc/passwd.pdf"), "passwd.pdf")
        self.assertEqual(sanitize_filename("C:\\temp\\Speiseplan.pdf"), "Speiseplan.pdf")
        self.assertEqual(sanitize_filename(".."), "attachment.pdf")

    def test_render_without_template_keeps_name(self):
        self.assertEqual(render_remote_name(None, "Speiseplan.pdf"), "Speiseplan.pdf")

    def test_render_template(self):
        stamp = datetime(2026, 10, 24, 23, 30, 5)
        self.assertEqual(
            render_remote_name("Speiseplan-{date}.pdf", "Plan.pdf", stamp),
            "Speiseplan-2026-10-24.pdf",
        )

    def test_render_rejects_unknown_placeholder(self):
        with self.assertRaises(ValueError):
            render_remote_name("{unbekannt}.pdf", "Plan.pdf")


class FileNameTests(unittest.TestCase):
    def test_pattern_matches_lowercase(self):
        self.assertTrue(filename_matches("speiseplan.pdf", r"^speiseplan.*\.pdf$"))

    def test_pattern_is_case_insensitive(self):
        self.assertTrue(filename_matches("Speiseplan_KW44.PDF", r"^speiseplan.*\.pdf$"))

    def test_other_document_is_rejected(self):
        self.assertFalse(filename_matches("hausordnung.pdf", r"^speiseplan.*\.pdf$"))

    def test_no_pattern_matches_everything(self):
        self.assertTrue(filename_matches("beliebig.pdf", None))

    def test_invalid_pattern_raises(self):
        with self.assertRaises(ValueError):
            filename_matches("x.pdf", "(")


class ReplyTests(unittest.TestCase):
    """Prüft nur den Aufbau der Bestätigungs-Mail (ohne SMTP)."""

    class Stub:
        smtp_from = "m2f@hase10.de"
        imap_user = "m2f@hase10.de"
        reply_subject_prefix = "Re: "
        reply_text = "Die Datei wurde erfolgreich uebertragen."

    def _build(self, subject="Speiseplan", message_id="<abc@example.org>", dry_run=False):
        from app.notify import build_reply

        return build_reply(self.Stub(), "sekretariat@schule.de", subject, message_id, dry_run=dry_run)

    def test_recipient_and_subject(self):
        msg = self._build()
        self.assertEqual(msg["To"], "sekretariat@schule.de")
        self.assertEqual(msg["Subject"], "Re: Speiseplan")

    def test_subject_prefix_not_doubled(self):
        msg = self._build(subject="Re: Speiseplan")
        self.assertEqual(msg["Subject"], "Re: Speiseplan")

    def test_threading_headers(self):
        msg = self._build()
        self.assertEqual(msg["In-Reply-To"], "<abc@example.org>")
        self.assertEqual(msg["References"], "<abc@example.org>")

    def test_body_contains_text(self):
        msg = self._build()
        self.assertIn("erfolgreich uebertragen", msg.get_content())

    def test_dry_run_is_marked(self):
        msg = self._build(dry_run=True)
        self.assertTrue(msg["Subject"].startswith("[TEST] "))
        self.assertIn("Testlauf", msg.get_content())


if __name__ == "__main__":
    unittest.main()
