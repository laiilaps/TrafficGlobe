#!/usr/bin/env python3
"""Globe-Collector (Bibliothek): Logzeilen -> geolokalisierte, IP-freie Ereignisse.

Nur Standardbibliothek (+ optional maxminddb). Eine IP existiert nur innerhalb
von parse_*() und Geo.lookup() im Arbeitsspeicher; Ereignisse enthalten nur Art,
gerundete Koordinaten, Länderkürzel, Stadt (aus der Geo-DB, nicht aus Logs), Port.
"""
import ipaddress
import json
import os
import re
import time
from collections import Counter, defaultdict
from datetime import datetime

KINDS = ["block", "ssh_fail", "ban", "http_scan", "http_ok"]
TARGET = {"la": 50.11, "lo": 8.68}  # Frankfurt (bewusst nicht der reale Standort)
WINDOW = 86400
DELAY_PRIVATE = 900
MAX_EVENTS = 25000
K_MIN = 3  # k-Anonymität für Besucher-Arten
DEDUP_SECONDS = 30

# --- Parser (strikte Regex, nur IP/Port/Status/Zeit; nie Freitext übernehmen) ---
IP = r"([0-9a-fA-F:.]{2,45})"
ISO_TS = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?[+-]\d{2}:\d{2}) ")
F2B_TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3} ")
RE_UFW_IN = re.compile(r"\bIN=(\S*)")
RE_UFW_OUT = re.compile(r"\bOUT=(\S*)")
RE_UFW_SRC = re.compile(r"\bSRC=" + IP + r"(?:\s|$)")
RE_UFW_DPT = re.compile(r"\bDPT=(\d{1,5})\b")
# Benutzernamen kommen vom Angreifer und dürfen Leerzeichen enthalten ("x from 1.2.3.4 y"). Darum steht bei allen
# Zeilen mit Namen die IP am festen Ende der Meldung (greedy .* davor = letztes Vorkommen gewinnt), nie hinter dem Namen.
_P = r"sshd\[\d+\]: "
_TAIL = r"\s" + IP + r" port \d+"
RE_SSH_FAIL = [re.compile(r) for r in (
    _P + r"Invalid user .*\sfrom " + IP + r" port \d+(?: \[preauth\])?\s*$",
    _P + r"Failed \S+ for .*\sfrom " + IP + r" port \d+ ssh2\s*$",
    _P + r"(?:Connection closed by|Connection reset by|Disconnected from) (?:invalid|authenticating) user .*" + _TAIL + r"(?: \[preauth\])?\s*$",
    _P + r"User .*\sfrom " + IP + r" not allowed because [^\n]*$",
    _P + r"(?:error: )?maximum authentication attempts exceeded for .*\sfrom " + IP + r" port \d+ ssh2(?: \[preauth\])?\s*$",
    _P + r"Disconnecting (?:invalid|authenticating) user .*" + _TAIL + r": Too many authentication failures(?: \[preauth\])?\s*$",
    # feste Meldungen ohne Angreifertext vor der IP
    _P + r"(?:Unable to negotiate with|banner exchange: Connection from) " + IP + r" port \d+",
    _P + r"error: kex_exchange_identification: (?:Connection closed by remote host|read: Connection reset by peer)\s+Connection from " + IP + r" port \d+",
)]
RE_SSH_OK = re.compile(_P + r"Accepted \S+ for .*\sfrom " + IP + r" port \d+ ssh2")
RE_BAN = re.compile(r"NOTICE\s+\[sshd\]\s+Ban\s+" + IP + r"\s*$")
RE_NGINX = re.compile(
    r'^\S+ - \S+ \[([^\]]+)\] "[A-Z]+ [^"]*" (\d{3}) \d+ "[^"]*" "([^"]*)" "' + IP + r'"\s*$')


def public_ip(text):
    """Gibt ipaddress-Objekt zurück, wenn global routbar, sonst None."""
    try:
        ip = ipaddress.ip_address(text.strip().rstrip(":"))
    except ValueError:
        return None
    return ip if ip.is_global else None


def _iso_epoch(line):
    m = ISO_TS.match(line)
    if not m:
        return None
    try:
        return int(datetime.fromisoformat(m.group(1)).timestamp())
    except ValueError:
        return None


def parse_ufw(line):
    """-> (ip, "block", port, epoch) oder None."""
    if "[UFW BLOCK]" not in line:
        return None
    i, o, src = RE_UFW_IN.search(line), RE_UFW_OUT.search(line), RE_UFW_SRC.search(line)
    if not (i and i.group(1) and o and not o.group(1) and src):  # nur eingehend
        return None
    ip, ts = public_ip(src.group(1)), _iso_epoch(line)
    if not ip or ts is None:
        return None
    d = RE_UFW_DPT.search(line)
    port = int(d.group(1)) if d else 0
    return ip, "block", port if port <= 65535 else 0, ts


def parse_ssh(line):
    """-> (ip, "ssh_fail" | "ssh_ok", 22, epoch) oder None."""
    ts = _iso_epoch(line)
    if ts is None:
        return None
    m = RE_SSH_OK.search(line)
    if m and (ip := public_ip(m.group(1))):
        return ip, "ssh_ok", 22, ts
    for rx in RE_SSH_FAIL:
        m = rx.search(line)
        if m and (ip := public_ip(m.group(1))):
            return ip, "ssh_fail", 22, ts
    return None


def parse_ban(line):
    """fail2ban schreibt Ortszeit ohne Zone; die Zone des Prozesses (TZ) gilt."""
    m = F2B_TS.match(line)
    b = RE_BAN.search(line)
    if not (m and b) or not (ip := public_ip(b.group(1))):
        return None
    try:
        ts = int(datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").timestamp())
    except ValueError:
        return None
    return ip, "ban", 22, ts


def parse_nginx(line, ignore_ips=()):
    """-> (ip, kind, port, epoch) oder None."""
    m = RE_NGINX.match(line)
    if not m:
        return None
    ts, status, ua, ipstr = m.groups()
    if "uptime-kuma" in ua.lower():
        return None
    ip = public_ip(ipstr)
    if not ip or str(ip) in ignore_ips:
        return None
    try:
        epoch = int(datetime.strptime(ts, "%d/%b/%Y:%H:%M:%S %z").timestamp())
    except ValueError:
        return None
    return ip, ("http_ok" if int(status) < 400 else "http_scan"), 443, epoch


PARSERS = {"ufw": parse_ufw, "ssh": parse_ssh, "f2b": parse_ban, "nginx": parse_nginx}


# --- Geo ---
class Geo:
    """IP -> Ort über eine lokale MaxMind-Datenbank (DB-IP Lite). Übernimmt eine ausgetauschte Datei selbst (ohne Neustart)."""
    RECHECK = 60  # Sekunden zwischen zwei Blicken auf das Änderungsdatum der Datei

    def __init__(self, mmdb_path=None, opener=None):
        self.path, self.reader, self.reloads = mmdb_path, None, 0
        self._mtime, self._checked, self._opener = None, 0.0, opener
        self._open(first=True)

    def _open(self, first=False):
        if not self.path or not os.path.exists(self.path):
            return
        try:
            opener = self._opener
            if opener is None:
                import maxminddb
                opener = maxminddb.open_database
            neu, mtime = opener(self.path), os.stat(self.path).st_mtime
        except Exception:
            self._mtime = os.stat(self.path).st_mtime if os.path.exists(self.path) else None   # kaputte Datei: alten Reader behalten
            return
        alt, self.reader, self._mtime = self.reader, neu, mtime
        if not first:
            self.reloads += 1
        try:
            alt and alt.close()
        except Exception:
            pass

    def _aktualisieren(self):
        jetzt = time.monotonic()
        if jetzt - self._checked < self.RECHECK or not self.path:
            return
        self._checked = jetzt
        try:
            if os.stat(self.path).st_mtime != self._mtime:
                self._open()
        except OSError:
            pass

    def lookup(self, ip):
        """-> (lat, lon, cc) oder None. Die IP verlässt diese Funktion nicht."""
        self._aktualisieren()
        if not self.reader:
            return None
        try:
            r = self.reader.get(str(ip)) or {}
            loc = r.get("location", {})
            if "latitude" not in loc:
                return None
            return float(loc["latitude"]), float(loc["longitude"]), \
                str(r.get("country", {}).get("iso_code", ""))[:2]
        except Exception:
            return None


def coarse_point(kind, la, lo):
    """Gröbe der Koordinaten: Besucher ganze Grad (~110 km), alles andere 0,1° (~11 km)."""
    if kind == "http_ok":
        return float(round(la)), float(round(lo))
    return round(la, 1), round(lo, 1)


def make_event(t, kind, geo_result, port):
    """Ereignis ohne IP, schon beim Erzeugen vergröbert: Es gibt nur diese eine (öffentliche) Genauigkeit."""
    la, lo = coarse_point(kind, geo_result[0], geo_result[1])
    return {"t": int(t), "k": kind, "la": la, "lo": lo, "cc": geo_result[2], "p": port}


def dedupe(events):
    seen, out = set(), []
    for e in sorted(events, key=lambda e: e["t"]):
        key = (e["t"] // DEDUP_SECONDS, e["k"], round(e["la"], 1), round(e["lo"], 1))
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


def prune(events, now):
    return [e for e in events if e["t"] >= now - WINDOW]


# --- Export ---
def _coarse(e):
    return coarse_point(e["k"], e["la"], e["lo"])


def build_public(events, now, delay=DELAY_PRIVATE, k_min=K_MIN):
    """Öffentliche, aggregierte Ausgabe (24 h, Minutenauflösung). Erfolgreiche SSH-Logins gibt es nicht.

    delay: Sekunden Verzögerung für Besucher (http_ok); k_min: Mindestanzahl je Rasterzelle.
    """
    cutoff_visitors = now - delay
    cells = defaultdict(int)
    for e in events:
        k = e["k"]
        if k not in KINDS or e["t"] < now - WINDOW:
            continue
        if k == "http_ok" and e["t"] > cutoff_visitors:
            continue  # Besucher um 15 min verzögern
        la, lo = _coarse(e)
        cells[(e["t"] // 60 * 60, KINDS.index(k), la, lo)] += 1
    visitor_cell_total = Counter()  # k-Anonymität: Besucherzellen mit < K_MIN fallen weg
    for (m, ki, la, lo), n in cells.items():
        if KINDS[ki] == "http_ok":
            visitor_cell_total[(la, lo)] += n
    out, totals = [], Counter()
    for (m, ki, la, lo), n in sorted(cells.items()):
        k = KINDS[ki]
        if k == "http_ok" and visitor_cell_total[(la, lo)] < k_min:
            continue
        out.append([m, ki, la, lo, n])
        totals[k] += n
    countries, ports = Counter(), Counter()
    for e in events:
        if e["k"] not in KINDS or e["t"] < now - WINDOW:
            continue
        if e["k"] == "http_ok" and (e["t"] > cutoff_visitors or visitor_cell_total[_coarse(e)] < k_min):
            continue
        if e["cc"]:
            countries[e["cc"]] += 1
        if e["k"] == "block" and e["p"]:
            ports[e["p"]] += 1
    return {
        "generated": int(now), "window": WINDOW, "delay_private": delay,
        "target": TARGET, "kinds": KINDS,
        "totals": {k: totals.get(k, 0) for k in KINDS},
        "countries": [[c, n] for c, n in countries.most_common(8)],
        "ports": [[p, n] for p, n in ports.most_common(8)],
        "events": out[-MAX_EVENTS:],
    }


def build_live(events, now, since, delay=DELAY_PRIVATE, k_min=K_MIN):
    """Kompakte Live-Datei (Sekundenzeit): [t, Art-Nummer, Breite, Länge]. Gleiche Regeln wie build_public."""
    visitors = Counter(_coarse(e) for e in events if e["k"] == "http_ok" and e["t"] >= now - WINDOW)
    out = []
    for e in events:
        if e["k"] not in KINDS or e["t"] < since:
            continue
        if e["k"] == "http_ok" and (e["t"] > now - delay or visitors[_coarse(e)] < k_min):
            continue
        la, lo = _coarse(e)
        out.append([e["t"], KINDS.index(e["k"]), la, lo])
    # Keine Artennamen und kein Ziel in der öffentlichen Datei: Das Frontend kennt die Reihenfolge selbst
    # (0 abgewiesen, 1 Login, 2 Sperre, 3 Scanner, 4 Besucher). So verrät die Datei nichts über die eingesetzte Technik.
    return {"v": 1, "generated": int(now), "window": int(now - since), "events": out[-MAX_EVENTS:]}


def atomic_write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, path)
