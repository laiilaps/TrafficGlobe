# TrafficGlobe

**Inbound traffic on a live 3D globe: port scans, brute-force logins, bans and real visitors, without ever showing or storing an IP address.**
Self-hosted, reads your own server logs, geolocates locally. (German UI and documentation; the code is small and commented, translations welcome.)

**Live ansehen · Live demo: [elija.de](https://elija.de)**

TrafficGlobe zeigt in Echtzeit auf einem 3D-Globus, woher Verbindungen zu deinem Server kommen: abgewiesene Port-Scans, gescheiterte
Login-Versuche, automatische IP-Sperren, Web-Scanner und normale Besucher. Jedes Ereignis wird eine Linie, die vom groben
Ursprungsort zum Ziel geschossen wird und dann mit der Zeit verblasst. Weitere Anfragen aus derselben Region schicken ein
kleines Paket über die bestehende Linie. Mit der Maus über einer Linie siehst du Art, Herkunftsland und Anzahl.

```
 Logs (ufw, sshd, fail2ban, nginx) ──lesen──> collector (Docker, ohne Netz) ──> public/live-public.json
                                                   ▲                                   │ (ro-Mount)
        geo/dbip-city-lite.mmdb (lokal) ◄── geo-update (Docker, 1x im Monat)           ▼
                                                                          nginx (nur statische Dateien) ──> Browser (globe.gl)
```

Es gibt **kein Backend, keine Datenbank und keine API**: Ein kleiner Container schreibt eine Datei, ein Webserver liefert sie
zusammen mit statischen Dateien aus.

## Datenschutz von Anfang an

- Eine IP-Adresse existiert nur für einen Moment im Arbeitsspeicher, wird in einen ungefähren Ort umgerechnet (lokale Datenbank,
  nichts geht an Dritte) und sofort verworfen. Es gibt keine Datei und keinen Log-Eintrag mit IPs.
- Ereignisse werden **schon beim Erzeugen vergröbert**: Besucher auf ganze Grad (ca. 110 km), Angriffe auf 0,1° (ca. 11 km).
  Intern gibt es keine feinere Version.
- Die öffentliche Datei enthält nur `[Zeit, Art-Nummer, Breite, Länge]`. Keine Namen, Ports, Länderlisten, User-Agents, URLs.
- Erfolgreiche Logins werden nirgends angezeigt oder gespeichert.
- Besucher-Ereignisse können verzögert (`PUBLIC_DELAY`, Standard 900 s) und erst ab einer Mindestanzahl je Rasterzelle
  angezeigt werden (`PUBLIC_K_MIN`, Standard 3), damit sich niemand als „einziger Besucher aus Ort X“ erkennt.
  Wer beides auf 0 bzw. 1 setzt, bekommt mehr „Live“, aber Besucher können ihre eigene Linie erkennen.
- Angreifer kontrollieren Logzeilen (Benutzernamen, User-Agents, Pfade). Deshalb: strikte Regex, die IP steht immer am festen
  Ende einer Meldung, Zeilen mit mehr als einer Adresse im Weiterleitungs-Header werden verworfen, Größenlimits. Siehe
  [SECURITY.md](SECURITY.md).

## Ausprobieren ohne Server-Logs (2 Minuten)

Du brauchst nur Python 3 und Node.js. Es entstehen künstliche Demo-Daten, die klar als solche erzeugt werden.

```bash
cd frontend && npm ci && npm run vendor && cd ..     # holt globe.gl (MIT) nach frontend/vendor/
python3 tools/make_demo_data.py --loop &              # schreibt frontend/data/live-public.json alle 3 s neu
python3 tools/dev_server.py                           # http://localhost:8769, mit derselben strengen CSP wie produktiv
```

## Mit echten Logs betreiben

Vollständige Anleitung: **[docs/SETUP.md](docs/SETUP.md)**. Kurzfassung:

1. Geo-Datenbank besorgen (kostenlos, kein Konto, siehe unten).
2. `cp .env.example .env`, `docker compose -f docker-compose.example.yml up -d --build`
3. nginx-Vorlage aus `deploy/` einbinden (statisch, nur zwei Read-only-Ordner).

### Die IP-Datenbank (DB-IP Lite)

Die Datenbank ist **nicht** im Repo. Sie ist kostenlos, braucht kein Konto und steht unter CC BY 4.0. Auf jeder Seite, die
Ergebnisse daraus anzeigt, muss ein Link auf DB-IP stehen (die Fußzeile in `frontend/index.html` macht das).

```bash
mkdir -p geo && ym=$(date +%Y-%m)
curl -fL -A "trafficglobe/1.0" -o geo/db.gz "https://download.db-ip.com/free/dbip-city-lite-$ym.mmdb.gz"   # eigener User-Agent nötig
gunzip -c geo/db.gz > geo/dbip-city-lite.mmdb && rm geo/db.gz && echo "$ym" > geo/VERSION
```

Die Datei erscheint monatlich neu. Der Container `geo-update` erledigt das automatisch: Er lädt nur den festen HTTPS-Host,
prüft die Datei (Datenbanktyp, Kontrollabfragen) und tauscht sie atomar aus. Bei jedem Fehler bleibt die alte Datei. Der
Collector übernimmt die neue Datei ohne Neustart.

## Was du anpassen musst

| Was | Wo |
|---|---|
| Ziel der Linien (Koordinaten) | `frontend/app.js`, Konstante `ZIEL`. Bewusst nicht der echte Serverstandort wählen. |
| Impressum / Datenschutz | `frontend/rechtliches.html` ist nur eine **Vorlage**. Kein Rechtsrat, an deine Lage anpassen. |
| Eigene IPs, die nicht angezeigt werden sollen (z. B. Monitoring) | `IGNORE_IPS` in `.env` |
| Zeitzone der Logs | `TZ` in `docker-compose.example.yml` |

## Tests

```bash
python3 -m unittest discover -s tests
```

Die Tests decken Parser (auch Angriffszeilen), Vergröberung, Rotation, Neustarts, Geo-Update und den Austausch der Datenbank ab.

## Entstehung

TrafficGlobe ist gemeinsam mit **Claude** (Anthropic) entstanden: Idee, Entscheidungen, Konfiguration und Prüfung kommen von Elija E,
ein großer Teil von Code, Tests und Dokumentation wurde zusammen mit Claude geschrieben und geprüft.
*Built together with Claude (Anthropic): ideas, decisions and review by Elija E; much of the code, tests and docs were co-written with Claude.*

## Lizenz

MIT, siehe [LICENSE](LICENSE). Drittanbieter siehe [NOTICE.md](NOTICE.md).
