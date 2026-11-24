"""Backoffice di QuandoPassa: API /api/admin per l'ufficio trasporti.

Accesso con l'utente del .env (ADMIN_USER, ADMIN_PASSWORD_HASH): sessione in un cookie firmato HttpOnly,
SameSite=Strict, con token CSRF nell'intestazione X-CSRF-Token per ogni modifica e blocco dopo troppi tentativi.

Ogni modifica (fermate, linee, orari, calendari, dati del feed, avvisi, bike sharing, impostazioni) avviene in una transazione
Postgres che, prima del commit, rigenera e verifica il feed GTFS in una cartella temporanea. Se il feed ha errori
la modifica viene annullata; altrimenti la cartella sostituisce quella pubblicata e l'app la ricarica subito:
la mappa dei cittadini mostra la modifica alla richiesta successiva.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import logging
import re
import secrets
import shutil
import threading
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

import psycopg
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, field_validator, model_validator

from .alerts import ALERTS_FILE, Alert, AlertBoard, apply_suspensions
from .bikes import (BIKES_FILE, BikeBoard, GbfsError, feed_urls, fetch_feed, fetch_json, http_client, nearby_stops,
                    parse_station_information, parse_station_status, parse_system_information, plan_import,
                    plan_summary, read_upload, ttl_of)
from .config import EDITABLE_SETTINGS
from .db import FEED_LOCK, Database
from .gtfs import Orario
from .password import verify_password
from .sources import InvalidSources, build_gtfs, osrm_route, validate, write_atomic, write_sources

log = logging.getLogger("quandopassa.admin")

SESSION_COOKIE = "qp_admin"
SESSION_SECONDS = 8 * 3600
MAX_FAILURES = 5
FAILURE_WINDOW = 15 * 60
ID_PATTERN = r"^[A-Za-z0-9_.\-]{1,40}$"
TIME_PATTERN = r"^([0-4]?[0-9]):([0-5][0-9])$"
COLOR_PATTERN = r"^[0-9A-Fa-f]{6}$"
BIKE_STATION_PATTERN = r"^[^\s/]{1,64}$"   # gli id GBFS sono testo libero (numeri, UUID...)
URL_PATTERN = r"^(https?://[^\s<>\"]+)?$"


# ===================================================================== modelli delle richieste
class LoginBody(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)


class StopBody(BaseModel):
    stop_id: str = Field(pattern=ID_PATTERN)
    stop_code: str = Field("", max_length=20)
    stop_name: str = Field(min_length=1, max_length=120)
    category: str = Field("", max_length=60)
    note: str = Field("", max_length=500)
    search_hint: str = Field("", max_length=300)
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    source: str = Field("manuale", max_length=120)

    @model_validator(mode="after")
    def both_coordinates(self):
        if (self.lat is None) != (self.lon is None):
            raise ValueError("indicare sia la latitudine sia la longitudine, oppure nessuna delle due")
        return self


class CalendarException(BaseModel):
    day: date
    type: Literal[1, 2]


class CalendarBody(BaseModel):
    service_id: str = Field(pattern=ID_PATTERN)
    days: str = Field(pattern=r"^[01]{7}$")
    start_date: date | None = None
    end_date: date | None = None
    note: str = Field("", max_length=300)
    exceptions: list[CalendarException] = Field(default_factory=list, max_length=1000)


class VariantStop(BaseModel):
    stop_id: str = Field(pattern=ID_PATTERN)
    minutes: int = Field(ge=0, le=24 * 60)


class VariantBody(BaseModel):
    variant_id: str = Field(pattern=ID_PATTERN)
    route_id: str = Field(pattern=ID_PATTERN)
    short_name: str = Field(min_length=1, max_length=20)
    long_name: str = Field("", max_length=120)
    color: str = Field(pattern=COLOR_PATTERN)
    text_color: str = Field(pattern=COLOR_PATTERN)
    service_id: str = Field(pattern=ID_PATTERN)
    headsign: str = Field("", max_length=120)
    direction_id: Literal[0, 1] = 0
    sort_order: int = 0
    stops: list[VariantStop] = Field(min_length=2, max_length=300)
    departures: list[Annotated[str, Field(pattern=TIME_PATTERN)]] = Field(default_factory=list, max_length=500)

    @field_validator("color", "text_color")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.upper()

    @field_validator("departures")
    @classmethod
    def normalize_times(cls, values: list[str]) -> list[str]:
        out = []
        for v in values:
            h, m = v.split(":")
            out.append(f"{int(h):02d}:{m}")
        return out


class AgencyBody(BaseModel):
    agency_id: str = Field(pattern=ID_PATTERN)
    agency_name: str = Field(min_length=1, max_length=150)
    agency_url: str = Field(pattern=r"^https?://", max_length=300)
    agency_timezone: str = Field("Europe/Rome", max_length=60)
    agency_lang: str = Field("it", max_length=10)
    agency_phone: str = Field("", max_length=40)


class FeedInfoBody(BaseModel):
    feed_publisher_name: str = Field(min_length=1, max_length=150)
    feed_publisher_url: str = Field(pattern=r"^https?://", max_length=300)
    feed_lang: str = Field("it", max_length=10)
    feed_start_date: date
    feed_end_date: date


class FeedBody(BaseModel):
    agency: AgencyBody
    feed_info: FeedInfoBody


class ShapeBody(BaseModel):
    points: list[tuple[float, float]] | None = Field(None, max_length=20000)


class AlertBody(BaseModel):
    kind: Literal["info", "detour", "stop_closed", "service_suspended"]
    title: str = Field(min_length=3, max_length=120)
    description: str = Field("", max_length=2000)
    starts_at: datetime
    ends_at: datetime | None = None
    route_ids: list[Annotated[str, Field(pattern=ID_PATTERN)]] = Field(default_factory=list, max_length=100)
    stop_ids: list[Annotated[str, Field(pattern=ID_PATTERN)]] = Field(default_factory=list, max_length=300)
    shape: list[tuple[float, float]] | None = Field(None, max_length=20000)

    @model_validator(mode="after")
    def coherent(self):
        if self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("la fine deve essere dopo l'inizio")
        if self.kind == "stop_closed" and not self.stop_ids:
            raise ValueError("indicare almeno una fermata sospesa")
        if self.kind == "detour" and not self.route_ids:
            raise ValueError("indicare le linee deviate")
        if self.kind == "service_suspended" and not self.ends_at:
            raise ValueError("indicare fino a quando il servizio è sospeso")
        if self.kind != "detour":
            self.shape = None
        return self


class BikeSystemBody(BaseModel):
    system_id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    operator: str = Field("", max_length=120)
    app_url: str = Field("", max_length=300, pattern=URL_PATTERN)
    gbfs_url: str = Field("", max_length=500, pattern=URL_PATTERN)
    status_url: str = Field("", max_length=500, pattern=URL_PATTERN)
    license_url: str = Field("", max_length=300, pattern=URL_PATTERN)
    live: bool = True


class BikeStationBody(BaseModel):
    station_id: str = Field(pattern=BIKE_STATION_PATTERN)
    name: str = Field(min_length=1, max_length=150)
    short_name: str = Field("", max_length=40)
    address: str = Field("", max_length=200)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    capacity: int | None = Field(None, ge=0, le=10000)
    active: bool = True
    note: str = Field("", max_length=500)


class BikeImportUrlBody(BaseModel):
    url: str = Field(min_length=10, max_length=500, pattern=r"^https?://[^\s<>\"]+$")
    remove_missing: bool = False
    dry_run: bool = True


# ===================================================================== sessione
class SessionSigner:
    """Token di sessione firmato con HMAC: utente, scadenza, token CSRF, impronta della password.

    L'impronta cambia quando cambia la password: le sessioni aperte con quella vecchia non valgono più.
    """

    def __init__(self, secret: bytes, credential: str):
        self.secret = secret
        self.fingerprint = hmac.new(secret, credential.encode(), hashlib.sha256).hexdigest()[:16]

    def _sign(self, payload: bytes) -> str:
        return base64.urlsafe_b64encode(hmac.new(self.secret, payload, hashlib.sha256).digest()).decode().rstrip("=")

    def issue(self, username: str) -> tuple[str, dict]:
        data = {"u": username, "exp": int(time.time()) + SESSION_SECONDS, "csrf": secrets.token_urlsafe(24),
                "k": self.fingerprint}
        payload = base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")
        return f"{payload}.{self._sign(payload.encode())}", data

    def read(self, token: str | None) -> dict | None:
        if not token or "." not in token:
            return None
        payload, signature = token.rsplit(".", 1)
        if not hmac.compare_digest(signature, self._sign(payload.encode())):
            return None
        try:
            data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        except ValueError:
            return None
        if data.get("exp", 0) < time.time() or data.get("k") != self.fingerprint:
            return None
        return data


class LoginLimiter:
    """Al massimo MAX_FAILURES tentativi sbagliati per indirizzo in FAILURE_WINDOW secondi."""

    def __init__(self):
        self.failures: dict[str, list[float]] = {}
        self.lock = threading.Lock()

    def retry_after(self, address: str) -> int:
        now = time.time()
        with self.lock:
            recent = [t for t in self.failures.get(address, []) if now - t < FAILURE_WINDOW]
            self.failures[address] = recent
            return int(FAILURE_WINDOW - (now - recent[0])) + 1 if len(recent) >= MAX_FAILURES else 0

    def failed(self, address: str) -> None:
        with self.lock:
            self.failures.setdefault(address, []).append(time.time())
            if len(self.failures) > 10_000:
                self.failures.clear()

    def succeeded(self, address: str) -> None:
        with self.lock:
            self.failures.pop(address, None)


# ===================================================================== generazione del feed
class InvalidData(Exception):
    def __init__(self, errors: list[str], warnings: list[str]):
        super().__init__("; ".join(errors))
        self.errors, self.warnings = errors, warnings


@dataclass
class PreparedFeed:
    folder: Path
    summary: dict
    warnings: list[str]
    settings: dict


class FeedPublisher:
    """Dal database ai file GTFS pubblicati: prepara (dentro la transazione) e attiva (dopo il commit)."""

    def __init__(self, state, db: Database):
        self.state = state
        self.db = db
        self.data_dir: Path = state.env_config.data_dir
        self.lock = threading.Lock()
        self.generated_at: datetime | None = None
        self.last_warnings: list[str] = []

    def prepare(self, conn) -> PreparedFeed:
        src = self.db.load_sources(conn)
        errors, warnings = validate(src)
        if errors:
            raise InvalidData(errors, warnings)
        tz = ZoneInfo(src["percorsi"]["agency"].get("agency_timezone") or "Europe/Rome")
        now = self.state.clock.adesso()
        alerts = [Alert.from_json(row, tz) for row in self.db.list_alerts(conn, not_ended_at=now)]
        built = apply_suspensions(src, alerts, tz)
        # versione = istante + impronta del contenuto: le interfacce aperte capiscono che il feed è cambiato
        digest = hashlib.sha256(json.dumps([built, [a.json() for a in alerts]], sort_keys=True,
                                           default=str).encode()).hexdigest()[:6]
        built["percorsi"]["feed_info"]["feed_version"] = f"{datetime.now(tz):%Y%m%d-%H%M%S}-{digest}"
        folder = self.data_dir / "gtfs.next"
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
        try:
            write_sources(folder, src)
            summary = build_gtfs(folder, built)
            write_atomic(folder / ALERTS_FILE, json.dumps([a.json() for a in alerts], ensure_ascii=False, indent=1))
            Orario(folder, str(tz))   # il feed deve caricarsi prima di sostituire quello pubblicato
            AlertBoard.load(folder, tz)
            write_atomic(folder / BIKES_FILE, json.dumps(self.db.bike_public(conn), ensure_ascii=False, indent=1,
                                                         default=str))
            BikeBoard.load(folder)
        except InvalidSources as e:
            shutil.rmtree(folder, ignore_errors=True)
            raise InvalidData([str(e)], warnings) from None
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        return PreparedFeed(folder, summary, warnings, self.db.get_settings(conn))

    def activate(self, prepared: PreparedFeed) -> None:
        current = self.state.feed_dir
        previous = self.data_dir / "gtfs.prev"
        shutil.rmtree(previous, ignore_errors=True)
        if current.exists():
            current.rename(previous)
        prepared.folder.rename(current)
        shutil.rmtree(previous, ignore_errors=True)
        settings = {k: v for k, v in prepared.settings.items() if k != LOGO_KEY}
        settings.update(write_logo(self.data_dir, prepared.settings.get(LOGO_KEY)))
        write_atomic(self.data_dir / "settings.json", json.dumps(settings, ensure_ascii=False, indent=1))
        self.state.reload()
        self.generated_at = datetime.now().astimezone()
        self.last_warnings = prepared.warnings

    def run(self, change: Callable | None = None) -> tuple[object, PreparedFeed]:
        """Esegue `change(conn)` e rigenera il feed nella stessa transazione; attiva il feed dopo il commit."""
        with self.lock:
            with self.db.connect() as conn:
                conn.execute("SELECT pg_advisory_xact_lock(%s)", (FEED_LOCK,))
                result = change(conn) if change else None
                prepared = self.prepare(conn)
            self.activate(prepared)
            return result, prepared


# ===================================================================== logo
LOGO_KEY = "logo"
LOGO_MAX_BYTES = 512 * 1024
LOGO_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/svg+xml": "svg"}


def logo_type(content: bytes) -> str | None:
    """Tipo dell'immagine dai primi byte (non ci si fida dell'intestazione Content-Type)."""
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    head = content[:1000].lstrip().lower()
    if (head.startswith(b"<svg") or head.startswith(b"<?xml")) and b"<svg" in head:
        if re.search(rb"<script|javascript:|\son[a-z]+\s*=|<foreignobject", content, re.I):
            return None
        return "image/svg+xml"
    return None


def write_logo(data_dir: Path, stored: str | None) -> dict:
    """Scrive il logo salvato nel database in DATA_DIR e restituisce i riferimenti per settings.json."""
    for old in data_dir.glob("logo.*"):
        old.unlink()
    if not stored:
        return {}
    logo = json.loads(stored)
    content = base64.b64decode(logo["data"])
    name = f"logo.{LOGO_TYPES[logo['type']]}"
    (data_dir / name).write_bytes(content)
    return {"logo_file": name, "logo_version": hashlib.sha256(content).hexdigest()[:12]}


# ===================================================================== impostazioni
_RX_ALLOWED_TAG = re.compile(r'^<a href="https?://[^"<>\s]+"( target="_blank")?( rel="[a-z ]+")?>$|^</a>$')


def check_setting(key: str, value: str) -> str:
    value = value.strip()
    if key == "centro":
        try:
            lat, lon = (float(x) for x in value.split(","))
        except ValueError:
            raise ValueError("scrivere latitudine e longitudine separate da una virgola") from None
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("coordinate fuori intervallo")
        return f"{lat:.6f},{lon:.6f}"
    if key == "mappa_tiles":
        if not value.startswith(("https://", "http://")) or not all(t in value for t in ("{z}", "{x}", "{y}")):
            raise ValueError("serve un indirizzo http(s) con {z}, {x} e {y}")
    elif key in ("geocoder", "link_biglietti", "entity_url"):
        if value and not value.startswith(("https://", "http://")):
            raise ValueError("serve un indirizzo che inizi con https://")
    elif key == "mappa_attribuzione":
        for tag in re.findall(r"<[^>]*>", value):
            if not _RX_ALLOWED_TAG.match(tag):
                raise ValueError(f"marcatura non ammessa: {tag} (solo <a href=\"https://…\">)")
    elif "<" in value or ">" in value:
        raise ValueError("i caratteri < e > non sono ammessi")
    limit = 1000 if key == "biglietti" else 300
    if len(value) > limit:
        raise ValueError(f"al massimo {limit} caratteri")
    if key in ("comune", "servizio", "mappa_tiles", "app_title") and not value:
        raise ValueError("campo obbligatorio")
    return value


# ===================================================================== router
def create_admin_router(state) -> APIRouter:
    cfg = state.env_config
    db = Database(cfg.database_url)
    publisher = FeedPublisher(state, db)
    secret = cfg.admin_secret.encode() if cfg.admin_secret else secrets.token_bytes(32)
    if not cfg.admin_secret:
        log.warning("ADMIN_SECRET vuoto: chiave di sessione casuale, al riavvio bisogna rifare l'accesso")
    signer = SessionSigner(secret, cfg.admin_credential)

    def password_ok(password: str) -> bool:
        if cfg.admin_password_hash:
            return verify_password(password, cfg.admin_password_hash)
        return hmac.compare_digest(password.encode(), cfg.admin_password.encode())
    limiter = LoginLimiter()
    ready = {"ok": False, "error": ""}

    def ensure_ready() -> None:
        """Schema, primo popolamento e allineamento dei file al database (al primo uso o dopo un errore)."""
        if ready["ok"]:
            return
        try:
            db.migrate()
            with db.connect() as conn:
                if db.is_empty(conn):
                    from .sources import load_folder

                    db.seed(conn, load_folder(state.feed_dir))
                    db.audit(conn, "sistema", "popolamento iniziale", str(cfg.gtfs_dir))
                    log.info("database popolato dal feed %s", state.feed_dir)
            publisher.run()
            ready.update(ok=True, error="")
        except psycopg.OperationalError as e:
            ready["error"] = str(e).splitlines()[0]
            log.error("database non raggiungibile: %s", ready["error"])
            raise HTTPException(503, "Database non raggiungibile: la mappa pubblica funziona, il backoffice no. "
                                     "Riprovare tra poco.") from None
        except InvalidData as e:
            ready.update(ok=True, error="")  # i dati si correggono dal backoffice
            log.error("il feed nel database ha errori: %s", e.errors)

    try:
        ensure_ready()
    except HTTPException:
        pass  # si riprova alla prima richiesta

    router = APIRouter(prefix="/api/admin", tags=["backoffice"])

    # ------------------------------------------------------------------ autenticazione
    def current_user(request: Request) -> dict:
        data = signer.read(request.cookies.get(SESSION_COOKIE))
        if not data:
            raise HTTPException(401, "Accesso richiesto")
        return data

    def editor(request: Request, session: dict = Depends(current_user)) -> str:
        """Per le modifiche: sessione valida e token CSRF uguale a quello della sessione."""
        token = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(token, session["csrf"]):
            raise HTTPException(403, "Token di sicurezza mancante o scaduto: ricaricare la pagina")
        ensure_ready()
        return session["u"]

    def reader(session: dict = Depends(current_user)) -> str:
        ensure_ready()
        return session["u"]

    def secure_cookie(request: Request) -> bool:
        return request.url.scheme == "https" or state.config.base_url.startswith("https://")

    @router.post("/login")
    def login(body: LoginBody, request: Request, response: Response):
        address = request.client.host if request.client else "?"
        wait = limiter.retry_after(address)
        if wait:
            raise HTTPException(429, f"Troppi tentativi: riprovare tra {wait // 60 + 1} minuti",
                                headers={"Retry-After": str(wait)})
        # la password si verifica sempre, anche con l'utente sbagliato: stessa durata della risposta
        right_password = password_ok(body.password)
        right_user = hmac.compare_digest(body.username.strip().lower().encode(), cfg.admin_user.lower().encode())
        if not (right_password and right_user):
            limiter.failed(address)
            log.warning("accesso al backoffice non riuscito")
            raise HTTPException(401, "Utente o password non corretti")
        limiter.succeeded(address)
        token, data = signer.issue(cfg.admin_user)
        response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_SECONDS, path="/api/admin", httponly=True,
                            secure=secure_cookie(request), samesite="strict")
        try:
            with db.connect() as conn:
                db.audit(conn, cfg.admin_user, "accesso")
        except psycopg.Error:
            pass
        return {"username": data["u"], "csrf": data["csrf"], "expires": data["exp"]}

    @router.post("/logout")
    def logout(response: Response, session: dict = Depends(current_user)):
        response.delete_cookie(SESSION_COOKIE, path="/api/admin")
        return {"ok": True}

    @router.get("/session")
    def session_info(session: dict = Depends(current_user)):
        return {"username": session["u"], "csrf": session["csrf"], "expires": session["exp"]}

    # ------------------------------------------------------------------ modifiche
    def apply(username: str, action: str, target: str, change: Callable, details: dict | None = None):
        def run(conn):
            result = change(conn)
            db.audit(conn, username, action, target, details)
            return result

        try:
            result, prepared = publisher.run(run)
        except InvalidData as e:
            raise HTTPException(422, {"message": "Modifica non salvata: il feed avrebbe degli errori",
                                      "errors": e.errors, "warnings": e.warnings}) from None
        except KeyError as e:
            raise HTTPException(404, f"Elemento non trovato: {e.args[0]}") from None
        except psycopg.errors.UniqueViolation:
            raise HTTPException(409, "Esiste già un elemento con questo identificativo") from None
        except psycopg.errors.ForeignKeyViolation:
            raise HTTPException(409, "L'elemento è usato altrove (una linea o un calendario): modificare prima "
                                     "quelli") from None
        except psycopg.errors.CheckViolation as e:
            raise HTTPException(422, f"Valore non ammesso ({e.diag.constraint_name or 'vincolo'})") from None
        except psycopg.OperationalError:
            ready["ok"] = False
            raise HTTPException(503, "Database non raggiungibile: modifica non salvata") from None
        return {"ok": True, "result": result, "summary": prepared.summary, "warnings": prepared.warnings,
                "feed_version": state.timetable.info()["versione_feed"]}

    # ------------------------------------------------------------------ stato e dati
    @router.get("/status")
    def status(user: str = Depends(reader)):
        info = state.timetable.info()
        return {"feed": {"version": info["versione_feed"], "validity": info["validita"], "stops": info["fermate"],
                         "provisional_stops": info["fermate_provvisorie"], "routes": len(info["linee"]),
                         "trips": info["corse"], "agency": info["agenzia"]},
                "generated_at": publisher.generated_at, "warnings": publisher.last_warnings,
                "alerts_active": len(state.alerts.visible(state.clock.adesso())),
                "bikes": {"systems": len(state.bikes.systems), "stations": len(state.bikes.stations)},
                "osrm": bool(cfg.osrm_url), "database": ready["ok"]}

    @router.get("/data")
    def data(user: str = Depends(reader)):
        with db.connect() as conn:
            snap = db.snapshot(conn)
        fi = snap["feed_info"]
        for k in ("feed_start_date", "feed_end_date"):
            if fi.get(k):
                fi[k] = f"{fi[k][:4]}-{fi[k][4:6]}-{fi[k][6:]}"
        return snap

    # ------------------------------------------------------------------ fermate
    def stop_dict(body: StopBody) -> dict:
        d = body.model_dump()
        if d["lat"] is None:
            d["source"] = ""
        return d

    @router.post("/stops")
    def create_stop(body: StopBody, user: str = Depends(editor)):
        return apply(user, "nuova fermata", body.stop_id, lambda c: db.save_stop(c, None, stop_dict(body)),
                     body.model_dump())

    @router.put("/stops/{stop_id}")
    def update_stop(stop_id: str, body: StopBody, user: str = Depends(editor)):
        return apply(user, "modifica fermata", stop_id, lambda c: db.save_stop(c, stop_id, stop_dict(body)),
                     body.model_dump())

    @router.delete("/stops/{stop_id}")
    def delete_stop(stop_id: str, user: str = Depends(editor)):
        with db.connect() as conn:
            used = [r["variant_id"] for r in conn.execute(
                "SELECT DISTINCT variant_id FROM variant_stops WHERE stop_id=%s ORDER BY 1", (stop_id,))]
        if used:
            raise HTTPException(409, f"La fermata è nel percorso delle linee {', '.join(used)}: toglierla prima "
                                     "dai percorsi")
        return apply(user, "elimina fermata", stop_id, lambda c: db.delete_stop(c, stop_id))

    # ------------------------------------------------------------------ calendari
    def calendar_dict(body: CalendarBody) -> dict:
        return {**body.model_dump(), "exceptions": [e.model_dump() for e in body.exceptions]}

    @router.post("/calendars")
    def create_calendar(body: CalendarBody, user: str = Depends(editor)):
        return apply(user, "nuovo calendario", body.service_id,
                     lambda c: db.save_calendar(c, None, calendar_dict(body)), body.model_dump())

    @router.put("/calendars/{service_id}")
    def update_calendar(service_id: str, body: CalendarBody, user: str = Depends(editor)):
        return apply(user, "modifica calendario", service_id,
                     lambda c: db.save_calendar(c, service_id, calendar_dict(body)), body.model_dump())

    @router.delete("/calendars/{service_id}")
    def delete_calendar(service_id: str, user: str = Depends(editor)):
        return apply(user, "elimina calendario", service_id, lambda c: db.delete_calendar(c, service_id))

    # ------------------------------------------------------------------ linee (varianti)
    def variant_dict(body: VariantBody, keep_shape: bool) -> dict:
        d = body.model_dump()
        d["stops"] = [s.model_dump() for s in body.stops]
        if keep_shape:
            d.pop("shape", None)
        return d

    @router.post("/variants")
    def create_variant(body: VariantBody, user: str = Depends(editor)):
        return apply(user, "nuova linea", body.variant_id,
                     lambda c: db.save_variant(c, None, {**variant_dict(body, False), "shape": None}),
                     body.model_dump())

    @router.put("/variants/{variant_id}")
    def update_variant(variant_id: str, body: VariantBody, user: str = Depends(editor)):
        return apply(user, "modifica linea", variant_id,
                     lambda c: db.save_variant(c, variant_id, variant_dict(body, True)), body.model_dump())

    @router.delete("/variants/{variant_id}")
    def delete_variant(variant_id: str, user: str = Depends(editor)):
        return apply(user, "elimina linea", variant_id, lambda c: db.delete_variant(c, variant_id))

    @router.put("/variants/{variant_id}/shape")
    def update_shape(variant_id: str, body: ShapeBody, user: str = Depends(editor)):
        points = [list(p) for p in body.points] if body.points else None
        action = "modifica tracciato" if points else "elimina tracciato"
        return apply(user, action, variant_id, lambda c: db.set_shape(c, variant_id, points),
                     {"punti": len(points or [])})

    @router.post("/variants/{variant_id}/shape/osrm")
    def compute_shape(variant_id: str, user: str = Depends(editor)):
        if not cfg.osrm_url:
            raise HTTPException(400, "Calcolo dei tracciati disattivato (OSRM_URL vuoto)")
        with db.connect() as conn:
            rows = conn.execute("SELECT s.stop_id, s.lat, s.lon FROM variant_stops v JOIN stops s USING (stop_id) "
                                "WHERE v.variant_id=%s ORDER BY v.position", (variant_id,)).fetchall()
        if not rows:
            raise HTTPException(404, f"Linea {variant_id} non trovata")
        missing = [r["stop_id"] for r in rows if r["lat"] is None]
        if missing:
            raise HTTPException(422, f"Fermate senza coordinate: {', '.join(missing)}")
        try:
            points = osrm_route([(r["lat"], r["lon"]) for r in rows], cfg.osrm_url)
        except Exception as e:  # rete, servizio non disponibile, risposta non valida
            raise HTTPException(502, f"Calcolo del tracciato non riuscito: {e}") from None
        return apply(user, "calcola tracciato", variant_id, lambda c: db.set_shape(c, variant_id, points),
                     {"punti": len(points)})

    # ------------------------------------------------------------------ agenzia e validità
    @router.put("/feed")
    def update_feed(body: FeedBody, user: str = Depends(editor)):
        agency = body.agency.model_dump()
        fi = body.feed_info.model_dump()
        fi["feed_start_date"] = body.feed_info.feed_start_date.strftime("%Y%m%d")
        fi["feed_end_date"] = body.feed_info.feed_end_date.strftime("%Y%m%d")
        fi["feed_version"] = ""
        return apply(user, "modifica agenzia e validità", "feed", lambda c: db.save_feed_meta(c, agency, fi),
                     body.model_dump())

    # ------------------------------------------------------------------ avvisi
    def check_alert_targets(conn, body: AlertBody) -> None:
        routes = {r["route_id"] for r in conn.execute("SELECT DISTINCT route_id FROM route_variants")}
        stops = {r["stop_id"] for r in conn.execute("SELECT stop_id FROM stops")}
        unknown = [r for r in body.route_ids if r not in routes] + [s for s in body.stop_ids if s not in stops]
        if unknown:
            raise InvalidData([f"Linee o fermate inesistenti: {', '.join(unknown)}"], [])

    def alert_dict(body: AlertBody) -> dict:
        d = body.model_dump()
        d["shape"] = [list(p) for p in body.shape] if body.shape else None
        return d

    @router.get("/alerts")
    def list_alerts(include_past: bool = False, user: str = Depends(reader)):
        with db.connect() as conn:
            return db.list_alerts(conn, None if include_past else state.clock.adesso())

    @router.post("/alerts")
    def create_alert(body: AlertBody, user: str = Depends(editor)):
        def change(conn):
            check_alert_targets(conn, body)
            return db.save_alert(conn, None, alert_dict(body), user)
        return apply(user, "nuovo avviso", body.title, change, body.model_dump())

    @router.put("/alerts/{alert_id}")
    def update_alert(alert_id: int, body: AlertBody, user: str = Depends(editor)):
        def change(conn):
            check_alert_targets(conn, body)
            return db.save_alert(conn, alert_id, alert_dict(body), user)
        return apply(user, "modifica avviso", str(alert_id), change, body.model_dump())

    @router.delete("/alerts/{alert_id}")
    def delete_alert(alert_id: int, user: str = Depends(editor)):
        return apply(user, "elimina avviso", str(alert_id), lambda c: db.delete_alert(c, alert_id))

    # ------------------------------------------------------------------ bike sharing
    @router.get("/bikes")
    def list_bikes(user: str = Depends(reader)):
        """Sistemi e stazioni, ognuna con le fermate del bus vicine (dove bus e bici si incontrano)."""
        with db.connect() as conn:
            snap = db.bike_snapshot(conn)
            stops = conn.execute("SELECT stop_id, stop_code, stop_name, lat, lon FROM stops").fetchall()
        counts: dict[str, int] = {}
        for s in snap["stations"]:
            s["nearby_stops"] = nearby_stops(s["lat"], s["lon"], stops)
            counts[s["system_id"]] = counts.get(s["system_id"], 0) + 1
        for system in snap["systems"]:
            system["stations"] = counts.get(system["system_id"], 0)
        return snap

    @router.post("/bikes/systems")
    def create_bike_system(body: BikeSystemBody, user: str = Depends(editor)):
        return apply(user, "nuovo sistema bike sharing", body.system_id,
                     lambda c: db.save_bike_system(c, None, body.model_dump()), body.model_dump())

    @router.put("/bikes/systems/{system_id}")
    def update_bike_system(system_id: str, body: BikeSystemBody, user: str = Depends(editor)):
        return apply(user, "modifica sistema bike sharing", system_id,
                     lambda c: db.save_bike_system(c, system_id, body.model_dump()), body.model_dump())

    @router.delete("/bikes/systems/{system_id}")
    def delete_bike_system(system_id: str, user: str = Depends(editor)):
        return apply(user, "elimina sistema bike sharing", system_id, lambda c: db.delete_bike_system(c, system_id))

    def station_dict(body: BikeStationBody) -> dict:
        # salvata dall'ufficio: i prossimi import dal feed non la sovrascrivono
        return {**body.model_dump(), "source": "manuale"}

    @router.post("/bikes/systems/{system_id}/stations")
    def create_bike_station(system_id: str, body: BikeStationBody, user: str = Depends(editor)):
        return apply(user, "nuova stazione bike sharing", f"{system_id}/{body.station_id}",
                     lambda c: db.save_bike_station(c, system_id, None, station_dict(body)), body.model_dump())

    @router.put("/bikes/systems/{system_id}/stations/{station_id}")
    def update_bike_station(system_id: str, station_id: str, body: BikeStationBody, user: str = Depends(editor)):
        return apply(user, "modifica stazione bike sharing", f"{system_id}/{station_id}",
                     lambda c: db.save_bike_station(c, system_id, station_id, station_dict(body)), body.model_dump())

    @router.delete("/bikes/systems/{system_id}/stations/{station_id}")
    def delete_bike_station(system_id: str, station_id: str, user: str = Depends(editor)):
        return apply(user, "elimina stazione bike sharing", f"{system_id}/{station_id}",
                     lambda c: db.delete_bike_station(c, system_id, station_id))

    def import_gbfs(user: str, system_id: str, docs: dict, urls: dict, origin: str, remove_missing: bool,
                    dry_run: bool):
        """Anteprima (dry_run) o import delle stazioni di un feed GBFS in un sistema."""
        if "station_information" not in docs:
            raise HTTPException(422, "Manca station_information: è il file con l'elenco delle stazioni")
        try:
            incoming, warnings = parse_station_information(docs["station_information"])
            info = parse_system_information(docs["system_information"]) if "system_information" in docs else {}
            if "gbfs" in docs and "station_status" not in urls:
                urls = {**feed_urls(docs["gbfs"]), **urls}
        except GbfsError as e:
            raise HTTPException(422, f"Feed GBFS non valido: {e}") from None
        if not incoming:
            raise HTTPException(422, {"message": "Il feed non contiene stazioni valide", "errors": warnings,
                                      "warnings": []})
        if dry_run:
            with db.connect() as conn:
                try:
                    existing = db.bike_stations(conn, system_id)
                except KeyError:
                    raise HTTPException(404, f"Sistema {system_id} non trovato") from None
            return {"ok": True, "dry_run": True, "plan": plan_summary(plan_import(existing, incoming, remove_missing)),
                    "warnings": warnings, "system_information": info, "status_url": urls.get("station_status", "")}

        def change(conn):
            plan = plan_import(db.bike_stations(conn, system_id), incoming, remove_missing)
            db.apply_bike_import(conn, system_id, plan)
            summary = plan_summary(plan)
            current = conn.execute("SELECT * FROM bike_systems WHERE system_id=%s", (system_id,)).fetchone()
            updates: dict = {"last_import": {
                "at": datetime.now().astimezone().isoformat(timespec="seconds"), "by": user, "origin": origin,
                "stations": len(incoming), "added": len(summary["added"]), "updated": len(summary["updated"]),
                "removed": len(summary["removed"]), "kept_manual": len(summary["kept_manual"]),
                "missing": len(summary["missing"]), "warnings": warnings[:20]}}
            if origin.startswith("http"):   # l'indirizzo usato (gbfs.json o station_information) per i prossimi import
                updates["gbfs_url"] = origin
            if urls.get("station_status") and not current["status_url"]:
                updates["status_url"] = urls["station_status"]
            for key in ("operator", "app_url", "license_url"):   # dal gestore, se l'ufficio non li ha già scritti
                if info.get(key) and not current[key]:
                    updates[key] = info[key][:300]
            db.update_bike_system(conn, system_id, updates)
            return {**summary, "warnings": warnings}

        return apply(user, "import GBFS", system_id, change,
                     {"origine": origin, "stazioni": len(incoming), "rimuovi_mancanti": remove_missing})

    @router.post("/bikes/systems/{system_id}/import/url")
    def import_bikes_url(system_id: str, body: BikeImportUrlBody, user: str = Depends(editor)):
        try:
            docs, urls = fetch_feed(body.url)
        except GbfsError as e:
            raise HTTPException(502 if "download" in str(e) else 422, f"Feed GBFS non leggibile: {e}") from None
        return import_gbfs(user, system_id, docs, urls, body.url, body.remove_missing, body.dry_run)

    @router.post("/bikes/systems/{system_id}/import/file")
    async def import_bikes_file(system_id: str, request: Request, remove_missing: bool = False, dry_run: bool = True,
                                user: str = Depends(editor)):
        """File GBFS caricato: un JSON (station_information, ...) o uno zip con i file del feed."""
        content = await request.body()
        if not content:
            raise HTTPException(422, "File vuoto")
        try:
            docs = read_upload(content)
        except GbfsError as e:
            raise HTTPException(422, f"File GBFS non valido: {e}") from None
        return import_gbfs(user, system_id, docs, {}, "file caricato", remove_missing, dry_run)

    @router.get("/bikes/systems/{system_id}/live")
    def check_bike_status(system_id: str, user: str = Depends(reader)):
        """Prova a leggere ora la disponibilità dal gestore (station_status), senza cache."""
        with db.connect() as conn:
            try:
                stations = {s["station_id"] for s in db.bike_stations(conn, system_id)}
            except KeyError:
                raise HTTPException(404, f"Sistema {system_id} non trovato") from None
            system = conn.execute("SELECT status_url FROM bike_systems WHERE system_id=%s", (system_id,)).fetchone()
        if not system["status_url"]:
            raise HTTPException(400, "Indirizzo di station_status non impostato")
        try:
            doc = fetch_json(system["status_url"], http_client(timeout=8))
            status = parse_station_status(doc)
        except GbfsError as e:
            raise HTTPException(502, f"Disponibilità non leggibile: {e}") from None
        matched = [sid for sid in status if sid in stations]
        return {"ok": True, "ttl": ttl_of(doc), "stations_in_feed": len(status), "matched": len(matched),
                "unknown": sorted(set(status) - stations)[:20],
                "without_status": sorted(stations - set(status))[:20],
                "bikes": sum(status[s]["bikes"] or 0 for s in matched),
                "docks": sum(status[s]["docks"] or 0 for s in matched)}

    # ------------------------------------------------------------------ impostazioni
    @router.get("/settings")
    def get_settings(user: str = Depends(reader)):
        with db.connect() as conn:
            saved = db.get_settings(conn)
        env = cfg
        fields = []
        for key, (variable, label, help_text) in EDITABLE_SETTINGS.items():
            env_value = getattr(env, key)
            if key == "centro":
                env_value = ",".join(str(x) for x in env_value)
            fields.append({"key": key, "variable": variable, "label": label, "help": help_text,
                           "value": saved.get(key, env_value), "env_value": env_value, "custom": key in saved})
        read_only = [
            {"variable": "BASE_URL", "value": cfg.base_url},
            {"variable": "GTFS_DIR", "value": str(cfg.gtfs_dir)},
            {"variable": "DATA_DIR", "value": str(cfg.data_dir)},
            {"variable": "ADMIN_USER", "value": cfg.admin_user},
            {"variable": "INFERENCE_URL", "value": cfg.inference_url or "(non configurato)"},
            {"variable": "OSRM_URL", "value": cfg.osrm_url or "(disattivato)"},
            {"variable": "DEMO_ORA", "value": cfg.demo_ora or "(ora reale)"},
        ]
        return {"fields": fields, "read_only": read_only, "logo": state.logo_url()}

    @router.put("/settings")
    def update_settings(values: dict[str, str | None] = Body(...), user: str = Depends(editor)):
        clean: dict[str, str | None] = {}
        problems = []
        for key, value in values.items():
            if key not in EDITABLE_SETTINGS:
                problems.append(f"{key}: impostazione sconosciuta o modificabile solo nel .env")
                continue
            if value is None:
                clean[key] = None
                continue
            try:
                clean[key] = check_setting(key, str(value))
            except ValueError as e:
                problems.append(f"{EDITABLE_SETTINGS[key][1]}: {e}")
        if problems:
            raise HTTPException(422, {"message": "Impostazioni non salvate", "errors": problems, "warnings": []})
        return apply(user, "modifica impostazioni", ", ".join(clean), lambda c: db.save_settings(c, clean), clean)

    @router.put("/logo")
    async def upload_logo(request: Request, user: str = Depends(editor)):
        """Logo dell'ente (PNG, JPEG, WebP o SVG senza script), al massimo 512 kB: corpo della richiesta = file."""
        content = await request.body()
        if not content or len(content) > LOGO_MAX_BYTES:
            raise HTTPException(413 if content else 422, "Il logo deve essere un'immagine di al massimo 512 kB")
        kind = logo_type(content)
        if not kind:
            raise HTTPException(415, "Formato non ammesso: PNG, JPEG, WebP o SVG senza script")
        stored = json.dumps({"type": kind, "data": base64.b64encode(content).decode()})
        return apply(user, "nuovo logo", kind, lambda c: db.save_settings(c, {LOGO_KEY: stored}),
                     {"tipo": kind, "byte": len(content)})

    @router.delete("/logo")
    def delete_logo(user: str = Depends(editor)):
        return apply(user, "elimina logo", "", lambda c: db.save_settings(c, {LOGO_KEY: None}))

    # ------------------------------------------------------------------ registro ed export
    @router.get("/audit")
    def audit(limit: int = Query(200, ge=1, le=2000), user: str = Depends(reader)):
        with db.connect() as conn:
            return db.list_audit(conn, limit)

    @router.get("/export.zip")
    def export_zip(sources: bool = False, user: str = Depends(reader)):
        """Il feed GTFS pubblicato (sempre allineato al database), con le sorgenti se richiesto."""
        folder = state.feed_dir
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(folder.glob("*.txt")):
                z.write(f, f.name)
            if sources:
                for name in ("fermate.csv", "percorsi.json", "forme.json", ALERTS_FILE, BIKES_FILE):
                    if (folder / name).exists():
                        z.write(folder / name, f"sorgenti/{name}")
        version = state.timetable.info()["versione_feed"] or "feed"
        return Response(buf.getvalue(), media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="gtfs-{version}.zip"'})

    return router
