# Einrichtung mit echten Logs

Getestet mit Ubuntu 24.04 (rsyslog mit ISO-Zeitstempeln), UFW, fail2ban und nginx hinter einem Reverse-Proxy oder Tunnel.
Andere Formate: die Parser stehen in `collector/globe_collector.py` (`parse_ufw`, `parse_ssh`, `parse_ban`, `parse_nginx`),
jeweils mit Tests.

## Voraussetzungen an die Logs

| Quelle | Datei | Erwartetes Format |
|---|---|---|
| Firewall | `/var/log/ufw.log` | `2026-09-30T12:36:00+02:00 host kernel: [UFW BLOCK] IN=eth0 OUT= … SRC=<ip> … DPT=<port>` (UFW-Logging mindestens `low`: `ufw logging low`) |
| SSH | `/var/log/auth.log` | `sshd[123]: Invalid user … from <ip> port …` u. Ä. |
| fail2ban | `/var/log/fail2ban.log` | `2026-09-30 12:34:56,183 … NOTICE  [sshd] Ban <ip>` |
| Web | Datei aus dem nginx-Container | Format wie `main`, aber **das letzte Feld muss die Client-IP sein** (siehe Schritt 2) |

Die Dateien sind für Gruppe `adm` lesbar. Der Container bekommt die Gruppe über `group_add: ["4"]` (GID von `adm` prüfen:
`getent group adm`).

## 1. Verzeichnisse und Geo-Datenbank

```bash
git clone <dein-fork> trafficglobe && cd trafficglobe
cp .env.example .env && chmod 600 .env
# Geo-Datenbank: siehe README, Abschnitt "Die IP-Datenbank"
mkdir -p out/public web
sudo chown 1000:1000 geo out         # die Container laufen als UID 1000 und schreiben dort
```

## 2. nginx schreibt zusätzlich ein Access-Log in eine Datei

Der Collector hat absichtlich keinen Docker-Socket. Damit er die Web-Zugriffe lesen kann, schreibt nginx sie zusätzlich in ein
gemeinsames Volume (`globe-nginx-logs`, wird von `docker-compose.example.yml` angelegt und von dir in den nginx eingebunden):

```nginx
# Das LETZTE Feld muss genau eine Client-IP sein (Zeilen mit mehreren Adressen werden verworfen, das schützt vor gefälschten Headern):
#   direkt aus dem Internet erreichbar:                     "$remote_addr"
#   nur über Cloudflare (Tunnel oder Proxy, Origin sonst dicht): "$http_cf_connecting_ip"
log_format globe '$remote_addr - - [$time_local] "$request" $status $body_bytes_sent "$http_referer" "$http_user_agent" "$http_cf_connecting_ip"';
access_log /var/log/nginx-globe/access.log globe;    # zusätzlich zum bestehenden Log
```

Vertraue `$http_cf_connecting_ip` und `X-Forwarded-For` nur, wenn Anfragen wirklich ausschließlich über den Proxy bei dir ankommen.
Sonst kann jeder den Header selbst setzen und falsche Herkunftsorte einschleusen.

Diese Datei wächst. Leere sie regelmäßig, z. B. täglich per Cron: `docker exec -u nginx nginx sh -c ': > /var/log/nginx-globe/access.log'`
(der Collector erkennt abgeschnittene Dateien).

## 3. Collector und Geo-Updater starten

```bash
docker compose -f docker-compose.example.yml up -d --build
docker logs -f globe-collector          # "gestartet: … Ereignisse geladen"
cat out/status.json                     # alle Quellen "error": null?
```

`out/public/live-public.json` ist die einzige Datei, die ein Webserver ausliefern darf. Alles andere in `out/` ist intern
(`events.jsonl`, `state.json`, `status.json`, `stats-24h.json`).

## 4. Frontend bereitstellen

```bash
cd frontend && npm ci && npm run vendor
cp index.html app.js style.css rechtliches.html rechtliches.css countries.geojson ../web/ && mkdir -p ../web/vendor && cp vendor/globe.gl.min.js ../web/vendor/
```

Ändere vorher `ZIEL` in `app.js` und passe `rechtliches.html` an (Vorlage!).

## 5. nginx

`deploy/nginx-globe.conf` nach `/etc/nginx/conf.d/` und `deploy/globe-headers.conf` nach `/etc/nginx/snippets/globe-headers.conf` legen
(Servername anpassen). Zwei Read-only-Mounts für die Inhalte:

```yaml
- ./web:/usr/share/nginx/globe-web:ro
- ./out/public:/usr/share/nginx/globe-data:ro
```

Die Vorlage liefert nur die bekannten Dateien aus (alles andere 404), erlaubt nur GET/HEAD, setzt eine strenge CSP und limitiert
Anfragen pro Besucher. **Rate-Limit-Schlüssel:** Die Vorlage nutzt `$http_cf_connecting_ip`. Ohne Cloudflare ist dieses Feld leer, dann
ersetze es in der ersten Zeile (`limit_req_zone`) durch `$binary_remote_addr`. Hinter Cloudflare **`Cache-Control: no-transform`** beibehalten: Sonst fügt Cloudflare Skripte ein und
schreibt E-Mail-Adressen um, das kollidiert mit der CSP.

## 6. Prüfen

```bash
H=https://deine-domain.example
for p in / /app.js /data/live-public.json /rechtliches; do curl -s -o /dev/null -w "$p %{http_code}\n" $H$p; done   # 200
for p in /data/ /data/state.json /status.json /events.jsonl /.env /package.json; do curl -s -o /dev/null -w "$p %{http_code}\n" $H$p; done   # 404
curl -s $H/data/live-public.json | grep -Ec '([0-9]{1,3}\.){3}[0-9]{1,3}'     # 0: keine IP-Muster
```

Im Browser: Netzwerk-Tab (nur eigene Domain), Konsole ohne CSP-Fehler, keine Cookies.

## Betrieb

- **Notaus:** `docker compose -f docker-compose.example.yml stop` und `rm out/public/live-public.json`.
- **systemd-Journal** enthält SSH- und Firewall-Meldungen mit IPs und hat standardmäßig keine Zeitgrenze. Wenn du versprichst,
  Logs würden regelmäßig gelöscht, setze `MaxRetentionSec=1month` in `/etc/systemd/journald.conf.d/`.
- **Gesundheit:** Beide Container haben einen Healthcheck (`docker ps`). Das Frontend zeigt „Daten veraltet“, wenn die Datei zu alt ist.
