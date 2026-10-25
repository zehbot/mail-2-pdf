"""Tests für das Einlesen der Konfiguration (Listenformate)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import _csv  # noqa: E402


class AllowlistFormatTests(unittest.TestCase):
    def test_comma_separated(self):
        self.assertEqual(_csv("a@b.de,*@example.org"), ("a@b.de", "*@example.org"))

    def test_multiple_lines(self):
        self.assertEqual(_csv("a@b.de\n*@example.org"), ("a@b.de", "*@example.org"))

    def test_block_list_with_dashes(self):
        raw = "  - a@b.de\n  - \"*@example.org\"\n"
        self.assertEqual(_csv(raw), ("a@b.de", "*@example.org"))

    def test_mixed_comma_and_lines(self):
        raw = "a@b.de, *@example.org\n- c@example.org"
        self.assertEqual(_csv(raw), ("a@b.de", "*@example.org", "c@example.org"))

    def test_regex_with_comma_is_kept_whole(self):
        raw = r"/^info\+(a|b),x@example\.org$/"
        self.assertEqual(_csv(raw), (raw,))

    def test_comments_and_blank_lines_are_ignored(self):
        raw = "# Absender\n\na@b.de\n\n"
        self.assertEqual(_csv(raw), ("a@b.de",))

    def test_empty_input(self):
        self.assertEqual(_csv(None), ())
        self.assertEqual(_csv("   "), ())


if __name__ == "__main__":
    unittest.main()
