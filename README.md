# mail-to-pdf

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
  3. Es hängt eine Datei mit erlaubter Endung an (Standard: `.pdf`), optional
     muss der Dateiname auf `ATTACHMENT_NAME_REGEX` passen
  4. Die Datei beginnt wirklich mit `%PDF-` (kein umbenanntes Word-Dokument)
  5. Größe ≤ `MAX_ATTACHMENT_MB`
- Lädt den Anhang per **SFTP** hoch, schreibt erst in eine `.part`-Datei und
  benennt sie atomar um – Besucher sehen nie eine halbe PDF.
- Antwortet optional dem Absender („Datei erfolgreich übertragen"), inklusive
  `In-Reply-To`/`References`, damit die Mail im selben Thread landet.
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

Beispiel: `IMAP_HOST=imap.example.org`,
`IMAP_PORT=993`, `IMAP_SSL=true` – Port und TLS sind bereits die Vorgaben.
Benutzername ist die vollständige E-Mail-Adresse, das Passwort kommt ins Secret.

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
| `ATTACHMENT_NAME_REGEX` | nein | – | optionaler Regex auf den Dateinamen |
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
| `REMOTE_DIR` | ja | – | Zielordner, z. B. `/var/www/example-web/dokumente` |
| `REMOTE_FILENAME` | nein | – | fester Zielname bzw. Vorlage mit `{date}`, `{time}`, `{timestamp}`, `{stem}`, `{suffix}` |

\* genau eines der drei Host-Key-Verfahren beziehungsweise einer der beiden
Key-Eingaben.

### Host-Key prüfen und pinnen

Der Fingerprint schützt davor, dass sich ein fremder Server als Ziel ausgibt.
Ohne Pin verweigert das Programm die Verbindung – das ist Absicht.

**Wert ermitteln – am sichersten auf dem Zielserver:**

```bash
ssh rootwww.example.org 'ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub'
# 256 SHA256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA www.example.org (ED25519)
```

**Von außen, ohne Login:**

```bash
ssh-keyscan -t ed25519 www.example.org 2>/dev/null | ssh-keygen -lf -
```

Bei abweichendem Port: `ssh-keyscan -p 2222 …`.

**In die ConfigMap setzen:**

```bash
kubectl -n mail-to-pdf patch configmap mail-to-pdf-config --type merge \
  -p '{"data":{"SSH_HOST_FINGERPRINT":"SHA256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}}'

kubectl -n mail-to-pdf rollout restart deployment/mail-to-pdf
```

Kontrolle:

```bash
kubectl -n mail-to-pdf get configmap mail-to-pdf-config \
  -o jsonpath='{.data.SSH_HOST_FINGERPRINT}{"\n"}'
```

**Zusammengehörigkeit:** Fingerprint und `SSH_HOST` müssen dasselbe Ziel
beschreiben. Beim Wechsel zwischen Test- und Produktivserver beide Werte
zusammen ändern, sonst bricht die Verbindung mit
`host key mismatch for …: expected SHA256:…, got SHA256:…` ab.

Nach einer Neuinstallation des Servers ändert sich der Host-Key – dann den Pin
bewusst erneuern (am besten gegen den Wert auf dem Server selbst prüfen, nicht
nur per `ssh-keyscan`).

### Laufzeit

| Variable | Standard | Bedeutung |
|---|---|---|
| `REPLY_ENABLED` | `false` | Bestätigungsmail an den Absender senden |
| `REPLY_ON_DRY_RUN` | `false` | Bestätigung auch im Dry-Run (Betreff erhält `[TEST] `) |
| `REPLY_TEXT` | „Die Datei wurde erfolgreich übertragen." | Textkörper der Antwort |
| `REPLY_SUBJECT_PREFIX` | `Re: ` | Präfix; wird nicht doppelt gesetzt |
| `SMTP_HOST` | `smtp.example.org` | SMTP-Server |
| `SMTP_PORT` | `587` | Port |
| `SMTP_STARTTLS` / `SMTP_SSL` | `true` / `false` | Verschlüsselung |
| `SMTP_USER` / `SMTP_PASSWORD` | = `IMAP_USER` / `IMAP_PASSWORD` | Zugangsdaten |
| `SMTP_FROM` | = `IMAP_USER` | Absenderadresse |
| `STATE_FILE` | `/tmp/mail-to-pdf-state.json` | Merker für verarbeitete Nachrichten |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `DRY_RUN` | `false` | wie `--dry-run` |

## Secrets richtig übergeben

### Lokal (Projektverzeichnis)

Ziel: nichts landet im Repo, nichts in der Shell-History.

```bash
cd mail-to-pdf
mkdir -p private
cp .env.example private/.env
chmod 600 private/.env         # nur du darfst lesen
$EDITOR private/.env           # IMAP_PASSWORD eintragen
```

Den **privaten Key** nicht in `.env` kleben, sondern als Datei referenzieren:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/mail-to-pdf -N "" -C "mail-to-pdf@$(hostname)"
# Public Key beim Zielserver hinterlegen, dann:
export SSH_PRIVATE_KEY_FILE=$HOME/.ssh/mail-to-pdf   # statt SSH_PRIVATE_KEY
```

Starten:

```bash
./run.sh --once --dry-run      # liest private/.env, startet die App
./run.sh                       # Dauerbetrieb
```

`run.sh` liest die Datei zeilenweise, statt sie zu `source`en: Passwörter mit
Sonderzeichen (`!!`, `$`, Backticks) würden in der Shell sonst interpoliert
oder die History-Expansion auslösen.

Alternativ von Hand:

```bash
set -a; . ./private/.env; set +a
.venv/bin/python -m app.main --once --dry-run
```

Wo landet was:

| Geheimnis | Ort | Rechte |
|---|---|---|
| Postfach-Passwort | `private/.env` (gitignored) | `600` |
| SSH-Key | `private/id_ed25519` oder `~/.ssh/mail-to-pdf` | `600`, per `SSH_PRIVATE_KEY_FILE` |
| Zielserver-Fingerprint | `.env` (`SSH_HOST_FINGERPRINT`) | kein Geheimnis, aber Pflicht |

`private/` ist bis auf `.gitkeep` ignoriert; prüfen mit `git check-ignore -v private/.env`.

### k3s

**Regel: Passwort als Env aus dem Secret, privater Key als gemountete Datei.**

Warum der Unterschied? Env-Variablen stehen in `/proc/<pid>/environ`, tauchen in
Crash-Dumps und Debug-Ausgaben auf. Eine Datei mit `0400`/`0440` ist deutlich
schwerer versehentlich zu leaken — deshalb mountet das Deployment den Key unter
`/run/secrets/ssh/id_ed25519` und setzt nur `SSH_PRIVATE_KEY_FILE`.

Secret anlegen, ohne dass Werte in der History landen:

```bash
# Variante A: mehrere Werte aus einer geschützten Datei
cat > /tmp/mail-to-pdf-secrets.env <<'EOF'
IMAP_PASSWORD=***
EOF
chmod 600 /tmp/mail-to-pdf-secrets.env

kubectl -n mail-to-pdf create secret generic mail-to-pdf-secrets \
  --from-env-file=/tmp/mail-to-pdf-secrets.env \
  --from-file=SSH_PRIVATE_KEY=$HOME/.ssh/mail-to-pdf

shred -u /tmp/mail-to-pdf-secrets.env 2>/dev/null || rm -f /tmp/mail-to-pdf-secrets.env
```

Das Secret enthält danach die Schlüssel `IMAP_PASSWORD` (Env) und
`SSH_PRIVATE_KEY` (Datei). Im Pod:

```yaml
env:
  - name: IMAP_PASSWORD
    valueFrom: { secretKeyRef: { name: mail-to-pdf-secrets, key: IMAP_PASSWORD } }
  - name: SSH_PRIVATE_KEY_FILE
    value: /run/secrets/ssh/id_ed25519
volumeMounts:
  - { name: ssh-key, mountPath: /run/secrets/ssh, readOnly: true }
volumes:
  - name: ssh-key
    secret:
      secretName: mail-to-pdf-secrets
      defaultMode: 0440            # mit fsGroup: 1000 lesbar für uid 1000
      items: [{ key: SSH_PRIVATE_KEY, path: id_ed25519 }]
```

`0440` + `fsGroup: 1000` ist der Punkt, an dem es sonst klemmt: Secret-Dateien
gehören `root`, und `0400` wäre für den Container-Benutzer (uid 1000) nicht lesbar.

### Rotation

```bash
kubectl -n mail-to-pdf create secret generic mail-to-pdf-secrets \
  --from-env-file=… --from-file=SSH_PRIVATE_KEY=… \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n mail-to-pdf rollout restart deployment/mail-to-pdf
```

Env-Variablen werden im laufenden Pod **nicht** aktualisiert — der Neustart ist
Pflicht. Gemountete Secrets aktualisiert kubelet dagegen automatisch (das
Programm liest den Key allerdings nur beim Verbindungsaufbau).

### Wenn die Manifeste ins Git sollen (GitOps)

Dann keine Klartext-Secrets einchecken, sondern eine der Varianten:

- **Sealed Secrets** (Bitnami): verschlüsselte `SealedSecret`-Objekte im Repo
- **SOPS + age**: verschlüsselte `.enc.yaml`, Entschlüsselung im Cluster
- **External Secrets Operator**: Werte bleiben im Backend (Vault, 1Password, …)

`k8s/secret.example.yaml` bleibt in jedem Fall eine Vorlage mit Platzhaltern.

## Lokal testen

```bash
cd mail-to-pdf
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v      # Filter-Tests

cp .env.example .env                          # Werte eintragen
python -m app.main --once --dry-run           # ein Durchlauf, nichts wird hochgeladen
python -m app.main                            # Dauerbetrieb
```

`--dry-run` verbindet sich mit dem Postfach und zeigt, **was** übertragen würde,
lädt aber nichts hoch und markiert keine Mail als gelesen.

### Betrieb als systemd-Dienst (lokal)

**Variante ohne root (User-Dienst, hier bereits eingerichtet):**

```bash
cp deployment/systemd/mail-to-pdf.user.service ~/.config/systemd/user/mail-to-pdf.service
systemctl --user daemon-reload
systemctl --user enable --now mail-to-pdf
loginctl enable-linger cbot          # läuft auch ohne angemeldete Sitzung
```

Logs dann mit `--user`:

```bash
journalctl --user -u mail-to-pdf -f
journalctl --user -u mail-to-pdf -n 50
```

**Variante als Systemdienst (root):**

```bash
sudo cp deployment/systemd/mail-to-pdf.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mail-to-pdf
journalctl -u mail-to-pdf -f          # ohne --user
```

Das Script schreibt auf `stderr` – systemd übernimmt das automatisch ins Journal,
`SyslogIdentifier=mail-to-pdf` sorgt für saubere Filterung.

```bash
journalctl -u mail-to-pdf -f              # live mitlesen
journalctl -u mail-to-pdf -n 50           # letzte 50 Zeilen
journalctl -u mail-to-pdf --since "1 hour ago"
journalctl -u mail-to-pdf -p err          # nur Fehler
journalctl -u mail-to-pdf -o cat          # nur die Meldung, ohne Metadaten
```

Die Größe des Journals regelt journald selbst (`/etc/systemd/journald.conf`,
`SystemMaxUse`). Für k3s ist es dasselbe – dort heißt es
`kubectl -n mail-to-pdf logs -f deploy/mail-to-pdf`.

## Container bauen

### Was im Image landet – und was nicht

Die `.dockerignore` hält alles draußen, was nicht ins Image gehört:

| Ausgeschlossen | Grund |
|---|---|
| `private/` | Zugangsdaten und SSH-Key |
| `tests/`, `k8s/`, `README.md` | Nur Entwicklung |
| `.git/`, `.venv/`, `.idea/` | Ballast |

Im Image sind nur `app/` und die installierten Abhängigkeiten (`paramiko`).
Das Image läuft als **uid 1000** (nicht root) und startet `python -m app.main`;
alle Argumente des Scripts (`--once`, `--dry-run`, `--log-level`) lassen sich
anhängen.

### Bauen und lokal testen

```bash
cd mail-to-pdf
docker build -t mail-to-pdf:0.1.0 .

# Hilfe anzeigen
docker run --rm mail-to-pdf:0.1.0 --help

# Ein Durchlauf mit der echten Konfiguration, ohne Upload
docker run --rm --env-file private/.env mail-to-pdf:0.1.0 --once --dry-run

# Wie im Cluster: read-only Root, /tmp als tmpfs
docker run --rm --read-only --tmpfs /tmp \
  --env-file private/.env mail-to-pdf:0.1.0 --once
```

`--env-file` liest die lokale `private/.env`; die Datei bleibt auf dem Host und
wird nicht ins Image kopiert.

### Mehrere Architekturen (k3s auf ARM / Raspberry Pi)

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t registry.example.org/schule/mail-to-pdf:0.1.0 \
  --push .
```

Ohne passende qemu-Handler bricht der ARM-Teil ab. Abhilfe auf dem Build-Rechner:

```bash
# einmalig: ARM-Emulation registrieren
docker run --privileged --rm tonistiigi/binfmt --install arm64

# danach einen Builder neu erzeugen, damit er die Plattform erkennt
docker buildx create --name armbuilder --driver docker-container \
  --driver-opt network=host --use
docker buildx inspect --bootstrap armbuilder
```

Wichtig für Raspberry Pi 4: **64-Bit-Betriebssystem** (Raspberry Pi OS 64-bit
oder Ubuntu) – nur dann ist die `arm64`-Variante lauffähig. Auf einem 32-Bit-OS
(`armv7`) müsste zusätzlich `linux/arm/v7` gebaut werden; k3s selbst setzt
64-Bit voraus.

### In eine Registry pushen

```bash
docker tag mail-to-pdf:0.1.0 registry.example.org/schule/mail-to-pdf:0.1.0
docker push registry.example.org/schule/mail-to-pdf:0.1.0
```

**Für dieses Projekt bereits veröffentlicht:**

```
inkassodeppen/mail-to-pdf:0.1.0   (auch :latest)
├── linux/amd64
└── linux/arm64        ← Raspberry Pi 4 mit 64-Bit-OS / k3s
```

Der Push erfolgte als Manifest-Liste, damit jedes Gerät automatisch die passende
Variante zieht:

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --provenance=false \
  -t inkassodeppen/mail-to-pdf:0.1.0 \
  -t inkassodeppen/mail-to-pdf:latest \
  --push .
```

Prüfen, welche Architekturen im Manifest stecken:

```bash
docker buildx imagetools inspect inkassodeppen/mail-to-pdf:0.1.0
docker pull --platform linux/arm64 inkassodeppen/mail-to-pdf:0.1.0
docker run --rm --platform linux/arm64 --entrypoint uname inkassodeppen/mail-to-pdf:0.1.0 -m   # aarch64
```

Docker Hub geht genauso (`<benutzer>/mail-to-pdf:0.1.0`). Für eine private
Registry im Cluster ist zusätzlich ein `imagePullSecret` nötig.

### Ohne Registry (Single-Node-k3s)

```bash
docker save mail-to-pdf:0.1.0 | sudo k3s ctr images import -
sudo k3s ctr images ls | grep mail-to-pdf
```

Das Deployment nutzt `imagePullPolicy: IfNotPresent`, greift also auf das
importierte Image zurück.

## Deployment auf k3s

Dateien: `k8s/configmap.yaml` (Einstellungen), `k8s/secret.example.yaml`
(Vorlage), `k8s/deployment.yaml` (Workload).

```
Namespace mail-to-pdf
├── ConfigMap mail-to-pdf-config      ← IMAP-Host, Filter, Zielpfad, Fingerprint
├── Secret    mail-to-pdf-secrets     ← IMAP_PASSWORD, SSH_PRIVATE_KEY
└── Deployment mail-to-pdf (1 Pod)
     ├── env aus ConfigMap + secretKeyRef
     ├── /run/secrets/ssh/id_ed25519  ← Key als Datei, 0440
     └── /tmp (emptyDir)              ← State-Datei
```

### 1. Namespace anlegen

```bash
kubectl create namespace mail-to-pdf
```

### 2. Secret erzeugen

Werte kommen aus Dateien, nicht aus der Shell-History:

```bash
# Passwort in eine geschützte Datei schreiben (Editor, nicht echo)
install -m 600 /dev/null /tmp/mail-to-pdf-secrets.env
$EDITOR /tmp/mail-to-pdf-secrets.env      # Inhalt: IMAP_PASSWORD=…

kubectl -n mail-to-pdf create secret generic mail-to-pdf-secrets \
  --from-env-file=/tmp/mail-to-pdf-secrets.env \
  --from-file=SSH_PRIVATE_KEY=private/id_ed25519

shred -u /tmp/mail-to-pdf-secrets.env
```

Kontrolle (nur Schlüsselnamen, keine Werte):

```bash
kubectl -n mail-to-pdf get secret mail-to-pdf-secrets \
  -o go-template='{{range $k, $v := .data}}{{$k}}{{"\n"}}{{end}}'
```

> `kubectl -o yaml` **nicht** verwenden – die base64-Werte sind im Klartext lesbar.

Weicht das SMTP-Passwort vom IMAP-Passwort ab, zusätzlich
`--from-literal=SMTP_PASSWORD=…` (bzw. ein weiterer keyRef im Deployment).

### 3. ConfigMap anpassen

`k8s/configmap.yaml` ist die einzige Datei mit umgebungsspezifischen Werten:

| Feld | Beispiel |
|---|---|
| `IMAP_HOST` / `IMAP_PORT` | `imap.example.org` / `993` |
| `IMAP_USER` | `speiseplan@example.org` |
| `SENDER_ALLOWLIST` | `*@example.org,eltern@example.org` |
| `ATTACHMENT_NAME_REGEX` | `^speiseplan.*\.pdf$` |
| `SSH_HOST` / `SSH_USER` | `www.example.org` / `speiseplan` |
| `SSH_HOST_FINGERPRINT` | `SHA256:…` (Pflicht!) |
| `REMOTE_DIR` / `REMOTE_FILENAME` | `/var/www/example-web/dokumente` / `Speiseplan.pdf` |

```bash
kubectl apply -f k8s/configmap.yaml
```

### 4. Image-Name im Deployment setzen

In `k8s/deployment.yaml` steht bereits das veröffentlichte Image
`inkassodeppen/mail-to-pdf:0.1.0` (amd64 + arm64). Für eine eigene Registry den
Namen ersetzen – oder beim Import ohne Registry `mail-to-pdf:0.1.0` eintragen:

```bash
sed -i 's|image: mail-to-pdf:0.1.0|image: registry.example.org/schule/mail-to-pdf:0.1.0|' k8s/deployment.yaml
```

### 5. Ausrollen und prüfen

```bash
kubectl apply -f k8s/deployment.yaml
kubectl -n mail-to-pdf rollout status deployment/mail-to-pdf

kubectl -n mail-to-pdf get pods -o wide
kubectl -n mail-to-pdf logs -f deploy/mail-to-pdf
```

Erwartete Ausgabe im Log:

```
mail-to-pdf 0.1.0 starting (mailbox=INBOX, target=speiseplan@www.example.org:22, dry_run=False)
0 ungelesene Nachricht(en) geprüft, 0 Treffer
```

### 6. Was das Manifest absichert

| Einstellung | Zweck |
|---|---|
| `replicas: 1` + `strategy: Recreate` | Nur ein Poller; kein paralleles Rollout mit zwei Instanzen |
| `runAsNonRoot`, uid/gid 1000 | Kein root im Container |
| `readOnlyRootFilesystem: true` | Schreibzugriff nur auf `/tmp` (emptyDir) |
| `capabilities.drop: [ALL]`, `seccompProfile: RuntimeDefault` | Minimale Angriffsfläche |
| Secret-Volume `defaultMode: 0440` + `fsGroup: 1000` | Key für uid 1000 lesbar (mit `0400` schlägt es fehl) |
| `SSH_PRIVATE_KEY_FILE` statt Env | Key steht nicht in `/proc/<pid>/environ` |
| `automountServiceAccountToken: false` | Kein unnötiges API-Token im Pod |

### 7. Änderungen ausrollen

```bash
# neues Image
docker build -t registry.example.org/schule/mail-to-pdf:0.1.1 .
docker push registry.example.org/schule/mail-to-pdf:0.1.1
kubectl -n mail-to-pdf set image deployment/mail-to-pdf mail-to-pdf=registry.example.org/schule/mail-to-pdf:0.1.1
kubectl -n mail-to-pdf rollout status deployment/mail-to-pdf

# geänderte ConfigMap
kubectl apply -f k8s/configmap.yaml
kubectl -n mail-to-pdf rollout restart deployment/mail-to-pdf

# geändertes Secret (Env-Werte werden im laufenden Pod NICHT aktualisiert)
kubectl -n mail-to-pdf rollout restart deployment/mail-to-pdf
```

### 8. Fehlersuche

| Symptom | Ursache | Lösung |
|---|---|---|
| `ImagePullBackOff` | Image nicht gepusht / falscher Name / private Registry ohne PullSecret | Namen prüfen, `k3s ctr images import`, `imagePullSecret` |
| `CrashLoopBackOff`, Exit 2 | Pflichtvariable fehlt | `kubectl logs` zeigt `configuration error: …`; ConfigMap/Secret prüfen |
| `Permission denied` beim Key | `defaultMode: 0400` bei uid 1000 | `0440` + `fsGroup: 1000` |
| `host key not verifiable` | `SSH_HOST_FINGERPRINT` leer | Fingerprint eintragen (`ssh-keyscan … \| ssh-keygen -lf -`) |
| Upload scheitert mit `Permission denied` | Zielbenutzer darf nicht in `REMOTE_DIR` schreiben | Rechte auf dem Webserver prüfen (`chmod 2775`, Gruppe) |
| Pod läuft, aber nichts passiert | Keine ungelesenen Mails | `kubectl logs` zeigt `0 ungelesene Nachricht(en)` |

### 9. Entfernen

```bash
kubectl delete -f k8s/deployment.yaml
kubectl -n mail-to-pdf delete configmap mail-to-pdf-config secret mail-to-pdf-secrets
kubectl delete namespace mail-to-pdf
```

## Beispiel: Speiseplan der Schule

```yaml
SENDER_ALLOWLIST: "sekretariat@example.org"
SUBJECT_REGEX: "speiseplan"
REMOTE_DIR: "/var/www/example-web/dokumente"
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
