#!/usr/bin/env python3
"""Erzeugt KÜNSTLICHE Demo-Daten im Format der echten Datei, damit man das Frontend ohne Server-Logs ausprobieren kann.

Format:  {"v":1,"generated":<epoch>,"window":600,"events":[[epoch, art, breite, länge], ...]}
Arten:   0 Port-Scan, 1 Passwort-Raten, 2 IP gesperrt, 3 Schwachstellen-Suche, 4 Besucher

Aufruf:  python3 tools/make_demo_data.py            einmal schreiben
         python3 tools/make_demo_data.py --loop     alle 3 s neue Ereignisse (Live-Eindruck)
Diese Daten sind zufällig erzeugt und haben nichts mit echtem Verkehr zu tun. Nie so ausliefern, als wären sie echt.
"""
import json
import os
import random
import sys
import time

AUS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "data", "live-public.json")
FENSTER = 600
# (Breite, Länge, Gewicht): grobe Regionen der Welt
REGIONEN = [(39.9, 116.4, 8), (31.2, 121.5, 8), (37.5, -122.0, 6), (40.7, -74.0, 7), (50.1, 8.7, 6), (52.4, 4.9, 5),
            (55.7, 37.6, 6), (19.1, 72.9, 5), (-23.5, -46.6, 4), (35.7, 139.7, 4), (1.35, 103.8, 3), (-33.9, 151.2, 2),
            (6.5, 3.4, 2), (-26.2, 28.0, 2), (51.5, -0.1, 4), (48.9, 2.3, 3)]
ARTEN = [(0, 50), (1, 20), (2, 4), (3, 8), (4, 18)]


def wuerfle(jetzt):
    (la, lo, _), = random.choices(REGIONEN, weights=[r[2] for r in REGIONEN])
    art = random.choices([a for a, _ in ARTEN], weights=[w for _, w in ARTEN])[0]
    la, lo = la + random.uniform(-3, 3), lo + random.uniform(-3, 3)
    la, lo = (float(round(la)), float(round(lo))) if art == 4 else (round(la, 1), round(lo, 1))
    return [jetzt - random.randint(0, 3), art, max(-85.0, min(85.0, la)), max(-180.0, min(180.0, lo))]


def schreibe(events, jetzt):
    os.makedirs(os.path.dirname(AUS), exist_ok=True)
    tmp = AUS + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"v": 1, "generated": jetzt, "window": FENSTER, "events": events}, f, separators=(",", ":"))
    os.replace(tmp, AUS)


def main():
    jetzt = int(time.time())
    events = sorted([wuerfle(jetzt - random.randint(0, FENSTER)) for _ in range(80)])
    schreibe(events, jetzt)
    print(f"{len(events)} künstliche Ereignisse -> {os.path.normpath(AUS)}")
    while "--loop" in sys.argv:
        time.sleep(3)
        jetzt = int(time.time())
        events = [e for e in events if e[0] >= jetzt - FENSTER] + [wuerfle(jetzt) for _ in range(random.randint(0, 4))]
        schreibe(events, jetzt)


if __name__ == "__main__":
    main()
