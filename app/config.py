"""Configuration from environment variables (12-factor, k3s friendly)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _get(name: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        if required:
            raise ConfigError(f"environment variable {name} is required")
        return default
    return value.strip()


def _get_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def _csv(raw: Optional[str]) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    """All runtime settings, read once at startup."""

    # Mailbox (IMAP)
    imap_host: str
    imap_port: int
    imap_ssl: bool
    imap_starttls: bool
    imap_user: str
    imap_password: str
    imap_mailbox: str
    poll_interval: int

    # Filtering
    sender_patterns: tuple[str, ...]
    subject_regex: Optional[str]
    attachment_suffixes: tuple[str, ...]
    max_attachment_bytes: int

    # Target (SSH/SFTP)
    ssh_host: str
    ssh_port: int
    ssh_user: str
    ssh_private_key: Optional[str]
    ssh_private_key_file: Optional[str]
    ssh_host_fingerprint: Optional[str]
    ssh_known_hosts: Optional[str]
    ssh_trust_unknown: bool
    remote_dir: str
    remote_filename: Optional[str]

    # Runtime
    state_file: str
    dry_run: bool
    log_level: str

    @property
    def key_material(self) -> str:
        """Private key as text, either inline (env) or from a mounted file."""
        if self.ssh_private_key_file:
            try:
                with open(self.ssh_private_key_file, "r", encoding="utf-8") as handle:
                    return handle.read()
            except OSError as exc:
                raise ConfigError(
                    f"cannot read SSH_PRIVATE_KEY_FILE {self.ssh_private_key_file}: {exc}"
                ) from exc
        if not self.ssh_private_key:
            raise ConfigError("SSH_PRIVATE_KEY or SSH_PRIVATE_KEY_FILE is required")
        # Kubernetes/env often carries the key with literal \n escapes
        return self.ssh_private_key.replace("\\n", "\n")


def load_settings(dry_run: bool = False) -> Settings:
    """Read and validate all settings from the environment."""
    imap_ssl = _get_bool("IMAP_SSL", True)
    starttls = _get_bool("IMAP_STARTTLS", False)
    if imap_ssl and starttls:
        raise ConfigError("set either IMAP_SSL or IMAP_STARTTLS, not both")

    sender_patterns = _csv(_get("SENDER_ALLOWLIST"))
    if not sender_patterns:
        raise ConfigError("SENDER_ALLOWLIST must list at least one sender pattern")

    suffix_raw = _get("ATTACHMENT_SUFFIXES", ".pdf") or ".pdf"
    suffixes = tuple(
        s.lower() if s.startswith(".") else f".{s.lower()}" for s in _csv(suffix_raw)
    )

    return Settings(
        imap_host=_get("IMAP_HOST", required=True) or "",
        imap_port=_get_int("IMAP_PORT", 993),
        imap_ssl=imap_ssl,
        imap_starttls=starttls,
        imap_user=_get("IMAP_USER", required=True) or "",
        imap_password=_get("IMAP_PASSWORD", required=True) or "",
        imap_mailbox=_get("IMAP_MAILBOX", "INBOX") or "INBOX",
        poll_interval=max(10, _get_int("POLL_INTERVAL", 60)),
        sender_patterns=sender_patterns,
        subject_regex=_get("SUBJECT_REGEX"),
        attachment_suffixes=suffixes,
        max_attachment_bytes=_get_int("MAX_ATTACHMENT_MB", 25) * 1024 * 1024,
        ssh_host=_get("SSH_HOST", required=True) or "",
        ssh_port=_get_int("SSH_PORT", 22),
        ssh_user=_get("SSH_USER", required=True) or "",
        ssh_private_key=_get("SSH_PRIVATE_KEY"),
        ssh_private_key_file=_get("SSH_PRIVATE_KEY_FILE"),
        ssh_host_fingerprint=_get("SSH_HOST_FINGERPRINT"),
        ssh_known_hosts=_get("SSH_KNOWN_HOSTS"),
        ssh_trust_unknown=_get_bool("SSH_TRUST_UNKNOWN", False),
        remote_dir=_get("REMOTE_DIR", required=True) or "",
        remote_filename=_get("REMOTE_FILENAME"),
        state_file=_get("STATE_FILE", "/tmp/mail-to-pdf-state.json") or "/tmp/mail-to-pdf-state.json",
        dry_run=dry_run or _get_bool("DRY_RUN", False),
        log_level=(_get("LOG_LEVEL", "INFO") or "INFO").upper(),
    )
