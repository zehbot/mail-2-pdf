"""Unit tests for the matching rules (python -m unittest discover -s tests)."""

from __future__ import annotations

import unittest
from datetime import datetime

from app.filters import (
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


if __name__ == "__main__":
    unittest.main()
