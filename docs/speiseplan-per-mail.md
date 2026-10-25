# Speiseplan per E-Mail aktualisieren

Der Speiseplan auf der Schulewebsite lässt sich ohne WebDAV, SFTP oder
Kommandozeile aktualisieren: einfach eine E-Mail mit der PDF schicken. Der Dienst
holt den Anhang automatisch ab und legt ihn auf dem Webserver ab.

## Das Wichtigste in drei Zeilen

| Was | Wert |
|---|---|
| **Absender** | eine freigegebene Adresse (siehe Schulleitung) |
| **Anhang** | eine PDF-Datei, Name beginnt mit `speiseplan` |
| **Empfänger** | die konfigurierte Postfachadresse (siehe Schulleitung) |

Der Dateiname muss **nicht** `Speiseplan.pdf` heißen – `speiseplan-erneueren.pdf`
ist genauso richtig. Auf dem Server heißt die Datei danach immer `Speiseplan.pdf`,
damit der Link auf der Website konstant bleibt.

## Schritt für Schritt

### 1. PDF vorbereiten

- Format: **PDF** (kein Word, kein Foto, kein Screenshot als PNG)
- Dateiname: beginnt mit `speiseplan`, z. B.
  `speiseplan-erneueren.pdf`, `Speiseplan-KW45.pdf`, `speiseplan_2026-11.pdf`
- Größe: maximal **25 MB**

Umbenennen geht in jedem Dateimanager per Rechtsklick → *Umbenennen*. Der Name
wird nur zur Erkennung gebraucht; er landet nicht auf dem Server.

### 2. E-Mail schreiben

- **An:** die Postfachadresse der Schule
- **Betreff:** frei wählbar, hilfreich ist z. B. `Speiseplan KW45`
- **Text:** optional, z. B. „Neuer Speiseplan für nächste Woche."
- **Anhang:** die PDF aus Schritt 1

Wichtig ist nur der **Absender**: Mails von nicht freigegebenen Adressen werden
ignoriert. Falls Sie von einer anderen Adresse schreiben, sagen Sie der
Schulleitung Bescheid, damit sie freigeschaltet wird.

### 3. Absenden

Das war es. Der Dienst prüft das Postfach jede Minute.

## Was danach automatisch passiert

1. Die Mail wird erkannt (Absender, Anhangname, gültige PDF).
2. Die PDF wird auf den Webserver übertragen und heißt dort `Speiseplan.pdf`.
3. Die vorherige Datei wird ersetzt – Besucher sehen nie eine halbe Datei.
4. Die Mail wird als gelesen markiert, damit sie nicht doppelt verarbeitet wird.
5. Sie bekommen eine **Bestätigungsmail**: „Die Datei wurde erfolgreich übertragen."

Innerhalb von etwa einer Minute ist der neue Plan auf der Website sichtbar.

## Kontrolle

- **Website:** Seite mit dem Speiseplan öffnen und mit `Strg` + `F5` neu laden
  (der Browser darf keine alte Fassung aus dem Cache zeigen).
- **Bestätigungsmail:** kommt automatisch; bleibt sie aus, ist etwas nicht
  durchgelaufen.

## Wenn nichts passiert

| Beobachtung | Ursache | Lösung |
|---|---|---|
| Keine Bestätigung, Website unverändert | Absender nicht freigegeben | Adresse von der Schulleitung freischalten lassen |
| Keine Bestätigung | Anhangname passt nicht | Datei mit `speiseplan…` beginnen lassen |
| Keine Bestätigung | Datei ist kein PDF (z. B. DOCX umbenannt) | als PDF exportieren |
| Keine Bestätigung | Datei größer als 25 MB | PDF verkleinern |
| Bestätigung kam, Website zeigt alte Datei | Browser-Cache | `Strg` + `F5` oder privates Fenster |
| Bestätigung kam, aber falscher Inhalt | falsche Datei angehängt | erneut senden (die neuere Mail gewinnt) |

## Gut zu wissen

- **Nur eine PDF pro Mail** – bei mehreren Anhängen wird der erste passende genommen.
- **Kein Passwort, kein Login** – der Absender ist die Freigabe.
- **Mehrfaches Senden ist unkritisch**: die zuletzt verarbeitete Mail gewinnt,
  und derselbe Dateiname überschreibt sich selbst.
- **Die Mail darf ruhig gelesen aussehen** – entscheidend ist, dass sie im
  Posteingang als *ungelesen* ankommt. Wer sie versehentlich öffnet, bevor der
  Dienst sie abholt, kann sie im Mailprogramm wieder auf „ungelesen" setzen.
