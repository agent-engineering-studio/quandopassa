"""Sorgenti del feed GTFS: lettura e scrittura dei file sorgente, verifica, generazione dei .txt, import da un GTFS.

Le sorgenti di una cartella sono tre file leggibili e modificabili a mano:

  fermate.csv     anagrafica delle fermate (stop_id, stop_code, stop_name, linee, tipologia, nota, ricerca, lat, lon, fonte)
  percorsi.json   agenzia, feed_info, calendari (con eccezioni), linee con sequenza fermate, minuti e partenze
  forme.json      (facoltativo) tracciati stradali: {chiave della linea: [[lat, lon], ...]}

`build_gtfs()` genera da queste i file GTFS (agency, feed_info, stops, routes, trips, stop_times, calendar,
calendar_dates, shapes). La usano scripts/build_gtfs.py e il backoffice, che tiene i dati in Postgres e a ogni
salvataggio rigenera il feed nello stesso formato.

Una voce di `linee` è un servizio con un solo percorso: per le varianti della stessa linea (stesso route_id,
percorso o calendario diversi) si aggiungono più voci con lo stesso route_id e un `id` diverso.
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_CENTER = (40.7990, 16.9230)  # centro indicativo per le posizioni provvisorie
STOP_FIELDS = ["stop_id", "stop_code", "stop_name", "linee", "tipologia", "nota", "ricerca", "lat", "lon", "fonte"]
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
SOURCE_FILES = ("fermate.csv", "percorsi.json", "forme.json")

RX_TIME = re.compile(r"^([0-4]?\d):([0-5]\d)$")
RX_ID = re.compile(r"^[A-Za-z0-9_.\-]{1,40}$")
RX_COLOR = re.compile(r"^[0-9A-Fa-f]{6}$")
RX_DATE = re.compile(r"^\d{8}$")


class InvalidSources(ValueError):
    """Le sorgenti non si possono trasformare in un feed GTFS."""


# ===================================================================== file sorgente
def has_sources(folder: Path) -> bool:
    return (folder / "fermate.csv").exists() and (folder / "percorsi.json").exists()


def read_sources(folder: Path) -> dict:
    """{fermate: [...], percorsi: {...}, forme: {...}} dalla cartella."""
    with (folder / "fermate.csv").open(encoding="utf-8", newline="") as f:
        stops = [{k: (row.get(k) or "") for k in STOP_FIELDS} for row in csv.DictReader(f)]
    routes_cfg = json.loads((folder / "percorsi.json").read_text(encoding="utf-8"))
    shapes = {}
    if (folder / "forme.json").exists():
        shapes = json.loads((folder / "forme.json").read_text(encoding="utf-8"))
    return {"fermate": stops, "percorsi": routes_cfg, "forme": shapes}


def write_sources(folder: Path, src: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=STOP_FIELDS, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    for row in src["fermate"]:
        writer.writerow({k: _text(row.get(k)) for k in STOP_FIELDS})
    write_atomic(folder / "fermate.csv", buf.getvalue())
    write_atomic(folder / "percorsi.json", json.dumps(src["percorsi"], ensure_ascii=False, indent=2) + "\n")
    if src.get("forme"):
        write_atomic(folder / "forme.json", json.dumps(src["forme"], separators=(",", ":")))
    elif (folder / "forme.json").exists():
        (folder / "forme.json").unlink()


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def lines_by_stop(routes_cfg: dict) -> dict[str, str]:
    """stop_id -> "A B" (colonna informativa `linee` di fermate.csv)."""
    out: dict[str, list[str]] = {}
    for line in routes_cfg.get("linee", []):
        name = line.get("route_short_name") or line.get("route_id", "")
        for stop_id, _ in line.get("percorso", []):
            if name not in out.setdefault(stop_id, []):
                out[stop_id].append(name)
    return {k: " ".join(v) for k, v in out.items()}


def variant_key(line: dict) -> str:
    """Identificativo della voce: `id` per le varianti, altrimenti il route_id."""
    return str(line.get("id") or line["route_id"])


# ===================================================================== generazione GTFS
def _minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _format_time(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}:00"


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def provisional_positions(lines: list[dict], center=DEFAULT_CENTER) -> dict[str, tuple[float, float]]:
    """Un anello per linea attorno al centro: solo per far funzionare l'app prima del geocoding."""
    out: dict[str, tuple[float, float]] = {}
    for i, line in enumerate(lines):
        unique = list(dict.fromkeys(stop_id for stop_id, _ in line["percorso"]))
        cx = center[0] + (0.002 if i else -0.002)
        cy = center[1] + (0.010 if i else -0.006)
        radius = 0.006 if i else 0.005
        for k, stop_id in enumerate(unique):
            if stop_id in out:
                continue
            angle = 2 * math.pi * k / len(unique)
            out[stop_id] = (round(cx + radius * math.cos(angle), 6), round(cy + radius * 1.3 * math.sin(angle), 6))
    return out


def build_gtfs(folder: Path, src: dict | None = None) -> dict:
    """Scrive i file GTFS nella cartella a partire dalle sorgenti (lette dalla cartella se non passate)."""
    src = src or read_sources(folder)
    cfg, stops_src, shapes_src = src["percorsi"], src["fermate"], src.get("forme") or {}

    provisional = provisional_positions(cfg["linee"])
    stops, n_provisional = [], 0
    for stop in stops_src:
        if stop.get("lat") and stop.get("lon"):
            lat, lon, position = float(stop["lat"]), float(stop["lon"]), stop.get("fonte") or "manuale"
        else:
            lat, lon = provisional.get(stop["stop_id"], DEFAULT_CENTER)
            position, n_provisional = "provvisoria", n_provisional + 1
        stops.append({
            "stop_id": stop["stop_id"], "stop_code": stop.get("stop_code", ""), "stop_name": stop["stop_name"],
            "stop_lat": f"{lat:.6f}", "stop_lon": f"{lon:.6f}",
            "stop_desc": f"{stop.get('tipologia', '')} – {stop.get('nota', '')}".strip(" –"),
            "wheelchair_boarding": "0", "posizione": position,
        })
    known = {s["stop_id"] for s in stops}

    agency = cfg["agency"]
    _write_csv(folder / "agency.txt", list(agency), [agency])
    _write_csv(folder / "feed_info.txt", list(cfg["feed_info"]), [cfg["feed_info"]])
    _write_csv(folder / "stops.txt", ["stop_id", "stop_code", "stop_name", "stop_lat", "stop_lon",
                                      "stop_desc", "wheelchair_boarding", "posizione"], stops)

    calendar, exceptions = [], []
    for c in cfg["calendar"]:
        row = {"service_id": c["service_id"], "start_date": c.get("inizio") or cfg["feed_info"]["feed_start_date"],
               "end_date": c.get("fine") or cfg["feed_info"]["feed_end_date"]}
        row.update({day: c["giorni"][i] for i, day in enumerate(WEEKDAYS)})
        calendar.append(row)
        for e in c.get("eccezioni", []):
            exceptions.append({"service_id": c["service_id"], "date": e["data"], "exception_type": str(e["tipo"])})
    _write_csv(folder / "calendar.txt", ["service_id", *WEEKDAYS, "start_date", "end_date"], calendar)
    _write_csv(folder / "calendar_dates.txt", ["service_id", "date", "exception_type"], exceptions)

    routes: dict[str, dict] = {}
    trips, stop_times, shapes = [], [], []
    for line in cfg["linee"]:
        key = variant_key(line)
        for stop_id, _ in line["percorso"]:
            if stop_id not in known:
                raise InvalidSources(f"Linea {key}: fermata {stop_id} inesistente")
        routes.setdefault(line["route_id"], {
            "route_id": line["route_id"], "agency_id": agency["agency_id"],
            "route_short_name": line["route_short_name"], "route_long_name": line["route_long_name"],
            "route_type": "3", "route_color": line["route_color"], "route_text_color": line["route_text_color"]})
        shape_id = ""
        if shapes_src.get(key):
            shape_id = f"SH_{key}"
            for n, (lat, lon) in enumerate(shapes_src[key]):
                shapes.append({"shape_id": shape_id, "shape_pt_lat": f"{lat:.6f}", "shape_pt_lon": f"{lon:.6f}",
                               "shape_pt_sequence": str(n + 1)})
        for departure in line["partenze"]:
            start = _minutes(departure)
            trip_id = f"{key}_{departure.replace(':', '')}"
            trips.append({"route_id": line["route_id"], "service_id": line["service_id"], "trip_id": trip_id,
                          "trip_headsign": line["headsign"], "direction_id": str(line.get("direzione", 0)),
                          "shape_id": shape_id})
            for seq, (stop_id, offset) in enumerate(line["percorso"], start=1):
                t = _format_time(start + int(offset))
                stop_times.append({"trip_id": trip_id, "arrival_time": t, "departure_time": t,
                                   "stop_id": stop_id, "stop_sequence": str(seq), "timepoint": "1"})

    _write_csv(folder / "routes.txt", ["route_id", "agency_id", "route_short_name", "route_long_name",
                                       "route_type", "route_color", "route_text_color"], list(routes.values()))
    _write_csv(folder / "trips.txt", ["route_id", "service_id", "trip_id", "trip_headsign", "direction_id",
                                      "shape_id"], trips)
    _write_csv(folder / "stop_times.txt", ["trip_id", "arrival_time", "departure_time", "stop_id",
                                           "stop_sequence", "timepoint"], stop_times)
    if shapes:
        _write_csv(folder / "shapes.txt", ["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"], shapes)
    elif (folder / "shapes.txt").exists():
        (folder / "shapes.txt").unlink()
    return {"fermate": len(stops), "provvisorie": n_provisional, "linee": len(routes), "corse": len(trips),
            "orari": len(stop_times), "forme": len([k for k in shapes_src if shapes_src[k]])}


# ===================================================================== verifica
def parse_date(text: str) -> date | None:
    try:
        return datetime.strptime(text, "%Y%m%d").date() if RX_DATE.match(text or "") else None
    except ValueError:
        return None


def validate(src: dict, today: date | None = None) -> tuple[list[str], list[str]]:
    """(errori, avvisi). Con errori il feed non viene generato; gli avvisi sono da valutare."""
    errors: list[str] = []
    warnings: list[str] = []
    today = today or date.today()
    stops, cfg, shapes = src.get("fermate") or [], src.get("percorsi") or {}, src.get("forme") or {}

    # ------------------------------------------------ fermate
    stop_ids: set[str] = set()
    for i, stop in enumerate(stops, start=1):
        stop_id = (stop.get("stop_id") or "").strip()
        name = stop.get("stop_name") or stop_id or f"riga {i}"
        if not RX_ID.match(stop_id):
            errors.append(f"Fermata «{name}»: identificativo «{stop_id}» non valido (lettere, cifre, _ . -)")
        elif stop_id in stop_ids:
            errors.append(f"Fermata {stop_id}: identificativo ripetuto")
        stop_ids.add(stop_id)
        if not (stop.get("stop_name") or "").strip():
            errors.append(f"Fermata {stop_id}: manca il nome")
        lat, lon = stop.get("lat"), stop.get("lon")
        if lat or lon:
            try:
                if not (-90 <= float(lat) <= 90 and -180 <= float(lon) <= 180):
                    raise ValueError
            except (TypeError, ValueError):
                errors.append(f"Fermata {stop_id}: coordinate non valide ({lat}, {lon})")
        else:
            warnings.append(f"Fermata {stop_id} «{name}»: senza coordinate, avrà una posizione provvisoria sulla mappa")

    # ------------------------------------------------ agenzia e validità
    agency = cfg.get("agency") or {}
    for field in ("agency_id", "agency_name", "agency_url", "agency_timezone"):
        if not str(agency.get(field) or "").strip():
            errors.append(f"Agenzia: manca {field}")
    if agency.get("agency_url") and not str(agency["agency_url"]).startswith(("http://", "https://")):
        errors.append("Agenzia: l'indirizzo del sito deve iniziare con http:// o https://")
    if agency.get("agency_timezone"):
        try:
            ZoneInfo(agency["agency_timezone"])
        except (ZoneInfoNotFoundError, ValueError):
            errors.append(f"Agenzia: fuso orario sconosciuto «{agency['agency_timezone']}»")
    feed_info = cfg.get("feed_info") or {}
    start, end = parse_date(feed_info.get("feed_start_date", "")), parse_date(feed_info.get("feed_end_date", ""))
    if not start or not end:
        errors.append("Validità del feed: date di inizio e fine obbligatorie")
    elif start > end:
        errors.append("Validità del feed: la data di inizio è dopo la data di fine")
    elif end < today:
        warnings.append(f"Validità del feed: scaduto il {end:%d/%m/%Y}, nessun bus viene mostrato")
    elif end < today + timedelta(days=30):
        warnings.append(f"Validità del feed: scade il {end:%d/%m/%Y}")

    # ------------------------------------------------ calendari
    services: dict[str, dict] = {}
    for c in cfg.get("calendar") or []:
        service_id = str(c.get("service_id") or "")
        if not RX_ID.match(service_id):
            errors.append(f"Calendario «{service_id}»: identificativo non valido")
            continue
        if service_id in services:
            errors.append(f"Calendario {service_id}: identificativo ripetuto")
        services[service_id] = c
        days = str(c.get("giorni") or "")
        if not re.fullmatch(r"[01]{7}", days):
            errors.append(f"Calendario {service_id}: giorni non validi (sette cifre 0/1 da lunedì a domenica)")
        for label, field in (("inizio", "inizio"), ("fine", "fine")):
            if c.get(field) and not parse_date(c[field]):
                errors.append(f"Calendario {service_id}: data di {label} non valida")
        added = 0
        for e in c.get("eccezioni") or []:
            if not parse_date(str(e.get("data", ""))):
                errors.append(f"Calendario {service_id}: data di eccezione non valida «{e.get('data')}»")
            if str(e.get("tipo")) not in ("1", "2"):
                errors.append(f"Calendario {service_id}: tipo di eccezione non valido (1 = aggiunto, 2 = soppresso)")
            added += str(e.get("tipo")) == "1"
        if days == "0000000" and not added:
            warnings.append(f"Calendario {service_id}: nessun giorno di servizio")

    # ------------------------------------------------ linee
    keys: set[str] = set()
    attributes: dict[str, tuple] = {}
    used_stops: set[str] = set()
    used_services: set[str] = set()
    lines = cfg.get("linee") or []
    if not lines:
        errors.append("Nessuna linea")
    for line in lines:
        route_id = str(line.get("route_id") or "")
        key = str(line.get("id") or route_id)
        label = f"Linea {key}"
        if not RX_ID.match(route_id):
            errors.append(f"{label}: route_id «{route_id}» non valido")
            continue
        if not RX_ID.match(key):
            errors.append(f"{label}: identificativo della variante non valido")
        if key in keys:
            errors.append(f"{label}: identificativo ripetuto (per le varianti della stessa linea usare un id diverso)")
        keys.add(key)
        attrs = (line.get("route_short_name"), line.get("route_long_name"), line.get("route_color"),
                 line.get("route_text_color"))
        if attributes.setdefault(route_id, attrs) != attrs:
            errors.append(f"{label}: nome o colori diversi dalle altre varianti della linea {route_id}")
        if not str(line.get("route_short_name") or "").strip():
            errors.append(f"{label}: manca il nome breve")
        for field in ("route_color", "route_text_color"):
            if not RX_COLOR.match(str(line.get(field) or "")):
                errors.append(f"{label}: colore {field} non valido (6 cifre esadecimali, es. 1864AB)")
        service_id = str(line.get("service_id") or "")
        if service_id not in services:
            errors.append(f"{label}: calendario «{service_id}» inesistente")
        used_services.add(service_id)
        path = line.get("percorso") or []
        if len(path) < 2:
            errors.append(f"{label}: il percorso deve avere almeno due fermate")
        previous = -1
        for pos, item in enumerate(path, start=1):
            try:
                stop_id, offset = str(item[0]), int(item[1])
            except (TypeError, ValueError, IndexError, KeyError):
                errors.append(f"{label}: voce {pos} del percorso non valida")
                continue
            if pos == 1 and offset != 0:
                warnings.append(f"{label}: la prima fermata non è al minuto 0")
            used_stops.add(stop_id)
            if stop_id not in stop_ids:
                errors.append(f"{label}: la fermata {stop_id} (posizione {pos}) non esiste")
            if offset < 0 or offset < previous:
                errors.append(f"{label}: i minuti alla fermata {pos} ({offset}) tornano indietro")
            previous = max(previous, offset)
        departures = line.get("partenze") or []
        if not departures:
            warnings.append(f"{label}: nessuna partenza")
        seen: set[str] = set()
        for departure in departures:
            if not RX_TIME.match(str(departure)):
                errors.append(f"{label}: orario di partenza non valido «{departure}» (HH:MM)")
            elif departure in seen:
                errors.append(f"{label}: partenza delle {departure} ripetuta")
            seen.add(departure)
        if key not in shapes:
            warnings.append(f"{label}: nessun tracciato stradale, sulla mappa le fermate sono unite in linea retta")
    for stop_id in sorted(stop_ids - used_stops):
        warnings.append(f"Fermata {stop_id}: non è servita da nessuna linea")
    for service_id in sorted(set(services) - used_services):
        warnings.append(f"Calendario {service_id}: non usato da nessuna linea")
    return errors, warnings


# ===================================================================== import da un GTFS qualsiasi
def _read_txt(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))


def _seconds(hms: str) -> int:
    hours, minutes, *rest = (hms or "0:0").strip().split(":")
    return int(hours) * 3600 + int(minutes) * 60 + int(rest[0] if rest else 0)


def read_gtfs_folder(folder: Path) -> dict[str, str]:
    return {f.name: f.read_text(encoding="utf-8") for f in folder.glob("*.txt")}


def from_gtfs(files: dict[str, str]) -> dict:
    """Sorgenti da un feed GTFS ({nome file: testo}): le corse con stesso percorso e tempi diventano una voce."""
    stops_txt = _read_txt(files["stops.txt"])
    routes = {r["route_id"]: r for r in _read_txt(files["routes.txt"])}
    trips = _read_txt(files["trips.txt"])
    stop_times = _read_txt(files["stop_times.txt"])
    calendars = _read_txt(files.get("calendar.txt", ""))
    calendar_dates = _read_txt(files.get("calendar_dates.txt", ""))
    agency_row = (_read_txt(files.get("agency.txt", "")) or [{}])[0]
    feed_info_row = (_read_txt(files.get("feed_info.txt", "")) or [{}])[0]
    shape_points: dict[str, list[tuple[int, list[float]]]] = {}
    for r in _read_txt(files.get("shapes.txt", "")):
        shape_points.setdefault(r["shape_id"], []).append(
            (int(r["shape_pt_sequence"]), [round(float(r["shape_pt_lat"]), 6), round(float(r["shape_pt_lon"]), 6)]))

    stops = []
    for r in stops_txt:
        if r.get("location_type") not in (None, "", "0"):
            continue
        source = r.get("posizione") or "gtfs"
        stops.append({"stop_id": r["stop_id"], "stop_code": r.get("stop_code", ""), "stop_name": r["stop_name"],
                      "linee": "", "tipologia": "", "nota": r.get("stop_desc", ""), "ricerca": "",
                      "lat": "" if source == "provvisoria" else r.get("stop_lat", ""),
                      "lon": "" if source == "provvisoria" else r.get("stop_lon", ""),
                      "fonte": "" if source == "provvisoria" else source})

    by_trip: dict[str, list[tuple[int, str, int]]] = {}
    for r in stop_times:
        t = r.get("departure_time") or r.get("arrival_time")
        if t:
            by_trip.setdefault(r["trip_id"], []).append((int(r["stop_sequence"]), r["stop_id"], _seconds(t)))

    groups: dict[tuple, dict] = {}
    for trip in trips:
        rows = sorted(by_trip.get(trip["trip_id"], []))
        if len(rows) < 2:
            continue
        t0 = rows[0][2]
        path = tuple((stop_id, round((sec - t0) / 60)) for _, stop_id, sec in rows)
        group_key = (trip["route_id"], trip["service_id"], trip.get("trip_headsign", ""),
                     trip.get("direction_id") or "0", path)
        group = groups.setdefault(group_key, {"departures": set(), "shape": trip.get("shape_id", "")})
        group["departures"].add(f"{t0 // 3600:02d}:{t0 % 3600 // 60:02d}")

    lines, shapes, counter = [], {}, {}
    for (route_id, service_id, headsign, direction, path), group in sorted(groups.items(), key=lambda x: x[0][:2]):
        route = routes.get(route_id, {"route_id": route_id})
        counter[route_id] = counter.get(route_id, 0) + 1
        line = {"route_id": route_id, "route_short_name": route.get("route_short_name") or route_id,
                "route_long_name": route.get("route_long_name", ""),
                "route_color": (route.get("route_color") or "0066CC").upper(),
                "route_text_color": (route.get("route_text_color") or "FFFFFF").upper(),
                "service_id": service_id, "headsign": headsign or route.get("route_long_name") or route_id,
                "percorso": [list(p) for p in path], "partenze": sorted(group["departures"])}
        if direction != "0":
            line["direzione"] = int(direction)
        if counter[route_id] > 1:
            line["id"] = f"{route_id}-{counter[route_id]}"
        lines.append(line)
        if group["shape"] in shape_points:
            shapes[variant_key(line)] = [p for _, p in sorted(shape_points[group["shape"]])]
    if not lines:
        raise InvalidSources("Il feed non contiene corse con almeno due fermate")

    services: dict[str, dict] = {}
    starts, ends = [], []
    for c in calendars:
        services[c["service_id"]] = {"service_id": c["service_id"],
                                     "giorni": "".join(c.get(day, "0") or "0" for day in WEEKDAYS),
                                     "inizio": c.get("start_date", ""), "fine": c.get("end_date", ""),
                                     "eccezioni": []}
        starts.append(c.get("start_date", ""))
        ends.append(c.get("end_date", ""))
    for e in calendar_dates:
        c = services.setdefault(e["service_id"], {"service_id": e["service_id"], "giorni": "0000000",
                                                  "eccezioni": []})
        c["eccezioni"].append({"data": e["date"], "tipo": int(e["exception_type"])})
        starts.append(e["date"])
        ends.append(e["date"])
    for service_id in {line["service_id"] for line in lines} - set(services):
        services[service_id] = {"service_id": service_id, "giorni": "0000000", "eccezioni": []}

    feed_start = feed_info_row.get("feed_start_date") or min([d for d in starts if d] or
                                                              [date.today().strftime("%Y%m%d")])
    feed_end = feed_info_row.get("feed_end_date") or max([d for d in ends if d] or [feed_start])
    # le date dei calendari uguali alla validità del feed non servono
    for c in services.values():
        if c.get("inizio") in ("", feed_start):
            c.pop("inizio", None)
        if c.get("fine") in ("", feed_end):
            c.pop("fine", None)
    agency = {"agency_id": agency_row.get("agency_id") or "AGENZIA", "agency_name": agency_row.get("agency_name", ""),
              "agency_url": agency_row.get("agency_url", ""),
              "agency_timezone": agency_row.get("agency_timezone") or "Europe/Rome",
              "agency_lang": agency_row.get("agency_lang") or "it", "agency_phone": agency_row.get("agency_phone", "")}
    routes_cfg = {
        "agency": agency,
        "feed_info": {"feed_publisher_name": feed_info_row.get("feed_publisher_name") or agency["agency_name"],
                      "feed_publisher_url": feed_info_row.get("feed_publisher_url") or agency["agency_url"],
                      "feed_lang": feed_info_row.get("feed_lang") or "it", "feed_start_date": feed_start,
                      "feed_end_date": feed_end, "feed_version": feed_info_row.get("feed_version", "")},
        "calendar": list(services.values()),
        "linee": lines,
    }
    line_names = lines_by_stop(routes_cfg)
    for stop in stops:
        stop["linee"] = line_names.get(stop["stop_id"], "")
    return {"fermate": stops, "percorsi": routes_cfg, "forme": shapes}


def load_folder(folder: Path) -> dict:
    """Sorgenti di una cartella: i file sorgente se ci sono, altrimenti ricavate dai .txt GTFS."""
    return read_sources(folder) if has_sources(folder) else from_gtfs(read_gtfs_folder(folder))


# ===================================================================== tracciato stradale
def osrm_route(points: list[tuple[float, float]], osrm_url: str, client=None) -> list[list[float]]:
    """Tracciato su strada che passa per i punti (lat, lon), dal servizio OSRM indicato (profilo auto)."""
    import httpx

    coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
    url = f"{osrm_url.rstrip('/')}/{coords}?overview=full&geometries=geojson&continue_straight=false"
    http = client or httpx.Client(timeout=20, headers={"User-Agent": "quandopassa-backoffice/0.1"})
    response = http.get(url)
    response.raise_for_status()
    data = response.json()
    if data.get("code") != "Ok":
        raise InvalidSources(f"OSRM: {data.get('code')} {data.get('message', '')}".strip())
    return [[round(lat, 6), round(lon, 6)] for lon, lat in data["routes"][0]["geometry"]["coordinates"]]
