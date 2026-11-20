"""Database Postgres del backoffice: fermate, linee, orari, calendari, avvisi, impostazioni e registro delle modifiche.

Il database è la fonte dei dati per chi li modifica; l'app pubblica legge solo i file GTFS generati a ogni
salvataggio (admin.py), quindi continua a funzionare anche se il database non è raggiungibile.

Lo schema si crea e si aggiorna da solo all'avvio (tabella schema_version). Al primo avvio il database vuoto viene
popolato dal feed in uso (sources.load_folder).
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, datetime

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .alerts import KINDS
from .sources import lines_by_stop, parse_date

MIGRATIONS: list[str] = [
    # ------------------------------------------------------------------ 1: schema iniziale
    f"""
    CREATE TABLE feed_meta (
        key   text PRIMARY KEY,
        value jsonb NOT NULL
    );
    CREATE TABLE stops (
        stop_id     text PRIMARY KEY,
        stop_code   text NOT NULL DEFAULT '',
        stop_name   text NOT NULL,
        category    text NOT NULL DEFAULT '',
        note        text NOT NULL DEFAULT '',
        search_hint text NOT NULL DEFAULT '',
        lat         double precision CHECK (lat BETWEEN -90 AND 90),
        lon         double precision CHECK (lon BETWEEN -180 AND 180),
        source      text NOT NULL DEFAULT '',
        updated_at  timestamptz NOT NULL DEFAULT now(),
        CHECK ((lat IS NULL) = (lon IS NULL))
    );
    CREATE TABLE calendars (
        service_id text PRIMARY KEY,
        days       char(7) NOT NULL CHECK (days ~ '^[01]{{7}}$'),
        start_date date,
        end_date   date,
        note       text NOT NULL DEFAULT ''
    );
    CREATE TABLE calendar_exceptions (
        service_id     text NOT NULL REFERENCES calendars ON UPDATE CASCADE ON DELETE CASCADE,
        day            date NOT NULL,
        exception_type smallint NOT NULL CHECK (exception_type IN (1, 2)),
        PRIMARY KEY (service_id, day)
    );
    CREATE TABLE route_variants (
        variant_id   text PRIMARY KEY,
        route_id     text NOT NULL,
        short_name   text NOT NULL,
        long_name    text NOT NULL DEFAULT '',
        color        char(6) NOT NULL,
        text_color   char(6) NOT NULL,
        service_id   text NOT NULL REFERENCES calendars ON UPDATE CASCADE,
        headsign     text NOT NULL DEFAULT '',
        direction_id smallint NOT NULL DEFAULT 0 CHECK (direction_id IN (0, 1)),
        sort_order   integer NOT NULL DEFAULT 0,
        shape        jsonb
    );
    CREATE TABLE variant_stops (
        variant_id text NOT NULL REFERENCES route_variants ON UPDATE CASCADE ON DELETE CASCADE,
        position   integer NOT NULL,
        stop_id    text NOT NULL REFERENCES stops ON UPDATE CASCADE,
        minutes    integer NOT NULL CHECK (minutes >= 0),
        PRIMARY KEY (variant_id, position)
    );
    CREATE INDEX variant_stops_stop ON variant_stops (stop_id);
    CREATE TABLE variant_departures (
        variant_id text NOT NULL REFERENCES route_variants ON UPDATE CASCADE ON DELETE CASCADE,
        departure  text NOT NULL CHECK (departure ~ '^[0-4]?[0-9]:[0-5][0-9]$'),
        PRIMARY KEY (variant_id, departure)
    );
    CREATE TABLE alerts (
        id          bigserial PRIMARY KEY,
        kind        text NOT NULL CHECK (kind IN ({", ".join(f"'{k}'" for k in KINDS)})),
        title       text NOT NULL,
        description text NOT NULL DEFAULT '',
        starts_at   timestamptz NOT NULL,
        ends_at     timestamptz,
        route_ids   text[] NOT NULL DEFAULT '{{}}',
        stop_ids    text[] NOT NULL DEFAULT '{{}}',
        shape       jsonb,
        created_by  text NOT NULL DEFAULT '',
        created_at  timestamptz NOT NULL DEFAULT now(),
        updated_at  timestamptz NOT NULL DEFAULT now(),
        CHECK (ends_at IS NULL OR ends_at > starts_at),
        CHECK (kind <> 'service_suspended' OR ends_at IS NOT NULL)
    );
    CREATE INDEX alerts_period ON alerts (ends_at, starts_at);
    CREATE TABLE settings (
        key        text PRIMARY KEY,
        value      text NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE audit_log (
        id       bigserial PRIMARY KEY,
        at       timestamptz NOT NULL DEFAULT now(),
        username text NOT NULL,
        action   text NOT NULL,
        target   text NOT NULL DEFAULT '',
        details  jsonb
    );
    CREATE INDEX audit_log_at ON audit_log (at DESC);
    """,
]

# blocco consultivo: una sola rigenerazione del feed per volta, anche con più processi
FEED_LOCK = 72_710_001


def _yyyymmdd(d: date | None) -> str:
    return d.strftime("%Y%m%d") if d else ""


def _date(text: str | None) -> date | None:
    return parse_date(text) if text else None


class Database:
    def __init__(self, url: str):
        self.url = url

    @contextmanager
    def connect(self):
        """Connessione con una transazione: commit all'uscita, rollback se c'è un'eccezione."""
        with psycopg.connect(self.url, row_factory=dict_row, connect_timeout=5) as conn:
            with conn.transaction():
                yield conn

    # ================================================================= schema e primo avvio
    def migrate(self) -> int:
        with self.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version integer PRIMARY KEY, "
                         "applied_at timestamptz NOT NULL DEFAULT now())")
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (FEED_LOCK,))
            current = conn.execute("SELECT coalesce(max(version), 0) AS v FROM schema_version").fetchone()["v"]
            for version, sql in enumerate(MIGRATIONS, start=1):
                if version > current:
                    conn.execute(sql)
                    conn.execute("INSERT INTO schema_version (version) VALUES (%s)", (version,))
            return len(MIGRATIONS)

    @staticmethod
    def is_empty(conn) -> bool:
        return conn.execute("SELECT NOT EXISTS (SELECT 1 FROM stops) AND NOT EXISTS "
                            "(SELECT 1 FROM route_variants) AS empty").fetchone()["empty"]

    def seed(self, conn, src: dict) -> None:
        """Popola il database vuoto dalle sorgenti di un feed (formato di sources.py)."""
        cfg = src["percorsi"]
        self.save_feed_meta(conn, cfg["agency"], cfg["feed_info"])
        for stop in src["fermate"]:
            self.save_stop(conn, None, {
                "stop_id": stop["stop_id"], "stop_code": stop.get("stop_code", ""), "stop_name": stop["stop_name"],
                "category": stop.get("tipologia", ""), "note": stop.get("nota", ""),
                "search_hint": stop.get("ricerca", ""),
                "lat": float(stop["lat"]) if stop.get("lat") else None,
                "lon": float(stop["lon"]) if stop.get("lon") else None, "source": stop.get("fonte", "")})
        for c in cfg["calendar"]:
            self.save_calendar(conn, None, {
                "service_id": c["service_id"], "days": c["giorni"], "note": c.get("nota", ""),
                "start_date": _date(c.get("inizio")), "end_date": _date(c.get("fine")),
                "exceptions": [{"day": _date(e["data"]), "type": int(e["tipo"])} for e in c.get("eccezioni", [])]})
        shapes = src.get("forme") or {}
        for order, line in enumerate(cfg["linee"]):
            key = str(line.get("id") or line["route_id"])
            self.save_variant(conn, None, {
                "variant_id": key, "route_id": line["route_id"], "short_name": line["route_short_name"],
                "long_name": line.get("route_long_name", ""), "color": line["route_color"].upper(),
                "text_color": line["route_text_color"].upper(), "service_id": line["service_id"],
                "headsign": line.get("headsign", ""), "direction_id": int(line.get("direzione", 0)),
                "sort_order": order, "shape": shapes.get(key),
                "stops": [{"stop_id": sid, "minutes": int(m)} for sid, m in line["percorso"]],
                "departures": list(line["partenze"])})

    # ================================================================= lettura
    def snapshot(self, conn) -> dict:
        """Tutti i dati modificabili, nel formato usato dal backoffice."""
        meta = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM feed_meta")}
        stops = conn.execute("SELECT stop_id, stop_code, stop_name, category, note, search_hint, lat, lon, source, "
                             "updated_at FROM stops ORDER BY stop_code, stop_id").fetchall()
        calendars = conn.execute("SELECT service_id, days, start_date, end_date, note FROM calendars "
                                 "ORDER BY service_id").fetchall()
        exceptions: dict[str, list] = {}
        for r in conn.execute("SELECT service_id, day, exception_type FROM calendar_exceptions ORDER BY day"):
            exceptions.setdefault(r["service_id"], []).append({"day": r["day"], "type": r["exception_type"]})
        for c in calendars:
            c["exceptions"] = exceptions.get(c["service_id"], [])
        variants = conn.execute("SELECT * FROM route_variants ORDER BY sort_order, variant_id").fetchall()
        path: dict[str, list] = {}
        for r in conn.execute("SELECT variant_id, stop_id, minutes FROM variant_stops ORDER BY variant_id, position"):
            path.setdefault(r["variant_id"], []).append({"stop_id": r["stop_id"], "minutes": r["minutes"]})
        departures: dict[str, list] = {}
        for r in conn.execute("SELECT variant_id, departure FROM variant_departures"):
            departures.setdefault(r["variant_id"], []).append(r["departure"])
        for v in variants:
            v["stops"] = path.get(v["variant_id"], [])
            v["departures"] = sorted(departures.get(v["variant_id"], []), key=lambda t: (len(t), t))
        return {"agency": meta.get("agency", {}), "feed_info": meta.get("feed_info", {}), "stops": stops,
                "calendars": calendars, "variants": variants}

    def load_sources(self, conn) -> dict:
        """I dati del database nel formato delle sorgenti (fermate.csv, percorsi.json, forme.json)."""
        snap = self.snapshot(conn)
        lines, shapes = [], {}
        for v in snap["variants"]:
            line = {"route_id": v["route_id"], "route_short_name": v["short_name"], "route_long_name": v["long_name"],
                    "route_color": v["color"], "route_text_color": v["text_color"], "service_id": v["service_id"],
                    "headsign": v["headsign"], "percorso": [[s["stop_id"], s["minutes"]] for s in v["stops"]],
                    "partenze": v["departures"]}
            if v["variant_id"] != v["route_id"]:
                line["id"] = v["variant_id"]
            if v["direction_id"]:
                line["direzione"] = v["direction_id"]
            lines.append(line)
            if v["shape"]:
                shapes[v["variant_id"]] = v["shape"]
        calendar = []
        for c in snap["calendars"]:
            item = {"service_id": c["service_id"], "giorni": c["days"]}
            if c["start_date"]:
                item["inizio"] = _yyyymmdd(c["start_date"])
            if c["end_date"]:
                item["fine"] = _yyyymmdd(c["end_date"])
            if c["note"]:
                item["nota"] = c["note"]
            item["eccezioni"] = [{"data": _yyyymmdd(e["day"]), "tipo": e["type"]} for e in c["exceptions"]]
            calendar.append(item)
        routes_cfg = {"_nota": "Generato dal backoffice di QuandoPassa: modificare i dati dal backoffice.",
                      "agency": snap["agency"], "feed_info": snap["feed_info"], "calendar": calendar, "linee": lines}
        line_names = lines_by_stop(routes_cfg)
        stops = [{"stop_id": s["stop_id"], "stop_code": s["stop_code"], "stop_name": s["stop_name"],
                  "linee": line_names.get(s["stop_id"], ""), "tipologia": s["category"], "nota": s["note"],
                  "ricerca": s["search_hint"], "lat": f"{s['lat']:.6f}" if s["lat"] is not None else "",
                  "lon": f"{s['lon']:.6f}" if s["lon"] is not None else "", "fonte": s["source"]}
                 for s in snap["stops"]]
        return {"fermate": stops, "percorsi": routes_cfg, "forme": shapes}

    @staticmethod
    def list_alerts(conn, not_ended_at: datetime | None = None) -> list[dict]:
        """Tutti gli avvisi, oppure solo quelli non ancora finiti all'istante dato (orologio del servizio)."""
        if not_ended_at is None:
            return conn.execute("SELECT * FROM alerts ORDER BY starts_at DESC, id DESC").fetchall()
        return conn.execute("SELECT * FROM alerts WHERE ends_at IS NULL OR ends_at > %s "
                            "ORDER BY starts_at DESC, id DESC", (not_ended_at,)).fetchall()

    # ================================================================= scrittura
    @staticmethod
    def save_feed_meta(conn, agency: dict, feed_info: dict) -> None:
        for key, value in (("agency", agency), ("feed_info", feed_info)):
            conn.execute("INSERT INTO feed_meta (key, value) VALUES (%s, %s) "
                         "ON CONFLICT (key) DO UPDATE SET value = excluded.value", (key, Jsonb(value)))

    @staticmethod
    def save_stop(conn, old_id: str | None, s: dict) -> None:
        values = (s["stop_id"], s.get("stop_code", ""), s["stop_name"], s.get("category", ""), s.get("note", ""),
                  s.get("search_hint", ""), s.get("lat"), s.get("lon"), s.get("source", ""))
        if old_id is None:
            conn.execute("INSERT INTO stops (stop_id, stop_code, stop_name, category, note, search_hint, lat, lon, "
                         "source) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", values)
            return
        cur = conn.execute("UPDATE stops SET stop_id=%s, stop_code=%s, stop_name=%s, category=%s, note=%s, "
                           "search_hint=%s, lat=%s, lon=%s, source=%s, updated_at=now() WHERE stop_id=%s",
                           (*values, old_id))
        if cur.rowcount == 0:
            raise KeyError(old_id)
        if old_id != s["stop_id"]:
            conn.execute("UPDATE alerts SET stop_ids = array_replace(stop_ids, %s, %s)", (old_id, s["stop_id"]))

    @staticmethod
    def delete_stop(conn, stop_id: str) -> None:
        if conn.execute("DELETE FROM stops WHERE stop_id=%s", (stop_id,)).rowcount == 0:
            raise KeyError(stop_id)
        conn.execute("UPDATE alerts SET stop_ids = array_remove(stop_ids, %s)", (stop_id,))

    @staticmethod
    def save_calendar(conn, old_id: str | None, c: dict) -> None:
        values = (c["service_id"], c["days"], c.get("start_date"), c.get("end_date"), c.get("note", ""))
        if old_id is None:
            conn.execute("INSERT INTO calendars (service_id, days, start_date, end_date, note) "
                         "VALUES (%s, %s, %s, %s, %s)", values)
        elif conn.execute("UPDATE calendars SET service_id=%s, days=%s, start_date=%s, end_date=%s, note=%s "
                          "WHERE service_id=%s", (*values, old_id)).rowcount == 0:
            raise KeyError(old_id)
        conn.execute("DELETE FROM calendar_exceptions WHERE service_id=%s", (c["service_id"],))
        for e in c.get("exceptions", []):
            conn.execute("INSERT INTO calendar_exceptions (service_id, day, exception_type) VALUES (%s, %s, %s) "
                         "ON CONFLICT (service_id, day) DO UPDATE SET exception_type = excluded.exception_type",
                         (c["service_id"], e["day"], e["type"]))

    @staticmethod
    def delete_calendar(conn, service_id: str) -> None:
        if conn.execute("DELETE FROM calendars WHERE service_id=%s", (service_id,)).rowcount == 0:
            raise KeyError(service_id)

    @staticmethod
    def save_variant(conn, old_id: str | None, v: dict) -> None:
        shape = Jsonb(v["shape"]) if v.get("shape") else None
        values = (v["variant_id"], v["route_id"], v["short_name"], v.get("long_name", ""), v["color"],
                  v["text_color"], v["service_id"], v.get("headsign", ""), v.get("direction_id", 0),
                  v.get("sort_order", 0))
        if old_id is None:
            conn.execute("INSERT INTO route_variants (variant_id, route_id, short_name, long_name, color, text_color, "
                         "service_id, headsign, direction_id, sort_order, shape) "
                         "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", (*values, shape))
        else:
            sql = ("UPDATE route_variants SET variant_id=%s, route_id=%s, short_name=%s, long_name=%s, color=%s, "
                   "text_color=%s, service_id=%s, headsign=%s, direction_id=%s, sort_order=%s")
            params = list(values)
            if "shape" in v:
                sql += ", shape=%s"
                params.append(shape)
            if conn.execute(sql + " WHERE variant_id=%s", (*params, old_id)).rowcount == 0:
                raise KeyError(old_id)
        # nome e colori sono della linea: uguali per tutte le sue varianti
        conn.execute("UPDATE route_variants SET short_name=%s, long_name=%s, color=%s, text_color=%s "
                     "WHERE route_id=%s AND variant_id<>%s",
                     (v["short_name"], v.get("long_name", ""), v["color"], v["text_color"], v["route_id"],
                      v["variant_id"]))
        conn.execute("DELETE FROM variant_stops WHERE variant_id=%s", (v["variant_id"],))
        for pos, s in enumerate(v.get("stops", []), start=1):
            conn.execute("INSERT INTO variant_stops (variant_id, position, stop_id, minutes) VALUES (%s, %s, %s, %s)",
                         (v["variant_id"], pos, s["stop_id"], s["minutes"]))
        conn.execute("DELETE FROM variant_departures WHERE variant_id=%s", (v["variant_id"],))
        for d in dict.fromkeys(v.get("departures", [])):
            conn.execute("INSERT INTO variant_departures (variant_id, departure) VALUES (%s, %s)",
                         (v["variant_id"], d))

    @staticmethod
    def set_shape(conn, variant_id: str, points: list | None) -> None:
        cur = conn.execute("UPDATE route_variants SET shape=%s WHERE variant_id=%s",
                           (Jsonb(points) if points else None, variant_id))
        if cur.rowcount == 0:
            raise KeyError(variant_id)

    @staticmethod
    def delete_variant(conn, variant_id: str) -> None:
        if conn.execute("DELETE FROM route_variants WHERE variant_id=%s", (variant_id,)).rowcount == 0:
            raise KeyError(variant_id)

    @staticmethod
    def save_alert(conn, alert_id: int | None, a: dict, username: str) -> int:
        values = (a["kind"], a["title"], a.get("description", ""), a["starts_at"], a.get("ends_at"),
                  list(a.get("route_ids", [])), list(a.get("stop_ids", [])),
                  Jsonb(a["shape"]) if a.get("shape") else None)
        if alert_id is None:
            row = conn.execute("INSERT INTO alerts (kind, title, description, starts_at, ends_at, route_ids, stop_ids, "
                               "shape, created_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                               (*values, username)).fetchone()
            return row["id"]
        cur = conn.execute("UPDATE alerts SET kind=%s, title=%s, description=%s, starts_at=%s, ends_at=%s, "
                           "route_ids=%s, stop_ids=%s, shape=%s, updated_at=now() WHERE id=%s", (*values, alert_id))
        if cur.rowcount == 0:
            raise KeyError(alert_id)
        return alert_id

    @staticmethod
    def delete_alert(conn, alert_id: int) -> None:
        if conn.execute("DELETE FROM alerts WHERE id=%s", (alert_id,)).rowcount == 0:
            raise KeyError(alert_id)

    @staticmethod
    def get_settings(conn) -> dict[str, str]:
        return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}

    @staticmethod
    def save_settings(conn, values: dict[str, str | None]) -> None:
        for key, value in values.items():
            if value is None:
                conn.execute("DELETE FROM settings WHERE key=%s", (key,))
            else:
                conn.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE "
                             "SET value = excluded.value, updated_at = now()", (key, value))

    # ================================================================= registro
    @staticmethod
    def audit(conn, username: str, action: str, target: str = "", details: dict | None = None) -> None:
        conn.execute("INSERT INTO audit_log (username, action, target, details) VALUES (%s, %s, %s, %s)",
                     (username, action, target, Jsonb(json.loads(json.dumps(details, default=str)))
                      if details else None))

    @staticmethod
    def list_audit(conn, limit: int = 200) -> list[dict]:
        return conn.execute("SELECT id, at, username, action, target, details FROM audit_log "
                            "ORDER BY at DESC, id DESC LIMIT %s", (limit,)).fetchall()


def to_iso(value):
    """datetime/date in testo ISO per le risposte JSON."""
    if isinstance(value, datetime):
        return value.isoformat(timespec="minutes")
    if isinstance(value, date):
        return value.isoformat()
    return value
