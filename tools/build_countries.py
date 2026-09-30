#!/usr/bin/env python3
"""Baut frontend/countries.geojson aus den Natural-Earth-Ländergrenzen (1:110m, Public Domain).

Quelle: https://github.com/nvkelso/natural-earth-vector (fester Commit, damit das Ergebnis reproduzierbar ist)
Änderungen gegenüber dem Original (bei gemeinfreien Daten erlaubt, hier nur zur Verkleinerung):
  * nur die Spalten, die das Frontend braucht
  * Koordinaten auf 3 Nachkommastellen gerundet (ca. 100 m, bei Maßstab 1:110 Mio. weit mehr als nötig)
  * ohne Leerraum gespeichert

Aufruf (aus dem Hauptverzeichnis):   python3 tools/build_countries.py [--out frontend/countries.geojson]
"""
import argparse
import json
import sys
import urllib.request

COMMIT = "9380cca83db5f9aef52d5e762765100745f84b27"
URL = f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{COMMIT}/geojson/ne_110m_admin_0_countries.geojson"
SPALTEN = ["NAME", "ISO_A2", "ADM0_A3", "WB_A2", "ISO_A3"]
ERWARTET = 177          # Länder in dieser Version


def runde(koordinaten):
    if koordinaten and isinstance(koordinaten[0], (int, float)):
        return [round(v, 3) for v in koordinaten[:2]]
    return [runde(k) for k in koordinaten]


def flaeche(ring):
    """Vorzeichenbehaftete Fläche eines Rings (0 = Punkt oder Linie ohne Fläche)."""
    return sum((ring[j][0] + ring[i][0]) * (ring[j][1] - ring[i][1]) for i, j in ((i, i - 1) for i in range(len(ring)))) / 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="frontend/countries.geojson")
    a = ap.parse_args()
    req = urllib.request.Request(URL, headers={"User-Agent": "trafficglobe-build/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        roh = json.load(r)
    if roh.get("type") != "FeatureCollection" or len(roh["features"]) != ERWARTET:
        sys.exit(f"Unerwarteter Inhalt: {roh.get('type')}, {len(roh.get('features', []))} Objekte (erwartet {ERWARTET})")
    features = []
    for f in roh["features"]:
        if f["geometry"]["type"] not in ("Polygon", "MultiPolygon"):
            sys.exit("Unerwarteter Geometrietyp: " + f["geometry"]["type"])
        polys = [f["geometry"]["coordinates"]] if f["geometry"]["type"] == "Polygon" else f["geometry"]["coordinates"]
        runde_polys = [p for p in (runde(p) for p in polys) if flaeche(p[0]) != 0]     # Inseln, die durchs Runden zu einem Punkt werden, entfallen
        if not runde_polys:
            sys.exit("Land ohne gültige Fläche: " + f["properties"]["NAME"])
        geo = {"type": "Polygon", "coordinates": runde_polys[0]} if len(runde_polys) == 1 else {"type": "MultiPolygon", "coordinates": runde_polys}
        features.append({"type": "Feature",
                         "properties": {k: f["properties"][k] for k in SPALTEN},
                         "geometry": geo})
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(features)} Länder -> {a.out}")


if __name__ == "__main__":
    main()
