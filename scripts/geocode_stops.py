"""Geocoding delle fermate (OpenStreetMap) e tracciati stradali delle linee.

    python scripts/geocode_stops.py data/gtfs/resta            # solo fermate senza coordinate
    python scripts/geocode_stops.py data/gtfs/resta --tutte    # rifà tutte tranne fonte=manuale
    python scripts/geocode_stops.py data/gtfs/resta --forme    # + tracciati stradali (OSRM) in forme.json

Per ogni fermata la colonna `ricerca` di fermate.csv elenca le strategie, separate da " ; ",
provate in ordine fino al primo risultato dentro il territorio comunale:

  incrocio:Via A|Via B   nodo in comune tra due strade (Overpass API); se le strade non si toccano,
                         punto medio dei due nodi più vicini, se distano meno di 150 m
  testo libero           ricerca Nominatim limitata al Comune (es. "Piazza Plebiscito")

Il risultato va in lat/lon con fonte=osm:<strategia>. Le righe con fonte=manuale (coordinate
rilevate sul posto) non vengono mai toccate: dopo il sopralluogo basta scriverle a mano.

Rispetta le policy d'uso dei servizi OSM: User-Agent identificativo, 1 richiesta al secondo,
nessun uso massivo. Gira in locale o nel workflow GitHub "geocoding".
"""
from __future__ import annotations

import csv
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

COMUNE = "Gioia del Colle"
BBOX = (40.74, 16.85, 40.86, 17.00)  # sud, ovest, nord, est (territorio comunale, con margine)
UA = "quandopassa/0.1 (+https://github.com/agent-engineering-studio/quandopassa)"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = "https://overpass-api.de/api/interpreter"
OSRM = "https://router.project-osrm.org/route/v1/driving/"

_ultima = 0.0


def _get(url: str, dati: bytes | None = None) -> dict | list:
    global _ultima
    attesa = 1.1 - (time.time() - _ultima)
    if attesa > 0:
        time.sleep(attesa)
    req = urllib.request.Request(url, data=dati, headers={"User-Agent": UA, "Accept-Language": "it"})
    for tentativo in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                _ultima = time.time()
                return json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001 - riprova sui 429/504 di Overpass
            if tentativo == 2:
                raise
            print(f"  ritento ({e})", file=sys.stderr)
            time.sleep(5 * (tentativo + 1))
    raise RuntimeError("irraggiungibile")


def _dentro(lat: float, lon: float) -> bool:
    return BBOX[0] <= lat <= BBOX[2] and BBOX[1] <= lon <= BBOX[3]


def _metri(a: tuple[float, float], b: tuple[float, float]) -> float:
    dy = (a[0] - b[0]) * 111_320
    dx = (a[1] - b[1]) * 111_320 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def nominatim(testo: str) -> tuple[float, float] | None:
    s, w, n, e = BBOX
    q = urllib.parse.urlencode({"q": f"{testo}, {COMUNE}", "format": "jsonv2", "limit": 3,
                                "countrycodes": "it", "viewbox": f"{w},{n},{e},{s}", "bounded": 1})
    for r in _get(f"{NOMINATIM}?{q}"):
        lat, lon = float(r["lat"]), float(r["lon"])
        if _dentro(lat, lon):
            return lat, lon
    return None


def _regex(nome: str) -> str:
    return re.escape(nome.strip()).replace("\\ ", " ")


def incrocio(a: str, b: str) -> tuple[float, float] | None:
    s, w, n, e = BBOX
    bb = f"{s},{w},{n},{e}"
    q = f"""[out:json][timeout:60];
way({bb})["highway"]["name"~"{_regex(a)}",i]->.a;
way({bb})["highway"]["name"~"{_regex(b)}",i]->.b;
node(w.a)(w.b);
out;
(.a;.b;);
out geom;"""
    dati = _get(OVERPASS, urllib.parse.urlencode({"data": q}).encode())
    el = dati.get("elements", [])
    comuni = [(x["lat"], x["lon"]) for x in el if x["type"] == "node"]
    if comuni:
        lat = sum(p[0] for p in comuni) / len(comuni)
        lon = sum(p[1] for p in comuni) / len(comuni)
        return (lat, lon) if _dentro(lat, lon) else None
    # strade che non si toccano (incrocio sfalsato, piazza): nodi più vicini
    def punti(nome: str) -> list[tuple[float, float]]:
        rx = re.compile(re.escape(nome), re.I)
        return [(g["lat"], g["lon"]) for x in el if x["type"] == "way" and rx.search(x.get("tags", {}).get("name", ""))
                for g in x.get("geometry", [])]
    pa, pb = punti(a), punti(b)
    if not pa or not pb:
        return None
    d, p, q2 = min(((_metri(p, q2), p, q2) for p in pa for q2 in pb), key=lambda t: t[0])
    if d > 150:
        return None
    return (p[0] + q2[0]) / 2, (p[1] + q2[1]) / 2


def geocodifica(ricerca: str) -> tuple[float, float, str] | None:
    for strategia in [s.strip() for s in ricerca.split(";") if s.strip()]:
        try:
            if strategia.startswith("incrocio:"):
                a, b = strategia.removeprefix("incrocio:").split("|", 1)
                pos = incrocio(a, b)
            else:
                pos = nominatim(strategia)
        except Exception as e:  # noqa: BLE001
            print(f"  {strategia}: errore {e}", file=sys.stderr)
            pos = None
        print(f"  {strategia}: {pos}", file=sys.stderr)
        if pos:
            return round(pos[0], 6), round(pos[1], 6), f"osm:{strategia}"
    return None


def forme(cartella: Path) -> None:
    """Tracciato stradale di ogni linea attraverso le sue fermate (OSRM, profilo auto)."""
    cfg = json.loads((cartella / "percorsi.json").read_text(encoding="utf-8"))
    with (cartella / "fermate.csv").open(encoding="utf-8") as f:
        pos = {r["stop_id"]: (float(r["lat"]), float(r["lon"])) for r in csv.DictReader(f) if r["lat"] and r["lon"]}
    out = {}
    for linea in cfg["linee"]:
        seq = [s for s, _ in linea["percorso"]]
        if any(s not in pos for s in seq):
            print(f"linea {linea['route_id']}: fermate senza coordinate, niente tracciato", file=sys.stderr)
            continue
        coord = ";".join(f"{pos[s][1]},{pos[s][0]}" for s in seq)
        r = _get(f"{OSRM}{coord}?overview=full&geometries=geojson&continue_straight=false")
        if r.get("code") != "Ok":
            print(f"linea {linea['route_id']}: OSRM {r.get('code')}", file=sys.stderr)
            continue
        out[linea["route_id"]] = [[round(lat, 6), round(lon, 6)] for lon, lat in r["routes"][0]["geometry"]["coordinates"]]
        print(f"linea {linea['route_id']}: {len(out[linea['route_id']])} punti, "
              f"{r['routes'][0]['distance'] / 1000:.1f} km", file=sys.stderr)
    (cartella / "forme.json").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")


def main(argv: list[str]) -> None:
    cartella = Path(next((a for a in argv if not a.startswith("--")), "data/gtfs/resta"))
    tutte = "--tutte" in argv
    file = cartella / "fermate.csv"
    with file.open(encoding="utf-8") as f:
        lettore = csv.DictReader(f)
        campi, righe = lettore.fieldnames, list(lettore)
    trovate = mancanti = 0
    for r in righe:
        if r.get("fonte") == "manuale" or (r.get("lat") and not tutte):
            continue
        print(f"{r['stop_id']} {r['stop_name']}", file=sys.stderr)
        g = geocodifica(r["ricerca"])
        if g:
            r["lat"], r["lon"], r["fonte"] = str(g[0]), str(g[1]), g[2]
            trovate += 1
        else:
            mancanti += 1
    with file.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campi, lineterminator="\n")
        w.writeheader()
        w.writerows(righe)
    print(json.dumps({"geocodificate": trovate, "non_trovate": mancanti}))
    if "--forme" in argv:
        forme(cartella)


if __name__ == "__main__":
    main(sys.argv[1:])
