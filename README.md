# mail2web

Kleiner Dienst, der ein E-Mail-Postfach überwacht und passende **PDF-Anhänge**
automatisch auf einen Webserver überträgt.

Gedacht für wiederkehrende Dokumente, die per Mail eintreffen – zum Beispiel der
wöchentliche Speiseplan, der als `Speiseplan.pdf` im Web-Verzeichnis landen soll.

```
IMAP-Postfach ──► Filter (Absender, Betreff, Anhang) ──► SFTP ──► /var/www/…/dokumente/
```

## Verhalten

- Prüft alle `POLL_INTERVAL` Sekunden die **ungesehenen** Nachrichten im Postfach.
- Verarbeitet nur Mails, die **alle** Filter bestehen:
  1. Absender steht in `SENDER_ALLOWLIST` (exakt, `*@domain` oder `/regex/`)
  2. Betreff passt auf `SUBJECT_REGEX` (optional)
  3. Es hängt eine Datei mit erlaubter Endung an (Standard: `.pdf`)
  4. Die Datei beginnt wirklich mit `%PDF-` (kein umbenanntes Word-Dokument)
  5. Größe ≤ `MAX_ATTACHMENT_MB`
- Lädt den Anhang per **SFTP** hoch, schreibt erst in eine `.part`-Datei und
  benennt sie atomar um – Besucher sehen nie eine halbe PDF.
- Markiert die Mail danach als gelesen (`\Seen`) und merkt sich die Message-ID
  in einer kleinen State-Datei. Schlägt der Upload fehl, bleibt die Mail
  ungelesen und wird im nächsten Zyklus erneut versucht.
- Bricht nie wegen einer einzelnen kaputten Mail ab: Fehler werden geloggt, der
  nächste Zyklus läuft weiter.

## Sicherheitsmodell

| Thema | Umsetzung |
|---|---|
| Absender | **fail-closed** – ohne Treffer in `SENDER_ALLOWLIST` passiert nichts |
| Anhang | Endung **und** Magic-Bytes-Prüfung, Größenlimit |
| Dateiname | bereinigt (keine Pfadwechsel, kein `../`), Länge begrenzt |
| Übertragung | SFTP über paramiko, kein `scp`-Binary, keine Shell |
| Host-Key | Pflicht: `SSH_HOST_FINGERPRINT` oder `SSH_KNOWN_HOSTS`; `SSH_TRUST_UNKNOWN=true` nur bewusst |
| Schlüssel | nur im Speicher (Env oder gemountetes Secret), nie auf Platte |
| Rechte im Container | non-root, read-only Root-Dateisystem, alle Capabilities gedroppt |

## Konfiguration

Alles über Umgebungsvariablen (12-Factor, passt zu k3s).

### Postfach

| Variable | Pflicht | Standard | Bedeutung |
|---|---|---|---|
| `IMAP_HOST` | ja | – | Servename, z. B. `imap.example.org` |
| `IMAP_PORT` | nein | `993` | Port |
| `IMAP_SSL` | nein | `true` | implizites TLS (Port 993) |
| `IMAP_STARTTLS` | nein | `false` | STARTTLS auf Port 143 (nicht mit `IMAP_SSL` kombinieren) |
| `IMAP_USER` | ja | – | Benutzername |
| `IMAP_PASSWORD` | ja | – | Passwort (aus Secret) |
| `IMAP_MAILBOX` | nein | `INBOX` | zu überwachender Ordner |
| `POLL_INTERVAL` | nein | `60` | Sekunden zwischen den Durchläufen (min. 10) |

### Filter

| Variable | Pflicht | Standard | Bedeutung |
|---|---|---|---|
| `SENDER_ALLOWLIST` | ja | – | Kommagetrennt: `a@b.de`, `*@schule.de`, `/^info\+.*@x\.de$/` |
| `SUBJECT_REGEX` | nein | – | Regex auf den Betreff, case-insensitiv |
| `ATTACHMENT_SUFFIXES` | nein | `.pdf` | erlaubte Endungen |
| `MAX_ATTACHMENT_MB` | nein | `25` | Größenlimit pro Datei |

### Zielserver

| Variable | Pflicht | Standard | Bedeutung |
|---|---|---|---|
| `SSH_HOST` | ja | – | Webserver |
| `SSH_PORT` | nein | `22` | SSH-Port |
| `SSH_USER` | ja | – | Benutzer, der in `REMOTE_DIR` schreiben darf |
| `SSH_PRIVATE_KEY` | * | – | Key-Inhalt; `\n`-Escapes werden aufgelöst |
| `SSH_PRIVATE_KEY_FILE` | * | – | alternativ: Pfad zu einem gemounteten Secret |
| `SSH_HOST_FINGERPRINT` | * | – | `SHA256:…` des Servers (`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`) |
| `SSH_KNOWN_HOSTS` | * | – | alternativ: Pfad zu einer known_hosts-Datei |
| `SSH_TRUST_UNKNOWN` | nein | `false` | akzeptiert jeden Host-Key (nur zum Testen) |
| `REMOTE_DIR` | ja | – | Zielordner, z. B. `/var/www/gsr-html-web/dokumente` |
| `REMOTE_FILENAME` | nein | – | fester Zielname bzw. Vorlage mit `{date}`, `{time}`, `{timestamp}`, `{stem}`, `{suffix}` |

\* genau eines der drei Host-Key-Verfahren beziehungsweise einer der beiden
Key-Eingaben.

### Laufzeit

| Variable | Standard | Bedeutung |
|---|---|---|
| `STATE_FILE` | `/tmp/mail2web-state.json` | Merker für verarbeitete Nachrichten |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `DRY_RUN` | `false` | wie `--dry-run` |

## Lokal testen

```bash
cd mail2web
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v      # Filter-Tests

cp .env.example .env                          # Werte eintragen
python -m app.main --once --dry-run           # ein Durchlauf, nichts wird hochgeladen
python -m app.main                            # Dauerbetrieb
```

`--dry-run` verbindet sich mit dem Postfach und zeigt, **was** übertragen würde,
lädt aber nichts hoch und markiert keine Mail als gelesen.

## Container

```bash
docker build -t mail2web:0.1.0 .
docker run --rm --env-file .env mail2web:0.1.0 --once --dry-run
```

## k3s

```bash
kubectl create namespace mail2web

# Zugangsdaten aus Dateien - nichts landet in der Shell-History
kubectl -n mail2web create secret generic mail2web-secrets \
  --from-literal=IMAP_PASSWORD='…' \
  --from-file=SSH_PRIVATE_KEY=/pfad/zum/id_ed25519

kubectl apply -f k8s/configmap.yaml
# vorher in k8s/deployment.yaml das Image auf die eigene Registry setzen
kubectl apply -f k8s/deployment.yaml

kubectl -n mail2web logs -f deploy/mail2web
```

Wichtig:

- **`replicas: 1`** und Strategie `Recreate` – zwei Instanzen würden dieselbe Mail
  doppelt verarbeiten.
- Der State liegt in `/tmp` (emptyDir) und ist nach einem Neustart weg. Das ist
  unkritisch, weil verarbeitete Mails als gelesen markiert sind; nur bei einem
  Absturz *zwischen* Upload und Markierung kann eine Mail erneut übertragen
  werden (derselbe Dateiname, also idempotent).
- `readOnlyRootFilesystem: true` funktioniert nur mit dem `emptyDir` auf `/tmp`.

## Beispiel: Speiseplan der Grundschule

```yaml
SENDER_ALLOWLIST: "sekretariat@grundschulerothenberg.de"
SUBJECT_REGEX: "speiseplan"
REMOTE_DIR: "/var/www/gsr-html-web/dokumente"
REMOTE_FILENAME: "Speiseplan.pdf"
SSH_USER: "speiseplan"
```

Damit ersetzt jede passende Mail automatisch die Datei, die die Website unter
`/dokumente/Speiseplan.pdf` verlinkt – ohne WebDAV, ohne manuellen Upload.

## Grenzen

- Nur **ungesehene** Mails werden betrachtet (bewusst – so kann man eine Mail
  erneut verarbeiten, indem man sie wieder auf „ungelesen" setzt).
- Kein Anhang-Virenscan; die Prüfung ist auf Typ, Größe und Absender begrenzt.
- Kein IMAP IDLE – es wird gepollt. Für Postfächer mit vielen Mails empfiehlt
  sich ein eigener Ordner (`IMAP_MAILBOX`) statt `INBOX`.
