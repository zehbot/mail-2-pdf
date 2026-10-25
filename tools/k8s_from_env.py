#!/usr/bin/env python3
"""Erzeugt Kubernetes-Manifeste aus einer .env-Datei.

    python3 tools/k8s_from_env.py private/mail-to-pdf.env private/k8s

Schreibt dorthin:
    configmap.yaml   alle nicht-geheimen Werte
    secret.yaml      IMAP_PASSWORD + privater Schlüssel (Klartext im YAML!)
    deployment.yaml  Kopie von k8s/deployment.yaml

Bewusst ohne PyYAML: die Struktur ist fest, die Datei wird direkt geschrieben.
Die .env wird zeilenweise gelesen (keine Shell-Interpretation), damit
Sonderzeichen im Passwort erhalten bleiben.
"""

from __future__ import annotations

import sys
from pathlib import Path

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


def quote(value: str) -> str:
    """Einzeiliger YAML-String mit escape-ten Anführungszeichen."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2

    env_path = Path(argv[1])
    out_dir = Path(argv[2])
    key_path = env_path.parent / "id_ed25519"

    env = read_env(env_path)
    # Optional dürfen leer bleiben (z. B. SUBJECT_REGEX, ATTACHMENT_NAME_REGEX)
    required = ["IMAP_HOST", "IMAP_USER", "IMAP_PASSWORD", "SSH_HOST", "SSH_USER", "REMOTE_DIR"]
    missing = [k for k in required if not env.get(k)]
    absent = [k for k in CONFIG_KEYS + SECRET_KEYS if k not in env]
    if missing or absent:
        if missing:
            print(f"leere Pflichtwerte: {', '.join(missing)}", file=sys.stderr)
        if absent:
            print(f"fehlende Schlüssel: {', '.join(absent)}", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)

    cm_lines = [
        f"# erzeugt aus {env_path}",
        "",
        "apiVersion: v1",
        "kind: ConfigMap",
        "metadata:",
        "  name: mail-to-pdf-config",
        "  namespace: mail-to-pdf",
        "data:",
    ]
    cm_lines += [f"  {key}: {quote(env[key])}" for key in CONFIG_KEYS]
    (out_dir / "configmap.yaml").write_text("\n".join(cm_lines) + "\n", encoding="utf-8")

    sec_lines = [
        f"# erzeugt aus {env_path}" + (f" + {key_path.name}" if key_path.is_file() else ""),
        "# ACHTUNG: Klartext-Geheimnisse - nicht versionieren, nach dem Anwenden loeschen:",
        "#   shred -u private/k8s/secret.yaml",
        "",
        "apiVersion: v1",
        "kind: Secret",
        "metadata:",
        "  name: mail-to-pdf-secrets",
        "  namespace: mail-to-pdf",
        "type: Opaque",
        "stringData:",
        f"  IMAP_PASSWORD: {quote(env['IMAP_PASSWORD'])}",
    ]
    if key_path.is_file():
        key_text = key_path.read_text(encoding="utf-8").rstrip("\n")
        sec_lines.append("  SSH_PRIVATE_KEY: |")
        sec_lines += [f"    {line}" for line in key_text.splitlines()]
    else:
        print(f"hinweis: {key_path} fehlt - Secret ohne SSH_PRIVATE_KEY", file=sys.stderr)

    (out_dir / "secret.yaml").write_text("\n".join(sec_lines) + "\n", encoding="utf-8")

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
