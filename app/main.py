"""Entry point: poll the mailbox and push matching PDFs to the web server."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from types import FrameType
from typing import Optional

from . import __version__
from .config import ConfigError, load_settings
from .filters import render_remote_name
from .mail import Candidate, connect, find_candidates, mark_seen
from .state import State
from .transfer import upload

log = logging.getLogger("mail-to-pdf")
_running = True


def _stop(signum: int, _frame: Optional[FrameType]) -> None:
    global _running
    log.info("signal %s received, finishing current cycle", signum)
    _running = False


def process_once(settings, state: State) -> int:
    """One polling cycle. Returns the number of successfully transferred files."""
    client = connect(settings)
    transferred = 0
    try:
        candidates = find_candidates(client, settings)
        for candidate in candidates:
            handle_candidate(settings, state, client, candidate)
            transferred += 1
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001 - closing must never mask errors
            pass
    return transferred


def handle_candidate(settings, state: State, client, candidate: Candidate) -> None:
    if state.is_processed(candidate.message_id):
        log.info("already handled: %s (%s)", candidate.message_id, candidate.subject[:60])
        mark_seen(client, candidate)
        return

    remote_name = render_remote_name(settings.remote_filename, candidate.filename)

    if settings.dry_run:
        log.info(
            "[dry-run] would upload %s (%d bytes) to %s/%s",
            candidate.filename,
            len(candidate.payload),
            settings.remote_dir,
            remote_name,
        )
        return

    try:
        remote_path = upload(settings, remote_name, candidate.payload)
    except Exception as exc:  # noqa: BLE001 - report, keep the message unseen
        attempts = state.bump_attempt(candidate.message_id)
        log.error(
            "upload failed for %s (attempt %d): %s", candidate.message_id, attempts, exc
        )
        return

    state.mark_processed(candidate.message_id)
    mark_seen(client, candidate)
    log.info(
        "uploaded %s -> %s (%d bytes) from %s",
        candidate.filename,
        remote_path,
        len(candidate.payload),
        candidate.sender,
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Watch an IMAP mailbox and forward matching PDF attachments via SFTP."
    )
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="log what would happen without uploading or flagging messages",
    )
    parser.add_argument("--log-level", default=None, help="override LOG_LEVEL")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)

    try:
        settings = load_settings(dry_run=args.dry_run)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    level = (args.log_level or settings.log_level).upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    log.info(
        "mail-to-pdf %s starting (mailbox=%s, target=%s@%s:%s, dry_run=%s)",
        __version__,
        settings.imap_mailbox,
        settings.ssh_user,
        settings.ssh_host,
        settings.ssh_port,
        settings.dry_run,
    )

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    state = State(settings.state_file)

    while _running:
        try:
            count = process_once(settings, state)
            log.debug("cycle finished, %d transfer(s)", count)
        except Exception as exc:  # noqa: BLE001 - never exit on a single failure
            log.error("cycle failed: %s", exc)

        if args.once or not _running:
            break
        for _ in range(settings.poll_interval):
            if not _running:
                break
            time.sleep(1)

    log.info("mail-to-pdf stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
