#!/usr/bin/env python3
"""Geo-Updater: holt monatlich die neue DB-IP-Lite-Datenbank, prüft sie und tauscht sie atomar aus.

Regeln, damit ein Fehler nie die laufende Datenbank beschädigt:
  * nur HTTPS, nur der feste Host download.db-ip.com (auch bei Weiterleitungen), Größenlimits
  * Download und Entpacken landen in Temp-Dateien im selben Ordner, erst nach erfolgreicher Prüfung wird ersetzt
  * bei jedem Fehler bleibt die alte Datenbank unverändert; der Dienst versucht es später erneut
Aufruf:  python update.py            läuft dauerhaft (prüft alle 6 Stunden, lädt nur bei neuem Monat)
         python update.py --once     ein Durchlauf   (--force: auch wenn der Monat schon aktuell ist)
         python update.py --dry-run  laden und prüfen, aber nichts ersetzen
"""
import argparse
import datetime
import gzip
import os
import sys
import time
import urllib.error
import urllib.request

HOST = "download.db-ip.com"
URL = "https://" + HOST + "/free/dbip-city-lite-{ym}.mmdb.gz"
DB_NAME = "dbip-city-lite.mmdb"
VERSION_FILE = "VERSION"
STATUS_FILE = ".update-status"
MIN_GZ = 20 * 1024 * 1024        # eine echte Datei hat rund 60 MB
MAX_GZ = 250 * 1024 * 1024
MAX_DB = 800 * 1024 * 1024
CHUNK = 1024 * 1024
TIMEOUT = 60
CHECK_EVERY = 6 * 3600
UA = os.environ.get("UPDATER_USER_AGENT", "trafficglobe-geo-updater/1.0")  # Python-Standard-UA bekommt HTTP 403


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


class Fehler(Exception):
    pass


class NurDbIp(urllib.request.HTTPRedirectHandler):
    """Weiterleitungen nur zu https://download.db-ip.com/…"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith("https://" + HOST + "/"):
            raise Fehler("Weiterleitung zu fremdem Ziel abgelehnt")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def standard_opener(url):
    op = urllib.request.build_opener(NurDbIp())
    return op.open(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=TIMEOUT)


def aktueller_monat(jetzt=None):
    d = jetzt or datetime.datetime.now(datetime.timezone.utc)
    return f"{d.year:04d}-{d.month:02d}"


def lade(url, ziel, opener=standard_opener):
    """Lädt url nach ziel. Nur https + fester Host, hartes Größenlimit. Gibt die Größe zurück."""
    if not url.startswith("https://" + HOST + "/"):
        raise Fehler("URL nicht erlaubt")
    with opener(url) as r:
        final = getattr(r, "geturl", lambda: url)()
        if not final.startswith("https://" + HOST + "/"):
            raise Fehler("Antwort kam von fremdem Ziel")
        gesamt = 0
        with open(ziel, "wb") as f:
            while True:
                block = r.read(CHUNK)
                if not block:
                    break
                gesamt += len(block)
                if gesamt > MAX_GZ:
                    raise Fehler("Download größer als erlaubt")
                f.write(block)
    if gesamt < MIN_GZ:
        raise Fehler(f"Download zu klein ({gesamt} Bytes), vermutlich keine Datenbank")
    return gesamt


def entpacke(gz_pfad, ziel):
    gesamt = 0
    try:
        with gzip.open(gz_pfad, "rb") as src, open(ziel, "wb") as dst:
            while True:
                block = src.read(CHUNK)
                if not block:
                    break
                gesamt += len(block)
                if gesamt > MAX_DB:
                    raise Fehler("entpackte Datei größer als erlaubt")
                dst.write(block)
    except (OSError, EOFError) as e:
        raise Fehler(f"Archiv beschädigt ({type(e).__name__})")
    return gesamt


def pruefe(pfad):
    """Die Datei muss sich als Datenbank öffnen lassen und bekannte Adressen richtig verorten."""
    try:
        import maxminddb
        with maxminddb.open_database(pfad) as db:
            meta = db.metadata()
            if "city" not in meta.database_type.lower():
                raise Fehler(f"falscher Datenbanktyp: {meta.database_type}")
            if meta.node_count < 100000:
                raise Fehler("Datenbank auffällig klein")
            r = db.get("8.8.8.8") or {}
            if r.get("country", {}).get("iso_code") != "US" or "latitude" not in r.get("location", {}):
                raise Fehler("Kontrollabfrage (8.8.8.8) liefert kein sinnvolles Ergebnis")
            r = db.get("2001:4860:4860::8888") or {}
            if not r.get("country", {}).get("iso_code"):
                raise Fehler("Kontrollabfrage (IPv6) liefert kein Ergebnis")
            return {"typ": meta.database_type, "gebaut": meta.build_epoch, "knoten": meta.node_count}
    except Fehler:
        raise
    except Exception as e:
        raise Fehler(f"Datenbank nicht lesbar ({type(e).__name__})")


def schreibe_atomar(pfad, text):
    tmp = pfad + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, pfad)


def erneuere(geo_dir, jetzt=None, force=False, dry_run=False, opener=standard_opener, pruefer=pruefe):
    """Ein Durchlauf. Gibt (Ergebnis, Text) zurück: aktuell | erneuert | geprüft | noch-nicht | fehler."""
    ym = aktueller_monat(jetzt)
    vpfad = os.path.join(geo_dir, VERSION_FILE)
    try:
        with open(vpfad) as f:
            vorhanden = f.read().strip()
    except OSError:
        vorhanden = ""
    if vorhanden == ym and not force:
        return "aktuell", f"Datenbank {ym} ist aktuell"

    gz, roh = os.path.join(geo_dir, ".neu.mmdb.gz"), os.path.join(geo_dir, ".neu.mmdb")
    try:
        try:
            groesse = lade(URL.format(ym=ym), gz, opener)
        except urllib.error.HTTPError as e:
            if e.code == 404:                          # der neue Monat ist noch nicht veröffentlicht
                return "noch-nicht", f"{ym} noch nicht veröffentlicht (HTTP 404), später erneut"
            raise Fehler(f"Download fehlgeschlagen (HTTP {e.code})")
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            raise Fehler(f"Download fehlgeschlagen ({type(e).__name__})")
        entpackt = entpacke(gz, roh)
        info = pruefer(roh)
        if dry_run:
            return "geprüft", f"{ym}: {groesse // 1048576} MB geladen, {entpackt // 1048576} MB entpackt, Prüfung bestanden, nichts ersetzt"
        os.chmod(roh, 0o644)
        os.replace(roh, os.path.join(geo_dir, DB_NAME))   # atomar: der Collector sieht immer eine ganze Datei
        schreibe_atomar(vpfad, ym + "\n")
        return "erneuert", f"{ym} eingespielt ({entpackt // 1048576} MB, {info.get('knoten', '?')} Knoten)"
    except Fehler as e:
        return "fehler", f"{ym}: {e}, alte Datenbank bleibt"
    finally:
        for p in (gz, roh):
            try:
                os.remove(p)
            except OSError:
                pass


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--geo-dir", default=os.environ.get("GEO_DIR", "/geo"))
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    while True:
        erg, text = erneuere(a.geo_dir, force=a.force, dry_run=a.dry_run)
        log(f"[{erg}] {text}")
        try:
            schreibe_atomar(os.path.join(a.geo_dir, STATUS_FILE), f"{int(time.time())} {erg}\n")   # für den Healthcheck
        except OSError:
            pass
        if a.once or a.dry_run:
            return 0 if erg != "fehler" else 1
        time.sleep(CHECK_EVERY)


if __name__ == "__main__":
    sys.exit(main())
