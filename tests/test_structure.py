"""Struktur- und Verhaltenstests für das Hauptmodul.

Läuft nur, wenn paramiko verfügbar ist (im .venv oder im Container) - die
übrigen Tests brauchen nur die Standardbibliothek.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

HAS_PARAMIKO = importlib.util.find_spec("paramiko") is not None


@unittest.skipUnless(HAS_PARAMIKO, "paramiko nicht installiert (Tests im .venv ausführen)")
class StructureTests(unittest.TestCase):
    def test_reply_helper_exists(self):
        from app import main as app_main

        # Regression: Aufruf vorhanden, Definition fehlte -> NameError im Betrieb
        self.assertTrue(callable(getattr(app_main, "_send_reply_safely", None)))

    def test_entrypoints_exist(self):
        from app import main as app_main

        for name in ("main", "process_once", "handle_candidate"):
            self.assertTrue(callable(getattr(app_main, name, None)), name)

    def test_transfer_and_mail_exposed(self):
        from app import mail, transfer

        for name in ("connect", "find_candidates", "mark_seen"):
            self.assertTrue(callable(getattr(mail, name, None)), name)
        for name in ("upload", "_load_key"):
            self.assertTrue(callable(getattr(transfer, name, None)), name)


@unittest.skipUnless(HAS_PARAMIKO, "paramiko nicht installiert")
class ReplyHelperTests(unittest.TestCase):
    class Candidate:
        sender = "sekretariat@schule.de"
        subject = "Speiseplan"
        message_id = "<abc@example.org>"

    def test_helper_passes_arguments(self):
        from app import main as app_main

        seen = {}

        def fake(settings, **kwargs):
            seen.update(kwargs)

        original = app_main.send_reply
        app_main.send_reply = fake
        try:
            app_main._send_reply_safely(object(), self.Candidate(), dry_run=True)
        finally:
            app_main.send_reply = original

        self.assertEqual(seen["sender"], "sekretariat@schule.de")
        self.assertEqual(seen["subject"], "Speiseplan")
        self.assertTrue(seen["dry_run"])

    def test_helper_swallows_smtp_errors(self):
        from app import main as app_main

        def boom(*_args, **_kwargs):
            raise RuntimeError("SMTP down")

        original = app_main.send_reply
        app_main.send_reply = boom
        try:
            app_main._send_reply_safely(object(), self.Candidate(), dry_run=False)
        finally:
            app_main.send_reply = original


if __name__ == "__main__":
    unittest.main()
