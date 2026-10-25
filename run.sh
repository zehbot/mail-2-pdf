#!/usr/bin/env bash
# Startet die App mit den Variablen aus private/.env.
#
# Warum nicht `source`? Werte mit Sonderzeichen (z. B. !!, $, Backticks) würden
# von der Shell interpretiert. Hier wird die Datei zeilenweise gelesen und
# unverändert als Umgebungsvariable gesetzt.
set -euo pipefail
cd "$(dirname "$0")"

exec .venv/bin/python - "$@" <<'PY'
import os
import runpy
import sys
from pathlib import Path

env_file = Path("private/.env")
if not env_file.is_file():
    raise SystemExit("private/.env fehlt (Vorlage: .env.example)")

for line in env_file.read_text(encoding="utf-8").splitlines():
    line = line.rstrip("\r")
    if not line.strip() or line.lstrip().startswith("#"):
        continue
    if "=" not in line:
        continue
    key, _, value = line.partition("=")
    os.environ.setdefault(key.strip(), value.strip())

sys.argv = ["app"] + sys.argv[1:]
runpy.run_module("app.main", run_name="__main__")
PY
