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
"""

import logging
import re
from datetime import date, datetime, timedelta

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .ai import ClientIA
from .assistente import ESEMPI, Assistente, AssistenteNonDisponibile
from .config import Config
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


def create_app(cfg: Config | None = None, ia: ClientIA | None = None) -> FastAPI:
    cfg = cfg or Config()
    orario = Orario(cfg.gtfs_dir, cfg.fuso)
    ia = ia or ClientIA(cfg.inference_url)
    orologio = Orologio(orario.fuso, cfg.demo_ora)
    pianificatore = Pianificatore(orario)
    luoghi = Luoghi(orario, cfg.geocoder, cfg.comune.removeprefix("Comune di ").strip())
    assistente = Assistente(cfg, orario, ia)
    log.info("feed %s: %s fermate (%s provvisorie), %s corse", cfg.gtfs_dir, len(orario.fermate),
             orario.info()["fermate_provvisorie"], len(orario.corse))

    app = FastAPI(title="QuandoPassa", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.orario, app.state.orologio = orario, orologio

    def istante(ora: str | None) -> datetime:
        if not ora:
            return orologio.adesso()
        try:
            d = datetime.fromisoformat(ora)
        except ValueError:
            raise HTTPException(422, "ora: usare ISO 8601, es. 2026-11-10T09:05") from None
        return d if d.tzinfo else d.replace(tzinfo=orario.fuso)

    def fermata_o_404(fid: str):
        f = orario.fermate.get(fid)
        if f is None:
            raise HTTPException(404, f"Fermata {fid} non trovata")
        return f

    # ---------------------------------------------------------- servizio
    @app.get("/api/v1/health")
    def health():
        stato_ia = ia.stato()
        return {"stato": "ok", "feed": orario.info()["versione_feed"],
                "ia": stato_ia or ("non configurata" if not ia.attivo else "non raggiungibile")}

    @app.get("/api/v1/info")
    def info():
        ora = orologio.adesso()
        ia_attiva = ia.stato() is not None
        return {**orario.info(), "comune": cfg.comune, "servizio": cfg.servizio, "centro": list(cfg.centro),
                "mappa": {"tiles": cfg.mappa_tiles, "attribuzione": cfg.mappa_attribuzione},
                "ora": ora.isoformat(timespec="seconds"), "prossima_corsa": orario.prossima_corsa(ora),
                "assistente": ia_attiva, "esempi_assistente": ESEMPI,
                "avvisi": _avvisi(orario)}

    @app.get("/api/v1/ora")
    def ora_servizio():
        return {"ora": orologio.adesso().isoformat(timespec="milliseconds"), "fuso": str(orario.fuso),
                "demo": bool(cfg.demo_ora)}

    # ---------------------------------------------------------- fermate
    @app.get("/api/v1/fermate")
    def fermate():
        return [{**f.json(), "linee": orario.linee_della_fermata(f.id)}
                for f in sorted(orario.fermate.values(), key=lambda f: f.codice)]

    @app.get("/api/v1/fermate/vicine")
    def vicine(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180),
               n: int = Query(5, ge=1, le=20), ora: str | None = None):
        t = istante(ora)
        out = orario.vicine(lat, lon, n)
        for f in out:
            f["partenze"] = orario.partenze(f["id"], t, n=2)
        return out

    @app.get("/api/v1/fermate/cerca")
    def cerca(q: str = Query(..., min_length=2, max_length=100), n: int = Query(5, ge=1, le=20)):
        return orario.cerca(q, n)

    @app.get("/api/v1/fermate/{fid}")
    def fermata(fid: str, ora: str | None = None):
        f = fermata_o_404(fid)
        return {**f.json(), "linee": orario.linee_della_fermata(fid),
                "partenze": orario.partenze(fid, istante(ora), n=6)}

    @app.get("/api/v1/fermate/{fid}/partenze")
    def partenze(fid: str, n: int = Query(5, ge=1, le=30), ora: str | None = None):
        fermata_o_404(fid)
        return orario.partenze(fid, istante(ora), n=n)

    # ---------------------------------------------------------- linee e bus
    @app.get("/api/v1/linee")
    def linee():
        out = []
        for l in orario.linee.values():
            tracciati = [t.json() for t in orario.tracciati.values() if t.linea_id == l.id]
            fermate_linea = list(dict.fromkeys(s for t in tracciati for s in t["fermate"]))
            out.append({**l.json(), "tracciati": tracciati, "fermate": fermate_linea})
        return out

    @app.get("/api/v1/orario")
    def orario_giorno(giorno: date | None = None):
        return orario.orario_del_giorno(giorno or orologio.adesso().date())

    @app.get("/api/v1/veicoli")
    def veicoli(ora: str | None = None, linea: str | None = None):
        t = istante(ora)
        v = orario.veicoli(t)
        if linea:
            v = [x for x in v if x["linea_id"].upper() == linea.upper()]
        return {"ora": t.isoformat(timespec="seconds"), "veicoli": v,
                "prossima_corsa": None if v else orario.prossima_corsa(t), "tempo_reale": False}

    @app.get("/api/v1/percorso")
    def percorso(lat: float, lon: float, a: str = Query(..., min_length=1, max_length=100), ora: str | None = None):
        if a in orario.fermate:
            dest = [orario.fermate[a].json()]
        else:
            dest = orario.cerca(a, n=2)
        if not dest:
            raise HTTPException(404, f"Nessuna fermata corrisponde a \"{a}\"")
        return {"destinazione": dest[0], "opzioni": orario.percorso(lat, lon, [d["id"] for d in dest], istante(ora))}

    # ---------------------------------------------------------- come arrivo
    @app.get("/api/v1/itinerari")
    def itinerari(da_lat: float = Query(..., ge=-90, le=90), da_lon: float = Query(..., ge=-180, le=180),
                  a_lat: float = Query(..., ge=-90, le=90), a_lon: float = Query(..., ge=-180, le=180),
                  da_nome: str = Query("Partenza", max_length=120), a_nome: str = Query("Destinazione", max_length=120),
                  ora: str | None = None, n: int = Query(3, ge=1, le=6)):
        return pianificatore.pianifica((da_lat, da_lon), (a_lat, a_lon), istante(ora), opzioni=n,
                                       nome_origine=da_nome, nome_destinazione=a_nome)

    @app.get("/api/v1/luoghi")
    def cerca_luoghi(q: str = Query(..., min_length=2, max_length=100)):
        return luoghi.cerca(q)

    # ---------------------------------------------------------- assistente
    @app.get("/api/v1/assistente")
    def chiedi(testo: str = Query(..., min_length=2, max_length=500), lat: float | None = None,
               lon: float | None = None, ora: str | None = None):
        try:
            return assistente.rispondi(testo, istante(ora), lat, lon)
        except AssistenteNonDisponibile:
            raise HTTPException(503, "Assistente non disponibile: mappa e orari funzionano comunque") from None

    # ---------------------------------------------------------- interfaccia React
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
            return FileResponse(dist / "index.html")

    return app


def _avvisi(orario: Orario) -> list[str]:
    avvisi = ["Posizioni dei bus stimate dall'orario programmato: non c'è un GPS a bordo."]
    n = orario.info()["fermate_provvisorie"]
    if n:
        avvisi.append(f"{n} fermate hanno una posizione provvisoria sulla mappa, in attesa del geocoding.")
    return avvisi
