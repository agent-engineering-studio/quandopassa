"""QuandoPassa – API e interfaccia web del bus urbano.

    uvicorn --factory quandopassa.main:create_app --reload

API pubbliche (JSON, /api/v1):
  GET  /health                         stato di app, feed e IA
  GET  /info                           servizio, linee, versione del feed, avvisi
  GET  /ora                            orologio del servizio (per sincronizzare l'interfaccia)
  GET  /fermate                        tutte le fermate con le linee che le servono
  GET  /fermate/vicine?lat&lon&n       fermate più vicine con distanza e minuti a piedi
  GET  /fermate/cerca?q                ricerca per nome
  GET  /fermate/{id}                   dettaglio + prossime partenze
  GET  /fermate/{id}/partenze?n&ora    prossimi passaggi
  GET  /linee                          linee con tracciati e fermate
  GET  /orario?giorno                  corse e tracciati del giorno (l'interfaccia anima i bus da sola)
  GET  /veicoli?ora                    bus in servizio con posizione stimata dall'orario
  GET  /percorso?lat&lon&a             come arrivo: a piedi + bus diretto verso una fermata
  GET  /itinerari?da_lat&da_lon&a_lat&a_lon   come arrivo porta a porta: a piedi, bus, cambi
  GET  /luoghi?q                       fermate, indirizzi e luoghi per scegliere partenza e arrivo
  GET  /assistente?testo&lat&lon       assistente IA
  GET  /alerts?ora                     avvisi di servizio: deviazioni, fermate sospese, servizio sospeso

Backoffice (/admin, API /api/admin): attivo con DATI_DIR, ADMIN_UTENTE e ADMIN_PASSWORD_HASH, vedi backoffice.py.
"""

import dataclasses
import json
import logging
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .ai import ClientIA
from .assistente import ESEMPI, Assistente, AssistenteNonDisponibile
from .alerts import AlertBoard
from .config import EDITABLE_SETTINGS, Config
from .gtfs import Orario
from .itinerari import Pianificatore
from .luoghi import Luoghi

log = logging.getLogger("quandopassa")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


class SenzaDatiPersonali(logging.Filter):
    """Nei log di accesso niente posizione né testo delle domande: restano percorso, esito e orario (GDPR art. 5.1.c)."""

    _rx = re.compile(r"\b(\w*lat|\w*lon|testo|q|da_nome|a_nome)=[^&\s\"]*")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(self._rx.sub(r"\1=***", a) if isinstance(a, str) else a for a in record.args)
        return True


logging.getLogger("uvicorn.access").addFilter(SenzaDatiPersonali())


class Orologio:
    """Ora del servizio. Con DEMO_ORA parte da un istante fisso e poi scorre normalmente."""

    def __init__(self, fuso, demo: str = ""):
        self.fuso = fuso
        self.scarto = timedelta(0)
        if demo:
            inizio = datetime.fromisoformat(demo)
            inizio = inizio if inizio.tzinfo else inizio.replace(tzinfo=fuso)
            self.scarto = inizio - datetime.now(fuso)

    def adesso(self) -> datetime:
        return datetime.now(self.fuso) + self.scarto


def feed_folder(cfg: Config) -> Path:
    """Feed in uso: GTFS_DIR, oppure DATA_DIR/gtfs (generato dal backoffice) copiato da GTFS_DIR al primo avvio."""
    if not cfg.data_dir:
        return cfg.gtfs_dir
    target = cfg.data_dir / "gtfs"
    if not (target / "stops.txt").exists():
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = cfg.data_dir / "gtfs.initial"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir()
        for f in cfg.gtfs_dir.iterdir():
            if f.is_file() and not f.name.startswith("."):
                shutil.copy2(f, tmp / f.name)
        shutil.rmtree(target, ignore_errors=True)
        tmp.rename(target)
        log.info("DATA_DIR: feed iniziale copiato da %s in %s", cfg.gtfs_dir, target)
    return target


def apply_settings(cfg: Config, values: dict) -> Config:
    """Config del .env con le impostazioni salvate dal backoffice (DATA_DIR/settings.json)."""
    changes = {}
    for key, value in values.items():
        if key not in EDITABLE_SETTINGS or value is None:
            continue
        if key == "centro":
            value = tuple(float(x) for x in str(value).split(","))
        changes[key] = value
    return dataclasses.replace(cfg, **changes)


class AppState:
    """Stato dell'app ricaricabile senza riavvio: feed, avvisi, impostazioni e componenti che ne dipendono."""

    def __init__(self, cfg: Config, ia: ClientIA):
        self.env_config = cfg
        self.ia = ia
        self.feed_dir = feed_folder(cfg)
        self.reload()
        self.clock = Orologio(self.timetable.fuso, cfg.demo_ora)

    @property
    def settings_file(self) -> Path | None:
        return self.env_config.data_dir / "settings.json" if self.env_config.data_dir else None

    def saved_settings(self) -> dict:
        path = self.settings_file
        if path and path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                log.exception("settings.json non leggibile: uso il .env")
        return {}

    def logo_url(self) -> str | None:
        """Indirizzo del logo caricato dal backoffice (con la versione, per la cache del browser)."""
        saved = self.saved_settings()
        if saved.get("logo_file") and self.env_config.data_dir and (self.env_config.data_dir / saved["logo_file"]).exists():
            return f"/api/v1/logo?v={saved.get('logo_version', '')}"
        return None

    def logo_file(self) -> Path | None:
        name = self.saved_settings().get("logo_file")
        if not name or not self.env_config.data_dir:
            return None
        path = self.env_config.data_dir / Path(name).name
        return path if path.exists() else None

    def reload(self) -> None:
        config = apply_settings(self.env_config, self.saved_settings())
        timetable = Orario(self.feed_dir, config.fuso)
        alerts = AlertBoard.load(self.feed_dir, timetable.fuso)
        # tutto pronto prima di sostituire: le richieste in corso vedono il vecchio o il nuovo, mai un misto
        planner = Pianificatore(timetable, closed_stops=lambda when, board=alerts: board.closed_stops(when))
        places = Luoghi(timetable, config.geocoder, config.comune.removeprefix("Comune di ").strip())
        assistant = Assistente(config, timetable, self.ia)
        self.config, self.timetable, self.alerts, self.planner, self.places, self.assistant = (
            config, timetable, alerts, planner, places, assistant)
        log.info("feed %s: %s fermate (%s provvisorie), %s corse, %s avvisi", self.feed_dir, len(timetable.fermate),
                 timetable.info()["fermate_provvisorie"], len(timetable.corse), len(alerts.alerts))


def create_app(cfg: Config | None = None, ia: ClientIA | None = None) -> FastAPI:
    cfg = cfg or Config()
    ia = ia or ClientIA(cfg.inference_url)
    s = AppState(cfg, ia)

    app = FastAPI(title="QuandoPassa", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.app_state = s

    def istante(ora: str | None) -> datetime:
        if not ora:
            return s.clock.adesso()
        try:
            d = datetime.fromisoformat(ora)
        except ValueError:
            raise HTTPException(422, "ora: usare ISO 8601, es. 2026-11-10T09:05") from None
        return d if d.tzinfo else d.replace(tzinfo=s.timetable.fuso)

    def mark_suspended(stop_id: str, departures: list[dict]) -> list[dict]:
        """Partenze da una fermata sospesa (avviso o deviazione): restano in elenco, segnate come sospese."""
        for d in departures:
            when = datetime.fromisoformat(d["orario"])
            closure = s.alerts.closure(stop_id, when, d["linea_id"])
            if closure:
                d["suspended"] = True
                d["alert_id"] = closure.id
        return departures

    def stop_alerts(stop_id: str, when: datetime) -> list[dict]:
        routes = set(s.timetable.linee_della_fermata(stop_id))
        return [a.json(when) for a in s.alerts.visible(when, route_ids=routes, stop_id=stop_id)]

    def fermata_o_404(fid: str):
        f = s.timetable.fermate.get(fid)
        if f is None:
            raise HTTPException(404, f"Fermata {fid} non trovata")
        return f

    # ---------------------------------------------------------- servizio
    @app.get("/api/v1/health")
    def health():
        stato_ia = ia.stato()
        return {"stato": "ok", "feed": s.timetable.info()["versione_feed"],
                "ia": stato_ia or ("non configurata" if not ia.attivo else "non raggiungibile")}

    @app.get("/api/v1/info")
    def info():
        ora = s.clock.adesso()
        ia_attiva = ia.stato() is not None
        return {**s.timetable.info(), "comune": s.config.comune, "servizio": s.config.servizio, "centro": list(s.config.centro),
                "mappa": {"tiles": s.config.mappa_tiles, "attribuzione": s.config.mappa_attribuzione},
                "ora": ora.isoformat(timespec="seconds"), "prossima_corsa": s.timetable.prossima_corsa(ora),
                "assistente": ia_attiva, "esempi_assistente": ESEMPI,
                "biglietti": {"url": s.config.link_biglietti or None, "nome": s.config.biglietteria_nome or None,
                              "info": s.config.biglietti},
                "avvisi": _avvisi(s.timetable),
                "alerts": [a.json(ora) for a in s.alerts.visible(ora)],
                "header": {"title": s.config.app_title, "subtitle": s.config.servizio, "entity_name": s.config.comune,
                           "entity_url": s.config.entity_url or s.timetable.agenzia.get("agency_url", ""),
                           "logo_url": s.logo_url(), "logo_alt": s.config.logo_alt}}

    @app.get("/api/v1/logo", include_in_schema=False)
    def logo():
        path = s.logo_file()
        if path is None:
            raise HTTPException(404, "Nessun logo")
        media = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp", ".svg": "image/svg+xml"}
        return FileResponse(path, media_type=media.get(path.suffix, "application/octet-stream"), headers={
            "Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox"})

    @app.get("/api/v1/alerts")
    def alerts(ora: str | None = None):
        """Avvisi di servizio in corso e della prossima settimana: deviazioni, fermate sospese, servizio sospeso."""
        t = istante(ora)
        return [a.json(t) for a in s.alerts.visible(t)]

    @app.get("/api/v1/ora")
    def ora_servizio():
        return {"ora": s.clock.adesso().isoformat(timespec="milliseconds"), "fuso": str(s.timetable.fuso),
                "demo": bool(s.config.demo_ora)}

    # ---------------------------------------------------------- fermate
    @app.get("/api/v1/fermate")
    def fermate():
        closed = s.alerts.closed_stops(s.clock.adesso())
        return [{**f.json(), "linee": s.timetable.linee_della_fermata(f.id), "closed": f.id in closed}
                for f in sorted(s.timetable.fermate.values(), key=lambda f: f.codice)]

    @app.get("/api/v1/fermate/vicine")
    def vicine(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180),
               n: int = Query(5, ge=1, le=20), ora: str | None = None):
        t = istante(ora)
        out = s.timetable.vicine(lat, lon, n)
        for f in out:
            f["partenze"] = mark_suspended(f["id"], s.timetable.partenze(f["id"], t, n=2))
        return out

    @app.get("/api/v1/fermate/cerca")
    def cerca(q: str = Query(..., min_length=2, max_length=100), n: int = Query(5, ge=1, le=20)):
        return s.timetable.cerca(q, n)

    @app.get("/api/v1/fermate/{fid}")
    def fermata(fid: str, ora: str | None = None):
        f = fermata_o_404(fid)
        t = istante(ora)
        return {**f.json(), "linee": s.timetable.linee_della_fermata(fid),
                "partenze": mark_suspended(fid, s.timetable.partenze(fid, t, n=6)), "alerts": stop_alerts(fid, t)}

    @app.get("/api/v1/fermate/{fid}/partenze")
    def partenze(fid: str, n: int = Query(5, ge=1, le=30), ora: str | None = None):
        fermata_o_404(fid)
        return mark_suspended(fid, s.timetable.partenze(fid, istante(ora), n=n))

    # ---------------------------------------------------------- linee e bus
    @app.get("/api/v1/linee")
    def linee():
        out = []
        for l in s.timetable.linee.values():
            tracciati = [t.json() for t in s.timetable.tracciati.values() if t.linea_id == l.id]
            fermate_linea = list(dict.fromkeys(s for t in tracciati for s in t["fermate"]))
            out.append({**l.json(), "tracciati": tracciati, "fermate": fermate_linea})
        return out

    @app.get("/api/v1/orario")
    def orario_giorno(giorno: date | None = None):
        return s.timetable.orario_del_giorno(giorno or s.clock.adesso().date())

    @app.get("/api/v1/veicoli")
    def veicoli(ora: str | None = None, linea: str | None = None):
        t = istante(ora)
        v = s.timetable.veicoli(t)
        if linea:
            v = [x for x in v if x["linea_id"].upper() == linea.upper()]
        return {"ora": t.isoformat(timespec="seconds"), "veicoli": v,
                "prossima_corsa": None if v else s.timetable.prossima_corsa(t), "tempo_reale": False}

    @app.get("/api/v1/percorso")
    def percorso(lat: float, lon: float, a: str = Query(..., min_length=1, max_length=100), ora: str | None = None):
        if a in s.timetable.fermate:
            dest = [s.timetable.fermate[a].json()]
        else:
            dest = s.timetable.cerca(a, n=2)
        if not dest:
            raise HTTPException(404, f"Nessuna fermata corrisponde a \"{a}\"")
        return {"destinazione": dest[0], "opzioni": s.timetable.percorso(lat, lon, [d["id"] for d in dest], istante(ora))}

    # ---------------------------------------------------------- come arrivo
    @app.get("/api/v1/itinerari")
    def itinerari(da_lat: float = Query(..., ge=-90, le=90), da_lon: float = Query(..., ge=-180, le=180),
                  a_lat: float = Query(..., ge=-90, le=90), a_lon: float = Query(..., ge=-180, le=180),
                  da_nome: str = Query("Partenza", max_length=120), a_nome: str = Query("Destinazione", max_length=120),
                  ora: str | None = None, n: int = Query(3, ge=1, le=6)):
        return s.planner.pianifica((da_lat, da_lon), (a_lat, a_lon), istante(ora), opzioni=n,
                                       nome_origine=da_nome, nome_destinazione=a_nome)

    @app.get("/api/v1/luoghi")
    def cerca_luoghi(q: str = Query(..., min_length=2, max_length=100)):
        return s.places.cerca(q)

    # ---------------------------------------------------------- assistente
    @app.get("/api/v1/assistente")
    def chiedi(testo: str = Query(..., min_length=2, max_length=500), lat: float | None = None,
               lon: float | None = None, ora: str | None = None):
        try:
            return s.assistant.rispondi(testo, istante(ora), lat, lon)
        except AssistenteNonDisponibile:
            raise HTTPException(503, "Assistente non disponibile: mappa e orari funzionano comunque") from None

    # ---------------------------------------------------------- backoffice
    if cfg.admin_enabled:
        from .admin import create_admin_router

        app.include_router(create_admin_router(s))
    else:
        log.error("Backoffice non attivo: %s (lanciare make env)", cfg.admin_problem)

    @app.middleware("http")
    async def admin_headers(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/api/admin"):
            response.headers["Cache-Control"] = "no-store"
        elif path == "/admin" or path.startswith("/admin/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; "
                "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        return response

    @app.api_route("/api/admin/{rest:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
    def admin_disabled(rest: str):
        raise HTTPException(404, f"Backoffice non attivo: {cfg.admin_problem}")

    # ---------------------------------------------------------- interfaccia React (pubblica e /admin)
    dist = cfg.web_dist
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{percorso:path}", include_in_schema=False)
        def spa(percorso: str):
            if percorso.startswith("api/"):
                raise HTTPException(404)
            f = (dist / percorso).resolve()
            if percorso and f.is_file() and dist.resolve() in f.parents:
                return FileResponse(f)
            if (percorso == "admin" or percorso.startswith("admin/")) and (dist / "admin" / "index.html").exists():
                return FileResponse(dist / "admin" / "index.html")
            return FileResponse(dist / "index.html")

    return app


def _avvisi(orario: Orario) -> list[str]:
    avvisi = ["Posizioni dei bus stimate dall'orario programmato: non c'è un GPS a bordo."]
    n = orario.info()["fermate_provvisorie"]
    if n:
        avvisi.append(f"{n} fermate hanno una posizione provvisoria sulla mappa, in attesa del geocoding.")
    return avvisi
