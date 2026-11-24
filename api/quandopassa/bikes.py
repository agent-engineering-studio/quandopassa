"""Bike sharing: stazioni gestite dal backoffice o importate da un feed GBFS, disponibilità letta lato server.

GBFS (General Bikeshare Feed Specification, https://gbfs.org) è per il bike sharing quello che GTFS è per i bus.
Il backoffice tiene in Postgres i sistemi (gestore, link all'app, indirizzi del feed) e l'anagrafica delle stazioni;
a ogni salvataggio scrive `bike_sharing.json` accanto al feed GTFS e l'app pubblica legge solo quel file.

L'import accetta GBFS v2.x e v3.0:

  gbfs.json                  autodiscovery: elenco degli altri file (con o senza lingua)
  system_information.json    nome del sistema, gestore, app per il noleggio
  station_information.json   anagrafica delle stazioni (posizione, nome, capacità)
  station_status.json        bici e stalli liberi: dato in tempo reale, non si importa ma si legge con una cache

La disponibilità la chiede il server al gestore, una volta per tutti e rispettando il `ttl` del feed: la posizione
di chi usa l'app non arriva mai a terzi. Se il gestore non risponde le stazioni restano visibili senza i numeri.
"""
from __future__ import annotations

import io
import json
import math
import threading
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .gtfs import metri, minuti_a_piedi

BIKES_FILE = "bike_sharing.json"
GBFS_FILES = ("gbfs", "system_information", "station_information", "station_status")
MAX_FEED_BYTES = 5 * 1024 * 1024
MAX_STATIONS = 5000
STATUS_TTL_MIN, STATUS_TTL_MAX, STATUS_TTL_DEFAULT = 30, 300, 60
STATUS_STALE_AFTER = 15 * 60       # oltre questa età i numeri non si mostrano più
NEARBY_STOP_METERS = 300           # fermate del bus "vicine" a una stazione
USER_AGENT = "quandopassa/0.1 (+https://github.com/agent-engineering-studio/quandopassa)"


class GbfsError(ValueError):
    """Il feed GBFS non si può leggere o non contiene le stazioni."""


# ===================================================================== lettura dei documenti GBFS
def localized(value, lang: str = "it") -> str:
    """Testo GBFS: stringa (v2) oppure elenco [{text, language}] (v3), si preferisce la lingua indicata."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        texts = [v for v in value if isinstance(v, dict) and isinstance(v.get("text"), str)]
        for v in texts:
            if str(v.get("language", "")).lower().startswith(lang):
                return v["text"].strip()
        return texts[0]["text"].strip() if texts else ""
    return ""


def _data(doc) -> dict:
    if not isinstance(doc, dict) or not isinstance(doc.get("data"), dict):
        raise GbfsError("non è un documento GBFS: manca l'oggetto «data»")
    return doc["data"]


def detect(doc) -> str | None:
    """Quale file GBFS è il documento (gbfs, system_information, station_information, station_status)."""
    try:
        data = _data(doc)
    except GbfsError:
        return None
    stations = data.get("stations")
    if isinstance(stations, list):
        sample = next((s for s in stations if isinstance(s, dict)), {})
        if "num_bikes_available" in sample or "num_vehicles_available" in sample:
            return "station_status"
        if "lat" in sample or "name" in sample or not stations:
            return "station_information"
    if isinstance(data.get("feeds"), list) or any(isinstance(v, dict) and isinstance(v.get("feeds"), list)
                                                  for v in data.values()):
        return "gbfs"
    if "system_id" in data or ("name" in data and "timezone" in data):
        return "system_information"
    return None


def feed_urls(doc, lang: str = "it") -> dict[str, str]:
    """Dall'autodiscovery gbfs.json: {nome del file: url}. v3 ha data.feeds, v2 data.<lingua>.feeds."""
    data = _data(doc)
    feeds = data.get("feeds")
    if not isinstance(feeds, list):
        langs = [k for k, v in data.items() if isinstance(v, dict) and isinstance(v.get("feeds"), list)]
        if not langs:
            raise GbfsError("gbfs.json senza elenco dei feed")
        chosen = next((k for k in langs if k.lower().startswith(lang)), None) or next(
            (k for k in langs if k.lower().startswith("en")), langs[0])
        feeds = data[chosen]["feeds"]
    return {f["name"]: f["url"] for f in feeds
            if isinstance(f, dict) and isinstance(f.get("name"), str) and isinstance(f.get("url"), str)}


def parse_system_information(doc) -> dict:
    data = _data(doc)
    apps = data.get("rental_apps") or {}
    app_url = ""
    for platform in ("android", "ios"):
        uri = (apps.get(platform) or {}).get("store_uri") if isinstance(apps, dict) else None
        if isinstance(uri, str) and uri.startswith("https://"):
            app_url = uri
            break
    return {"system_id": str(data.get("system_id", "")).strip(), "name": localized(data.get("name")),
            "operator": localized(data.get("operator")), "url": str(data.get("url") or "").strip(),
            "app_url": app_url, "license_url": str(data.get("license_url") or "").strip()}


def _station_id(value) -> str:
    sid = str(value if value is not None else "").strip()
    return sid if 0 < len(sid) <= 64 and "/" not in sid and sid.isprintable() else ""


def parse_station_information(doc, lang: str = "it") -> tuple[list[dict], list[str]]:
    """Stazioni del feed nel formato del database, più gli avvisi sulle righe scartate."""
    stations = _data(doc).get("stations")
    if not isinstance(stations, list):
        raise GbfsError("station_information senza elenco «stations»")
    if len(stations) > MAX_STATIONS:
        raise GbfsError(f"troppe stazioni ({len(stations)}): al massimo {MAX_STATIONS}")
    out, warnings, seen = [], [], set()
    for i, s in enumerate(stations, start=1):
        if not isinstance(s, dict):
            warnings.append(f"riga {i}: non è un oggetto, scartata")
            continue
        sid = _station_id(s.get("station_id"))
        name = localized(s.get("name"), lang)[:150]
        try:
            lat, lon = float(s.get("lat")), float(s.get("lon"))
        except (TypeError, ValueError):
            lat = lon = math.nan
        if not sid:
            warnings.append(f"riga {i}: station_id mancante o non valido, scartata")
            continue
        if sid in seen:
            warnings.append(f"stazione {sid}: ripetuta, tenuta la prima")
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            warnings.append(f"stazione {sid}: coordinate non valide, scartata")
            continue
        capacity = s.get("capacity")
        seen.add(sid)
        out.append({"station_id": sid, "name": name or sid, "short_name": localized(s.get("short_name"), lang)[:40],
                    "address": str(s.get("address") or "").strip()[:200], "lat": round(lat, 6),
                    "lon": round(lon, 6),
                    "capacity": int(capacity) if isinstance(capacity, (int, float)) and capacity >= 0 else None})
    return out, warnings


def _reported(value) -> str | None:
    if isinstance(value, (int, float)) and value > 0:            # v2: secondi POSIX
        return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds")
    if isinstance(value, str) and value:                         # v3: RFC 3339
        return value
    return None


def parse_station_status(doc) -> dict[str, dict]:
    """{station_id: {bikes, docks, renting, returning, reported_at}} per le stazioni installate."""
    stations = _data(doc).get("stations")
    if not isinstance(stations, list):
        raise GbfsError("station_status senza elenco «stations»")
    out = {}
    for s in stations:
        if not isinstance(s, dict) or s.get("is_installed") is False:
            continue
        sid = _station_id(s.get("station_id"))
        if not sid:
            continue
        bikes = s.get("num_bikes_available", s.get("num_vehicles_available"))
        docks = s.get("num_docks_available")
        out[sid] = {"bikes": int(bikes) if isinstance(bikes, (int, float)) else None,
                    "docks": int(docks) if isinstance(docks, (int, float)) else None,
                    "renting": s.get("is_renting") is not False, "returning": s.get("is_returning") is not False,
                    "reported_at": _reported(s.get("last_reported"))}
    return out


def ttl_of(doc) -> int:
    ttl = doc.get("ttl") if isinstance(doc, dict) else None
    ttl = int(ttl) if isinstance(ttl, (int, float)) and ttl > 0 else STATUS_TTL_DEFAULT
    return min(max(ttl, STATUS_TTL_MIN), STATUS_TTL_MAX)


# ===================================================================== fonti: file caricato o URL
def _json(content: bytes, name: str):
    try:
        return json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        raise GbfsError(f"{name}: non è un file JSON valido") from None


def read_upload(content: bytes) -> dict[str, dict]:
    """File caricato dal backoffice: un JSON GBFS (riconosciuto dal contenuto) o uno zip con i file del feed."""
    if len(content) > MAX_FEED_BYTES:
        raise GbfsError(f"file troppo grande: al massimo {MAX_FEED_BYTES // 1024 // 1024} MB")
    if content[:4] == b"PK\x03\x04":
        docs = {}
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                for info in z.infolist():
                    stem = Path(info.filename).name.removesuffix(".json")
                    if info.is_dir() or stem not in GBFS_FILES:
                        continue
                    if info.file_size > MAX_FEED_BYTES:
                        raise GbfsError(f"{info.filename}: file troppo grande")
                    docs[stem] = _json(z.read(info), info.filename)
        except zipfile.BadZipFile:
            raise GbfsError("archivio zip non valido") from None
        if not docs:
            raise GbfsError("nello zip non ci sono file GBFS (station_information.json, ...)")
        return docs
    doc = _json(content, "file")
    kind = detect(doc)
    if not kind:
        raise GbfsError("il file non è un documento GBFS riconosciuto")
    return {kind: doc}


def _check_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("https://", "http://")) or len(url) > 500:
        raise GbfsError("serve un indirizzo che inizi con https://")
    return url


def fetch_json(url: str, client) -> dict:
    """Scarica un documento GBFS con limiti di tempo e dimensione."""
    url = _check_url(url)
    try:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_FEED_BYTES:
                    raise GbfsError(f"{url}: risposta troppo grande")
                chunks.append(chunk)
    except GbfsError:
        raise
    except Exception as e:  # rete, stato HTTP, timeout
        raise GbfsError(f"{url}: download non riuscito ({e.__class__.__name__}: {e})") from None
    return _json(b"".join(chunks), url)


def http_client(timeout: float = 10):
    import httpx

    return httpx.Client(timeout=timeout, follow_redirects=True, max_redirects=3,
                        headers={"User-Agent": USER_AGENT, "Accept": "application/json"})


def fetch_feed(url: str, client=None, lang: str = "it") -> tuple[dict[str, dict], dict[str, str]]:
    """Da un URL GBFS (autodiscovery o station_information) i documenti utili e gli indirizzi dei file."""
    http = client or http_client()
    first = fetch_json(url, http)
    kind = detect(first)
    if kind is None:
        raise GbfsError("l'indirizzo non restituisce un documento GBFS riconosciuto")
    docs, urls = {kind: first}, {kind: url}
    if kind == "gbfs":
        listed = feed_urls(first, lang)
        if "station_information" not in listed:
            raise GbfsError("il feed non pubblica station_information: non è un sistema a stazioni")
        for name in ("system_information", "station_information"):
            if name in listed:
                docs[name] = fetch_json(listed[name], http)
        urls.update({k: v for k, v in listed.items() if k in GBFS_FILES})
    return docs, urls


# ===================================================================== import: differenze con il database
def plan_import(existing: list[dict], incoming: list[dict], remove_missing: bool) -> dict:
    """Cosa cambia importando `incoming` in un sistema che ha già le stazioni `existing`.

    Le stazioni modificate a mano (source «manuale») non vengono toccate: restano come le ha salvate l'ufficio.
    Con `remove_missing` si tolgono le stazioni importate in passato che il feed non pubblica più.
    """
    fields = ("name", "short_name", "address", "lat", "lon", "capacity")
    current = {s["station_id"]: s for s in existing}
    added, updated, unchanged, kept_manual = [], [], [], []
    for s in incoming:
        old = current.get(s["station_id"])
        if old is None:
            added.append(s)
        elif old.get("source") == "manuale":
            kept_manual.append(s["station_id"])
        elif any(old.get(k) != s.get(k) for k in fields) or not old.get("active", True):
            updated.append(s)
        else:
            unchanged.append(s["station_id"])
    ids = {s["station_id"] for s in incoming}
    missing = [s["station_id"] for s in existing if s["station_id"] not in ids and s.get("source") == "gbfs"]
    return {"added": added, "updated": updated, "unchanged": unchanged, "kept_manual": kept_manual,
            "removed": missing if remove_missing else [], "missing": missing}


def plan_summary(plan: dict) -> dict:
    """Riepilogo leggibile (per la risposta e per il registro)."""
    return {"added": [s["station_id"] for s in plan["added"]], "updated": [s["station_id"] for s in plan["updated"]],
            "unchanged": len(plan["unchanged"]), "kept_manual": plan["kept_manual"], "removed": plan["removed"],
            "missing": plan["missing"]}


# ===================================================================== disponibilità in tempo reale
@dataclass
class _Entry:
    fetched: float = 0.0
    ttl: int = STATUS_TTL_DEFAULT
    data: dict[str, dict] = field(default_factory=dict)
    error: str = ""
    retry_after: float = 0.0


class StatusCache:
    """station_status di ogni sistema, scaricato al massimo una volta per ttl, condiviso da tutte le richieste."""

    def __init__(self, client=None, clock=time.monotonic):
        self.client = client
        self.clock = clock
        self.entries: dict[str, _Entry] = {}
        self.lock = threading.Lock()

    def get(self, url: str) -> tuple[dict[str, dict], float | None, str]:
        """(disponibilità per stazione, età in secondi o None, errore). Non solleva eccezioni."""
        now = self.clock()
        with self.lock:
            entry = self.entries.setdefault(url, _Entry())
            fresh = entry.fetched and now - entry.fetched < entry.ttl
            if not fresh and now >= entry.retry_after:
                try:
                    doc = fetch_json(url, self.client or http_client(timeout=5))
                    entry.data, entry.ttl, entry.fetched, entry.error = parse_station_status(doc), ttl_of(doc), now, ""
                except GbfsError as e:
                    entry.error, entry.retry_after = str(e), now + STATUS_TTL_MIN
            age = now - entry.fetched if entry.fetched else None
            if age is not None and age > STATUS_STALE_AFTER:
                return {}, age, entry.error or "dati troppo vecchi"
            return entry.data, age, entry.error


# ===================================================================== dati pubblicati e ricerca
class BikeBoard:
    """Sistemi e stazioni pubblicati (bike_sharing.json), con la disponibilità se il gestore la fornisce."""

    def __init__(self, systems: list[dict], stations: list[dict], cache: StatusCache | None = None):
        self.systems = {s["system_id"]: s for s in systems}
        self.stations = [s for s in stations if s.get("active", True) and s["system_id"] in self.systems]
        self.cache = cache or StatusCache()

    @classmethod
    def load(cls, folder: Path, cache: StatusCache | None = None) -> "BikeBoard":
        path = folder / BIKES_FILE
        if not path.exists():
            return cls([], [], cache)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(data.get("systems", []), data.get("stations", []), cache)

    def __bool__(self) -> bool:
        return bool(self.stations)

    def systems_json(self) -> list[dict]:
        return [{"id": s["system_id"], "name": s["name"], "operator": s.get("operator", ""),
                 "app_url": s.get("app_url") or None, "live": bool(s.get("live") and s.get("status_url"))}
                for s in self.systems.values()]

    def _availability(self) -> dict[str, tuple[dict, float | None]]:
        out = {}
        for sid, system in self.systems.items():
            if system.get("live") and system.get("status_url"):
                data, age, _ = self.cache.get(system["status_url"])
                out[sid] = (data, age)
        return out

    def _json(self, s: dict, live: dict) -> dict:
        system = self.systems[s["system_id"]]
        item = {"id": s["station_id"], "system_id": s["system_id"], "system": system["name"], "name": s["name"],
                "short_name": s.get("short_name", ""), "address": s.get("address", ""), "lat": s["lat"],
                "lon": s["lon"], "capacity": s.get("capacity"), "app_url": system.get("app_url") or None,
                "live": False, "bikes": None, "docks": None}
        data, age = live.get(s["system_id"], ({}, None))
        status = data.get(s["station_id"])
        if status:
            item.update(live=True, bikes=status["bikes"], docks=status["docks"], renting=status["renting"],
                        returning=status["returning"], reported_at=status["reported_at"],
                        age_s=round(age) if age is not None else None)
        return item

    def all(self) -> list[dict]:
        live = self._availability()
        return [self._json(s, live) for s in sorted(self.stations, key=lambda s: (s["system_id"], s["name"]))]

    def nearby(self, lat: float, lon: float, n: int = 5, radius: float | None = None) -> list[dict]:
        rows = []
        for s in self.stations:
            d = metri((lat, lon), (s["lat"], s["lon"]))
            if radius is None or d <= radius:
                rows.append((d, s))
        rows.sort(key=lambda r: r[0])
        live = self._availability() if rows else {}
        return [{**self._json(s, live), "distance_m": round(d), "walk_min": minuti_a_piedi(d)} for d, s in rows[:n]]


def nearby_stops(lat: float, lon: float, stops: list[dict], radius: float = NEARBY_STOP_METERS,
                 n: int = 3) -> list[dict]:
    """Fermate del bus vicine a una stazione: per vedere a colpo d'occhio dove bus e bici si incontrano."""
    rows = []
    for s in stops:
        if s.get("lat") is None:
            continue
        d = metri((lat, lon), (s["lat"], s["lon"]))
        if d <= radius:
            rows.append({"stop_id": s["stop_id"], "stop_code": s.get("stop_code", ""), "name": s["stop_name"],
                         "meters": round(d)})
    return sorted(rows, key=lambda r: r["meters"])[:n]
