"""Upload a file to the web server over SFTP (no shell, no external binaries)."""

from __future__ import annotations

import base64
import hashlib
import logging
import posixpath
import uuid
from io import StringIO
from typing import Optional

import paramiko

from .config import ConfigError, Settings

log = logging.getLogger(__name__)


def _load_key(material: str) -> paramiko.PKey:
    """Try the common key types; paramiko raises SSHException on mismatch."""
    last_error: Optional[Exception] = None
    for key_class in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
        try:
            return key_class.from_private_key(StringIO(material))
        except Exception as exc:  # wrong type or encrypted key
            last_error = exc
    raise ConfigError(f"cannot load SSH private key: {last_error}")


class FingerprintPolicy(paramiko.MissingHostKeyPolicy):
    """Accept a host only if its SHA256 fingerprint was pinned in the config."""

    def __init__(self, expected: str) -> None:
        self.expected = expected.replace("SHA256:", "").strip().rstrip("=")

    def missing_host_key(self, client, hostname, key) -> None:
        digest = hashlib.sha256(key.asbytes()).digest()
        actual = base64.b64encode(digest).decode().rstrip("=")
        if actual != self.expected:
            raise paramiko.SSHException(
                f"host key mismatch for {hostname}: expected SHA256:{self.expected}, "
                f"got SHA256:{actual}"
            )


def _connect(settings: Settings) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    if settings.ssh_known_hosts:
        client.load_host_keys(settings.ssh_known_hosts)
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    elif settings.ssh_host_fingerprint:
        client.set_missing_host_key_policy(FingerprintPolicy(settings.ssh_host_fingerprint))
    elif settings.ssh_trust_unknown:
        log.warning("SSH_TRUST_UNKNOWN is set - accepting any host key")
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    else:
        raise ConfigError(
            "host key not verifiable: set SSH_HOST_FINGERPRINT (SHA256:...), "
            "SSH_KNOWN_HOSTS or explicitly SSH_TRUST_UNKNOWN=true"
        )

    client.connect(
        hostname=settings.ssh_host,
        port=settings.ssh_port,
        username=settings.ssh_user,
        pkey=_load_key(settings.key_material),
        look_for_keys=False,
        allow_agent=False,
        timeout=30,
        banner_timeout=30,
        auth_timeout=30,
    )
    return client


def upload(settings: Settings, remote_name: str, payload: bytes) -> str:
    """Write the payload to REMOTE_DIR/remote_name and return the remote path.

    Uploads to a temporary name first so a reader never sees a half-written PDF.
    """
    remote_path = posixpath.join(settings.remote_dir, remote_name)
    temp_path = posixpath.join(settings.remote_dir, f".{remote_name}.{uuid.uuid4().hex}.part")

    client = _connect(settings)
    try:
        with client.open_sftp() as sftp:
            try:
                sftp.stat(settings.remote_dir)
            except IOError as exc:
                raise RuntimeError(f"remote directory {settings.remote_dir} not found") from exc

            with sftp.open(temp_path, "wb") as handle:
                handle.set_pipelined(True)
                handle.write(payload)
            try:
                sftp.posix_rename(temp_path, remote_path)
            except IOError:
                # server without posix-rename extension
                try:
                    sftp.remove(remote_path)
                except IOError:
                    pass
                sftp.rename(temp_path, remote_path)
    finally:
        client.close()

    return remote_path
