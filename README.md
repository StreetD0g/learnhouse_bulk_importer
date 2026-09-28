# LearnHouse Course Importer

Ein self-hosted Bulk-Importer für lokale LearnHouse-Kursordner. Das Projekt befindet sich im Aufbau.

## Verbindungsmodell: lokal oder extern

Der Importer kommuniziert serverseitig ausschließlich über die LearnHouse-REST-
API. Daher müssen Importer und LearnHouse nicht auf demselben Docker-Host oder
im selben Docker-Netzwerk laufen. Das macht den Betrieb auf einem separaten NAS
oder einem Rechner des Uploaders möglich.

### Externes LearnHouse – Standard

Die normale [`docker-compose.yml`](docker-compose.yml) benötigt kein
`learnhouse`-Docker-Netzwerk. Trage die öffentliche HTTPS-Adresse ein:

```yaml
LEARNHOUSE_URL: "https://learn.example.com"
```

Das ist die empfohlene Variante, wenn die Kursdateien und LearnHouse auf
unterschiedlichen Hosts liegen. Die Kommunikation läuft vom Importer-Container
über HTTPS zum Reverse Proxy der LearnHouse-Instanz. CORS ist dabei nicht
relevant, weil keine Browser-Anfrage an LearnHouse erfolgt.

Der Reverse Proxy vor LearnHouse muss große, lang laufende Uploads zulassen. Bei
Nginx betrifft das insbesondere `client_max_body_size` sowie die Proxy-
Timeouts; ein vorgeschalteter CDN-, Tunnel- oder Proxy-Dienst darf keine
niedrigeren Upload- oder Zeitlimits erzwingen. Für den vorgesehenen MVP sollten
MP4/WebM bis 5 GB und PDFs bis 500 MB möglich sein.

### Direkte lokale Docker-Verbindung – optional

Wenn beide Dienste auf demselben Docker-Host laufen, kann der Importer statt
des öffentlichen Umwegs direkt `http://learnhouse` verwenden. Dazu:

1. `docker-compose.local.yml.example` nach `docker-compose.local.yml` kopieren.
2. Prüfen, dass das externe Docker-Netzwerk `learnhouse` existiert.
3. Beide Dateien gemeinsam starten:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
   ```

Die lokale Ergänzungsdatei ist von Git ausgeschlossen. Dadurch bleibt die
Standardinstallation portabel und öffentliche Repository-Inhalte enthalten
keine host-spezifische Netzwerk-Konfiguration.

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
