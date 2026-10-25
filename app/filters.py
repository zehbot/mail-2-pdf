"""Matching rules: sender, subject and attachment checks."""

from __future__ import annotations

import fnmatch
import re
from datetime import datetime
from pathlib import PurePosixPath
from typing import Optional

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def parse_address(raw: str) -> str:
    """Extract the bare address from 'Name <mail@host>' style headers."""
    match = re.search(r"<([^>]+)>", raw)
    return (match.group(1) if match else raw).strip().lower()


def _pattern_matches(address: str, pattern: str) -> bool:
    if len(pattern) > 2 and pattern.startswith("/") and pattern.endswith("/"):
        return re.search(pattern[1:-1], address, re.IGNORECASE) is not None
    if any(ch in pattern for ch in "*?[]"):
        return fnmatch.fnmatchcase(address, pattern.lower())
    return address == pattern.lower()


def sender_matches(address: str, patterns: tuple[str, ...]) -> bool:
    """True when the address is explicitly allowed.

    Patterns may be exact addresses, globs (*@example.org) or /regex/.
    Matching is case-insensitive; an empty allowlist never matches - callers
    rely on fail-closed behaviour.
    """
    if not patterns:
        return False
    normalized = address.strip().lower()
    return any(_pattern_matches(normalized, pattern) for pattern in patterns)


def subject_matches(subject: str, pattern: Optional[str]) -> bool:
    """Case-insensitive regex search; an empty pattern matches everything."""
    if not pattern:
        return True
    try:
        return re.search(pattern, subject, re.IGNORECASE) is not None
    except re.error as exc:  # invalid config should not crash the loop
        raise ValueError(f"invalid SUBJECT_REGEX {pattern!r}: {exc}") from exc


def has_suffix(filename: str, suffixes: tuple[str, ...]) -> bool:
    lowered = filename.lower()
    return any(lowered.endswith(suffix) for suffix in suffixes)


def looks_like_pdf(payload: bytes) -> bool:
    """Cheap content check so a renamed .txt cannot pass as PDF."""
    return payload[:5] == b"%PDF-"


def sanitize_filename(name: str) -> str:
    """Strip directories, control characters and dangerous prefixes."""
    base = PurePosixPath(name.replace("\\", "/")).name
    cleaned = _UNSAFE.sub("_", base).strip("._-")
    if not cleaned:
        cleaned = "attachment.pdf"
    return cleaned[:120]


def render_remote_name(
    template: Optional[str],
    original: str,
    now: Optional[datetime] = None,
) -> str:
    """Build the target filename.

    Template placeholders: {stem}, {suffix}, {date}, {time}, {timestamp}.
    Without a template the sanitized original name is used.
    """
    safe_original = sanitize_filename(original)
    if not template:
        return safe_original

    stem, dot, suffix = safe_original.rpartition(".")
    if not dot:
        stem, suffix = safe_original, ""
    stamp = now or datetime.now()
    values = {
        "stem": stem,
        "suffix": suffix,
        "date": stamp.strftime("%Y-%m-%d"),
        "time": stamp.strftime("%H%M%S"),
        "timestamp": stamp.strftime("%Y%m%d-%H%M%S"),
    }
    try:
        rendered = template.format(**values)
    except (KeyError, IndexError) as exc:
        raise ValueError(f"invalid REMOTE_FILENAME template {template!r}: {exc}") from exc
    return sanitize_filename(rendered)
