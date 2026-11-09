"""Genera i file GTFS di una cartella a partire da fermate.csv e percorsi.json.

    python scripts/build_gtfs.py data

Input (nella cartella):
  fermate.csv     anagrafica delle fermate con coordinate (colonne lat/lon/fonte, vedi geocode_stops.py)
  percorsi.json   agenzia, calendari, linee con sequenza fermate, minuti di percorrenza e partenze
  forme.json      (facoltativo) tracciati stradali per linea, prodotti da geocode_stops.py --forme

Output: agency.txt stops.txt routes.txt trips.txt stop_times.txt calendar.txt
        calendar_dates.txt feed_info.txt e, se c'è forme.json, shapes.txt.

Le fermate senza coordinate ricevono una posizione PROVVISORIA (su un anello attorno al centro)
così l'app resta utilizzabile; la colonna `posizione` lo dichiara e l'interfaccia lo mostra.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

CENTRO = (40.7990, 16.9230)  # Gioia del Colle, centro storico (indicativo)


def _hhmm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def _fmt(minuti: int) -> str:
    return f"{minuti // 60:02d}:{minuti % 60:02d}:00"


def _scrivi(path: Path, campi: list[str], righe: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campi, lineterminator="\n")
        w.writeheader()
        for r in righe:
            w.writerow({k: r.get(k, "") for k in campi})


def posizioni_provvisorie(fermate: list[dict], linee: list[dict]) -> dict[str, tuple[float, float]]:
    """Anello per linea: A a ovest del centro, B a est. Solo per far funzionare l'app prima del geocoding."""
    out: dict[str, tuple[float, float]] = {}
    for i, linea in enumerate(linee):
        seq = [s for s, _ in linea["percorso"]]
        uniche = list(dict.fromkeys(seq))
        cx = CENTRO[0] + (0.002 if i else -0.002)
        cy = CENTRO[1] + (0.010 if i else -0.006) * 1.0
        r = 0.006 if i else 0.005
        for k, sid in enumerate(uniche):
            if sid in out:
                continue
            a = 2 * math.pi * k / len(uniche)
            out[sid] = (round(cx + r * math.cos(a), 6), round(cy + r * 1.3 * math.sin(a), 6))
    return out


def costruisci(cartella: Path) -> dict:
    cfg = json.loads((cartella / "percorsi.json").read_text(encoding="utf-8"))
    with (cartella / "fermate.csv").open(encoding="utf-8") as f:
        fermate = list(csv.DictReader(f))
    forme = {}
    if (cartella / "forme.json").exists():
        forme = json.loads((cartella / "forme.json").read_text(encoding="utf-8"))

    provv = posizioni_provvisorie(fermate, cfg["linee"])
    stops = []
    n_provv = 0
    for fm in fermate:
        if fm.get("lat") and fm.get("lon"):
            lat, lon, posizione = float(fm["lat"]), float(fm["lon"]), fm.get("fonte") or "manuale"
        else:
            lat, lon = provv.get(fm["stop_id"], CENTRO)
            posizione, n_provv = "provvisoria", n_provv + 1
        stops.append({
            "stop_id": fm["stop_id"], "stop_code": fm["stop_code"], "stop_name": fm["stop_name"],
            "stop_lat": f"{lat:.6f}", "stop_lon": f"{lon:.6f}",
            "stop_desc": f"{fm['tipologia']} – {fm['nota']}".strip(" –"),
            "wheelchair_boarding": "0", "posizione": posizione,
        })
    noti = {s["stop_id"] for s in stops}

    ag = cfg["agency"]
    _scrivi(cartella / "agency.txt", list(ag), [ag])
    _scrivi(cartella / "feed_info.txt", list(cfg["feed_info"]), [cfg["feed_info"]])
    _scrivi(cartella / "stops.txt", ["stop_id", "stop_code", "stop_name", "stop_lat", "stop_lon",
                                     "stop_desc", "wheelchair_boarding", "posizione"], stops)

    giorni = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    cal = []
    for c in cfg["calendar"]:
        r = {"service_id": c["service_id"], "start_date": cfg["feed_info"]["feed_start_date"],
             "end_date": cfg["feed_info"]["feed_end_date"]}
        r.update({g: c["giorni"][i] for i, g in enumerate(giorni)})
        cal.append(r)
    _scrivi(cartella / "calendar.txt", ["service_id", *giorni, "start_date", "end_date"], cal)
    _scrivi(cartella / "calendar_dates.txt", ["service_id", "date", "exception_type"], [])

    routes, trips, times, shapes = [], [], [], []
    for linea in cfg["linee"]:
        for sid, _ in linea["percorso"]:
            if sid not in noti:
                raise SystemExit(f"Linea {linea['route_id']}: fermata {sid} non presente in fermate.csv")
        routes.append({"route_id": linea["route_id"], "agency_id": ag["agency_id"],
                       "route_short_name": linea["route_short_name"], "route_long_name": linea["route_long_name"],
                       "route_type": "3", "route_color": linea["route_color"],
                       "route_text_color": linea["route_text_color"]})
        shape_id = ""
        if linea["route_id"] in forme:
            shape_id = f"SH_{linea['route_id']}"
            for k, (lat, lon) in enumerate(forme[linea["route_id"]]):
                shapes.append({"shape_id": shape_id, "shape_pt_lat": f"{lat:.6f}", "shape_pt_lon": f"{lon:.6f}",
                               "shape_pt_sequence": str(k + 1)})
        for p in linea["partenze"]:
            t0 = _hhmm(p)
            trip_id = f"{linea['route_id']}_{p.replace(':', '')}"
            trips.append({"route_id": linea["route_id"], "service_id": linea["service_id"], "trip_id": trip_id,
                          "trip_headsign": linea["headsign"], "direction_id": "0", "shape_id": shape_id})
            for seq, (sid, off) in enumerate(linea["percorso"], start=1):
                t = _fmt(t0 + off)
                times.append({"trip_id": trip_id, "arrival_time": t, "departure_time": t,
                              "stop_id": sid, "stop_sequence": str(seq), "timepoint": "1"})

    _scrivi(cartella / "routes.txt", ["route_id", "agency_id", "route_short_name", "route_long_name",
                                      "route_type", "route_color", "route_text_color"], routes)
    _scrivi(cartella / "trips.txt", ["route_id", "service_id", "trip_id", "trip_headsign", "direction_id",
                                     "shape_id"], trips)
    _scrivi(cartella / "stop_times.txt", ["trip_id", "arrival_time", "departure_time", "stop_id",
                                          "stop_sequence", "timepoint"], times)
    if shapes:
        _scrivi(cartella / "shapes.txt", ["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"], shapes)
    elif (cartella / "shapes.txt").exists():
        (cartella / "shapes.txt").unlink()
    return {"fermate": len(stops), "provvisorie": n_provv, "linee": len(routes), "corse": len(trips),
            "orari": len(times), "forme": len(forme)}


if __name__ == "__main__":
    dest = Path(sys.argv[1] if len(sys.argv) > 1 else "data")
    print(json.dumps(costruisci(dest), ensure_ascii=False))
