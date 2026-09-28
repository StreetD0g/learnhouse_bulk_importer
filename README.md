# LearnHouse Course Importer

Ein self-hosted Bulk-Importer für lokale LearnHouse-Kursordner. Das Projekt befindet sich im Aufbau.

## Konfiguration in Docker Compose

Für ZimaOS/CasaOS werden Benutzername, Passwort und Session-Schlüssel direkt im
Block `environment` der [`docker-compose.yml`](docker-compose.yml) eingetragen.
Die Datei enthält nur sichere Platzhalter; der Dienst startet nicht, solange sie
unverändert sind. Lokale Änderungen an dieser Datei dürfen nicht committed werden.

`COOKIE_SECURE` bleibt für reines LAN-HTTP auf `false`. Bei Zugriff über einen
HTTPS-Reverse-Proxy muss der Wert auf `true` gesetzt werden.

## LearnHouse-API-Token

Der API-Token steht bewusst weder in Compose noch in einer Datenbank oder im
Browser. Beim ersten Start legt der Container im gemounteten lokalen Ordner
`./config` diese Datei an:

```env
LEARNHOUSE_API_TOKEN=
```

Der Betreiber ergänzt den Token lokal in `config/learnhouse-importer.env`.
Der Ordner ist per `.gitignore` ausgeschlossen und wird nicht in das Docker-Image
kopiert. Das Vorhandensein des Tokens wird beim Aufruf der Oberfläche geprüft;
seine Gültigkeit wird erst bei einem Verbindungs-Test oder Import geprüft.

Der Container muss den Konfigurationsordner beschreiben dürfen, damit er die
Vorlage beim ersten Start anlegen kann. Die Kursquelle unter `/imports` bleibt
hingegen read-only.

## Sicherheit

- Der Importer verwendet eine eigene Login-Session und speichert keine Nutzer
  in einer Datenbank.
- Der LearnHouse-Token bleibt ausschließlich in der lokalen Konfigurationsdatei
  auf dem Host und wird nicht an den Browser ausgeliefert.
- Das Repository enthält keine echten Zugangsdaten.
