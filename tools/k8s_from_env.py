#!/usr/bin/env python3
"""Erzeugt Kubernetes-Manifeste aus einer .env-Datei.

    python3 tools/k8s_from_env.py private/mail-to-pdf.env private/k8s

Schreibt dorthin:
    configmap.yaml   alle nicht-geheimen Werte
    secret.yaml      IMAP_PASSWORD + privater Schlüssel (Klartext im YAML!)
    deployment.yaml  Kopie von k8s/deployment.yaml

Die .env wird zeilenweise gelesen (keine Shell-Interpretation), damit
Sonderzeichen im Passwort erhalten bleiben.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

CONFIG_KEYS = [
    "IMAP_HOST", "IMAP_PORT", "IMAP_SSL", "IMAP_USER", "IMAP_MAILBOX", "POLL_INTERVAL",
    "SENDER_ALLOWLIST", "SUBJECT_REGEX", "ATTACHMENT_SUFFIXES", "ATTACHMENT_NAME_REGEX",
    "MAX_ATTACHMENT_MB",
    "SSH_HOST", "SSH_PORT", "SSH_USER", "REMOTE_DIR", "REMOTE_FILENAME",
    "SSH_HOST_FINGERPRINT",
    "REPLY_ENABLED", "REPLY_ON_DRY_RUN", "REPLY_TEXT",
    "SMTP_HOST", "SMTP_PORT", "SMTP_STARTTLS", "SMTP_SSL",
    "STATE_FILE", "LOG_LEVEL",
]
SECRET_KEYS = ["IMAP_PASSWORD"]


def read_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        data[key.strip()] = value.strip()
    return data


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2

    env_path = Path(argv[1])
    out_dir = Path(argv[2])
    key_path = Path(argv[1]).parent / "id_ed25519"

    env = read_env(env_path)
    missing = [k for k in CONFIG_KEYS + SECRET_KEYS if not env.get(k)]
    if missing:
        print(f"fehlende Werte: {', '.join(missing)}", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)

    configmap = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "mail-to-pdf-config", "namespace": "mail-to-pdf"},
        "data": {k: env[k] for k in CONFIG_KEYS},
    }
    secret = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": "mail-to-pdf-secrets", "namespace": "mail-to-pdf"},
        "type": "Opaque",
        "stringData": {"IMAP_PASSWORD": env["IMAP_PASSWORD"]},
    }
    if key_path.is_file():
        secret["stringData"]["SSH_PRIVATE_KEY"] = key_path.read_text(encoding="utf-8")
    else:
        print(f"hinweis: {key_path} fehlt - Secret ohne SSH_PRIVATE_KEY", file=sys.stderr)

    def dump(obj, header: str) -> None:
        return header + yaml.safe_dump(obj, sort_keys=False, allow_unicode=True,
                                       default_flow_style=False)

    (out_dir / "configmap.yaml").write_text(
        dump(configmap, f"# erzeugt aus {env_path}\n\n"), encoding="utf-8")
    (out_dir / "secret.yaml").write_text(
        dump(secret,
             f"# erzeugt aus {env_path} + {key_path.name}\n"
             "# ACHTUNG: Klartext-Geheimnisse - nicht versionieren, nach dem\n"
             "# Anwenden loeschen (shred -u).\n\n"), encoding="utf-8")

    deployment_src = Path(__file__).resolve().parents[1] / "k8s" / "deployment.yaml"
    (out_dir / "deployment.yaml").write_text(
        "# Kopie von k8s/deployment.yaml\n\n" + deployment_src.read_text(encoding="utf-8"),
        encoding="utf-8")

    for name in ("configmap.yaml", "secret.yaml", "deployment.yaml"):
        (out_dir / name).chmod(0o600)

    print(f"geschrieben nach {out_dir}: configmap.yaml, secret.yaml, deployment.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
