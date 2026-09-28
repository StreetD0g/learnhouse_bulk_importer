# LearnHouse Course Importer

Ein self-hosted Bulk-Importer für lokale LearnHouse-Kursordner. Das Projekt befindet sich im Aufbau.

> Dieses Projekt ist nicht mit LearnHouse verbunden oder von LearnHouse unterstützt.

## Funktionsumfang des MVP

- Scan lokaler Kursordner mit Vorschau von Kapiteln, Lektionen und übersprungenen Dateien
- Import von `.mp4`, `.webm` und `.pdf` über die LearnHouse-API
- Erstellen von Kursen, Kapiteln und verschachtelten Library-Ordnern
- Optionales Veröffentlichen erst nach vollständigem Kursimport
- Persistenter Importverlauf und Wiederaufnahme nach Container-Neustart
- Ein eigener, Compose-konfigurierter Zugang zum Importer-Webinterface

Nicht unterstützt werden aktuell Untertitel, Office-Dateien, Audio, SCORM und
direkter Zugriff auf die LearnHouse-Datenbank oder deren Content-Verzeichnis.

## Schnellstart

1. Bearbeite die Platzhalter für `IMPORTER_PASSWORD` und `SESSION_SECRET` in
   [`docker-compose.yml`](docker-compose.yml).
2. Setze `LEARNHOUSE_URL` passend zur LearnHouse-Instanz. Die Organisations-ID
   und den Slug nutzt der Importer als Rückfall für ein einzelnes Ziel.
3. Starte den Dienst mit `docker compose up -d --build`.
4. Ergänze den API-Token in der automatisch angelegten Datei
   `config/learnhouse-importer.env`.
5. Öffne `http://HOST:8099`, melde dich an und teste die Verbindung.

Der Importer startet absichtlich nicht mit unveränderten Passwort- oder
Session-Schlüssel-Platzhaltern.

## Kursstruktur

```text
imports/
└── Example course/
    ├── course.json                 # optional
    ├── thumbnail.png               # optional
    ├── 01 Start und Orientierung/
    │   ├── 001 Willkommen.mp4
    │   └── 002 Kursaufbau.mp4
    └── 02 Grundlagen/
        ├── 001 Informationssicherheit.webm
        └── 002 Handout.pdf
```

Der oberste Ordner wird zu einem LearnHouse-Kurs, jeder direkte Unterordner zu
einem Kapitel. Nummerierungspräfixe wie `01`, `01 -`, `001` und `001.` werden
aus sichtbaren Titeln entfernt, bestimmen aber weiter die natürliche Sortierung.

`course.json` kann die Metadaten überschreiben:

```json
{
  "name": "Example course",
  "description": "A practical guide for internal processes",
  "about": "Internal processes and audit readiness.",
  "library_path": "Department/Topic",
  "thumbnail": "thumbnail.png",
  "publish": false
}
```

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

## LearnHouse-Ziele und API-Tokens

API-Tokens stehen bewusst weder in Compose noch in einer Datenbank oder im
Browser. Beim ersten Start legt der Container im gemounteten lokalen Ordner
`./config` diese Datei an:

```env
LEARNHOUSE_TOKEN_1=
LEARNHOUSE_ORG_1=
LEARNHOUSE_ORG_ID_1=
LEARNHOUSE_ORG_SLUG_1=
```

Der Betreiber ergänzt die Werte lokal in `config/learnhouse-importer.env`. Der
Ordner ist per `.gitignore` ausgeschlossen und wird nicht in das Docker-Image
kopiert.

`LEARNHOUSE_ORG_1` ist ausschließlich der sichtbare Name im Importer, zum
Beispiel `Example academy`. Er kann weggelassen oder auskommentiert
werden; dann zeigt die Oberfläche nur `Token 1` an. Tokeninhalte werden nie
angezeigt oder an den Browser gesendet.

Bei genau einem gesetzten Token startet der Import direkt in dieses Ziel. Bei
mehreren Tokens zeigt der Importer vor dem Start einen Dialog zur Auswahl und
Bestätigung des Ziels. Weitere Ziele werden fortlaufend nummeriert:

```env
LEARNHOUSE_TOKEN_2=lh_...
LEARNHOUSE_ORG_2=Interne Akademie
LEARNHOUSE_ORG_ID_2=7
LEARNHOUSE_ORG_SLUG_2=interne-akademie
```

Die ID und der Slug sind für jedes abweichende Ziel erforderlich, weil
LearnHouse-API-Tokens organisationsgebunden sind. Lässt man sie bei `Token 1`
weg, verwendet der Importer die Rückfallwerte `LEARNHOUSE_ORG_ID` und
`LEARNHOUSE_ORG_SLUG` aus Docker Compose. Bestehende Installationen mit
`LEARNHOUSE_API_TOKEN=` funktionieren weiterhin als einzelnes Ziel.

Das Vorhandensein eines Tokens wird beim Aufruf der Oberfläche geprüft; seine
Gültigkeit wird erst beim Verbindungs-Test beziehungsweise Import geprüft.

Der Container muss den Konfigurationsordner beschreiben dürfen, damit er die
Vorlage beim ersten Start anlegen kann. Die Kursquelle unter `/imports` bleibt
hingegen read-only.

## Importverlauf und Wiederaufnahme

Der Importer speichert Job-, Kurs-, Kapitel- und Lektionsstatus in der lokalen
SQLite-Datenbank des `/data`-Volumes. Der API-Token wird dabei niemals
gespeichert. Nach einem Container-Neustart werden laufende Jobs als unterbrochen
markiert und können in der Oberfläche fortgesetzt werden. Bereits erfolgreich
hochgeladene Lektionen werden dabei nicht erneut gesendet.

Ein Import mit Dateifehlern wird als Teilimport markiert. Erfolgreich erstellte
LearnHouse-Daten werden im MVP nicht automatisch gelöscht.

## Sicherheit

- Der Importer verwendet eine eigene Login-Session und speichert keine Nutzer
  in einer Datenbank.
- Der LearnHouse-Token bleibt ausschließlich in der lokalen Konfigurationsdatei
  auf dem Host und wird nicht an den Browser ausgeliefert.
- Das Repository enthält keine echten Zugangsdaten.
- Der Importer schreibt nie direkt in die LearnHouse-Datenbank und kopiert nie
  Dateien direkt in das LearnHouse-Content-Verzeichnis.
