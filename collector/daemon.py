#!/usr/bin/env python3
"""Globe-Daemon: liest Logs fortlaufend mit (fast live), schreibt IP-freie, öffentliche JSON-Dateien.

Es gibt nur eine Version der Daten (die öffentliche). Läuft im Container ohne Netz, read-only,
nur /out ist beschreibbar. Ausgaben:
  public/live-public.json  letzte 10 Minuten, alle ~2 s  <- NUR dieses Verzeichnis darf ein Webserver ausliefern
  stats-24h.json     24 h, Minutenauflösung (Länder, blockierte Ports): intern, wird nicht veröffentlicht
  events.jsonl       IP-freie, schon vergröberte Ereignisse für Neustarts (intern)
  state.json / status.json   Leseposition (ohne IPs) / Zähler (intern)
"""
import ipaddress
import json
import os
import signal
import sys
import time

import globe_collector as gc

LIVE_SECONDS = 600
MAX_READ = 8 * 1024 * 1024
MAX_LINES_PER_POLL = 200000


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)  # nie Logzeilen oder IPs ausgeben


class Tailer:
    """Liest neue, vollständige Zeilen einer Datei; übersteht Rotation und fehlende Rechte."""

    def __init__(self, name, path, state):
        self.name, self.path = name, path
        s = state.get(name)
        self.first_run = s is None
        self.inode = s["inode"] if s else None
        self.offset = s["offset"] if s else 0
        self.error = None

    def _read(self, path, offset):
        with open(path, "rb") as f:
            f.seek(offset)
            chunk = f.read(MAX_READ)
        end = chunk.rfind(b"\n")
        if end < 0:
            if len(chunk) >= MAX_READ:      # ein ganzes Lesefenster ohne Zeilenumbruch: Müll überspringen, sonst Endlosschleife
                return [], offset + len(chunk), True
            return [], offset, False        # halbe Zeile am Dateiende: später weiterlesen
        text = chunk[:end + 1].decode("utf-8", "replace")
        return text.splitlines(), offset + end + 1, len(chunk) >= MAX_READ

    def read_lines(self):
        lines = []
        try:
            st = os.stat(self.path)
            if self.inode is None:  # erster Start: rotierte Datei komplett, dann die aktuelle
                self.inode, self.offset = st.st_ino, 0
                if os.path.exists(self.path + ".1"):
                    more, off = True, 0
                    while more:
                        got, off, more = self._read(self.path + ".1", off)
                        lines += got
            elif st.st_ino != self.inode:  # rotiert: Rest der alten Datei, dann neue von vorn
                old = self.path + ".1"
                if os.path.exists(old) and os.stat(old).st_ino == self.inode:
                    more, off = True, self.offset
                    while more:
                        got, off, more = self._read(old, off)
                        lines += got
                self.inode, self.offset = st.st_ino, 0
            elif st.st_size < self.offset:  # abgeschnitten
                self.offset = 0
            more = True
            while more and len(lines) < MAX_LINES_PER_POLL:
                got, self.offset, more = self._read(self.path, self.offset)
                lines += got
            self.error = None
        except FileNotFoundError:
            self.error = "missing"
        except PermissionError:
            self.error = "permission"
        return lines


class Collector:
    def __init__(self, cfg, geo, now=time.time):
        self.cfg, self.geo, self.now = cfg, geo, now
        self.out = cfg["OUT_DIR"]
        os.makedirs(os.path.join(self.out, "public"), exist_ok=True)
        self.pub_delay = int(cfg.get("PUBLIC_DELAY") or gc.DELAY_PRIVATE)
        self.pub_kmin = int(cfg.get("PUBLIC_K_MIN") or gc.K_MIN)
        self.ignore = {str(ipaddress.ip_address(x)) for x in
                       (cfg.get("IGNORE_IPS") or "").replace(" ", "").split(",") if x}
        state = self._load_json("state.json").get("files", {})
        d = cfg["LOG_DIR"]
        self.tailers = [
            Tailer("ssh", os.path.join(d, "auth.log"), state),   # zuerst: lernt eigene IPs für die anderen
            Tailer("ufw", os.path.join(d, "ufw.log"), state),
            Tailer("f2b", os.path.join(d, "fail2ban.log"), state),
            Tailer("nginx", cfg["NGINX_LOG"], state),
        ]
        self.events = self._load_events()
        self.stats = {t.name: {"lines": 0, "events": 0} for t in self.tailers}
        self.no_geo = 0
        self.last = {"live": 0, "full": 0, "public": 0, "prune": self.now(), "state": 0}
        self.dirty = True

    def _load_json(self, name):
        try:
            with open(os.path.join(self.out, name)) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _load_events(self):
        """Lädt alte Ereignisse und bereinigt sie: nur bekannte Arten, keine Eigen-Markierungen,
        Koordinaten auf die öffentliche Gröbe, keine Zusatzfelder."""
        events, cutoff, geaendert = [], self.now() - gc.WINDOW, False
        try:
            with open(os.path.join(self.out, "events.jsonl")) as f:
                for line in f:
                    try:
                        e = json.loads(line)
                    except ValueError:
                        geaendert = True
                        continue
                    if not (isinstance(e, dict) and e.get("t", 0) >= cutoff and e.get("k") in gc.KINDS) or e.get("own"):
                        geaendert = True
                        continue
                    la, lo = gc.coarse_point(e["k"], e["la"], e["lo"])
                    clean = {"t": int(e["t"]), "k": e["k"], "la": la, "lo": lo,
                             "cc": str(e.get("cc", ""))[:2], "p": int(e.get("p", 0))}
                    geaendert = geaendert or clean != e
                    events.append(clean)
        except OSError:
            pass
        events = gc.dedupe(events)
        if geaendert:
            self._rewrite_jsonl(events)
        return events

    def _rewrite_jsonl(self, events):
        tmp = os.path.join(self.out, "events.jsonl.tmp")
        with open(tmp, "w") as f:
            for e in events:
                f.write(json.dumps(e, separators=(",", ":")) + "\n")
        os.replace(tmp, os.path.join(self.out, "events.jsonl"))

    def step(self):
        """Ein Durchlauf: neue Zeilen lesen -> Ereignisse -> Dateien schreiben."""
        now = self.now()
        new = []
        for t in self.tailers:
            parse = gc.PARSERS[t.name]
            for line in t.read_lines():
                if len(line) > 4096:
                    continue
                r = parse(line, self.ignore) if t.name == "nginx" else parse(line)
                if not r:
                    continue
                ip, kind, port, ts = r
                if ts < now - gc.WINDOW or ts > now + 300:
                    continue
                if kind == "ssh_ok":       # erfolgreiche Logins werden nirgends angezeigt oder gespeichert
                    continue
                g = self.geo.lookup(ip)
                del ip  # ab hier gibt es keine IP mehr
                if not g:
                    self.no_geo += 1
                    continue
                new.append(gc.make_event(ts, kind, g, port))
                self.stats[t.name]["lines"] += 1
        if new:
            merged = gc.dedupe(self.events + new)
            fresh = {id(e) for e in new}
            kept = [e for e in merged if id(e) in fresh]
            for e in kept:
                self.stats_for(e)
            self.events = merged[-gc.MAX_EVENTS:]
            self._append(kept)
            self.dirty = True
        self._write(now)
        return len(new)

    def stats_for(self, e):
        name = {"block": "ufw", "ssh_fail": "ssh", "ban": "f2b"}.get(e["k"], "nginx")
        self.stats[name]["events"] += 1

    def _append(self, events):
        with open(os.path.join(self.out, "events.jsonl"), "a") as f:
            for e in events:
                f.write(json.dumps(e, separators=(",", ":")) + "\n")

    def _write(self, now):
        w = lambda name, obj: gc.atomic_write_json(os.path.join(self.out, name), obj)
        if (self.dirty and now - self.last["live"] >= 2) or now - self.last["live"] >= 30:
            w("public/live-public.json", gc.build_live(self.events, now, now - LIVE_SECONDS,
                                                self.pub_delay, self.pub_kmin))
            self.last["live"] = now
        if (self.dirty and now - self.last["public"] >= 60) or now - self.last["public"] >= 300:
            w("stats-24h.json", gc.build_public(self.events, now, self.pub_delay, self.pub_kmin))
            self.last["public"] = now
            self.dirty = False
        if now - self.last["prune"] >= 3600:
            self.events = gc.prune(self.events, now)
            self._rewrite_jsonl(self.events)
            self.last["prune"] = now
        if now - self.last["state"] >= 5:
            w("state.json", {"files": {t.name: {"inode": t.inode, "offset": t.offset}
                                       for t in self.tailers if t.inode is not None}})
            w("status.json", {"generated": int(now), "events": len(self.events),
                              "no_geo": self.no_geo, "geo_reloads": getattr(self.geo, "reloads", 0),
                              "sources": {t.name: {"error": t.error, **self.stats[t.name]}
                                          for t in self.tailers}})
            self.last["state"] = now


def main():
    cfg = {k: os.environ.get(k, d) for k, d in {
        "LOG_DIR": "/host-log", "NGINX_LOG": "/nginx-log/access.log", "OUT_DIR": "/out",
        "MMDB": "/geo/dbip-city-lite.mmdb", "IGNORE_IPS": "",
        "POLL_SECONDS": "2", "PUBLIC_DELAY": "", "PUBLIC_K_MIN": ""}.items()}
    geo = gc.Geo(cfg["MMDB"])
    if not geo.reader:
        log("WARNUNG: keine Geo-Datenbank gefunden, es entstehen keine Ereignisse")
    c = Collector(cfg, geo)
    log(f"gestartet: {len(c.events)} Ereignisse geladen, {len(c.ignore)} ignorierte IPs")
    running = [True]
    signal.signal(signal.SIGTERM, lambda *_: running.__setitem__(0, False))
    signal.signal(signal.SIGINT, lambda *_: running.__setitem__(0, False))
    while running[0]:
        try:
            n = c.step()
            if n:
                log(f"+{n} Ereignisse (gesamt {len(c.events)})")
        except Exception as e:  # Dienst soll nie wegen einer Zeile sterben
            log(f"Fehler im Durchlauf: {type(e).__name__}")
        time.sleep(float(cfg["POLL_SECONDS"]))
    c.last["state"] = 0
    c._write(time.time())
    log("beendet")


if __name__ == "__main__":
    sys.exit(main())
