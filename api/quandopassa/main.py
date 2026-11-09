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
Biglietti (prototipo, tariffe nel .env; acquisto anonimo con chiave sul dispositivo):
  GET  /biglietti                      tariffe e modalità di pagamento
  POST /biglietti/acquisti             nuovo acquisto {tipo} -> chiave, importo, riferimento di pagamento
  POST /biglietti/acquisti/{id}/pagamento-simulato   esito del pagamento simulato
  POST /biglietti/acquisti/{id}/conferma            emette il titolo a pagamento riuscito
  POST /biglietti/portafoglio          titoli delle chiavi salvate sul dispositivo
  POST /biglietti/titoli/{id}/attiva   attiva una corsa: codice e QR firmato
  POST /biglietti/verifica             controllore (HTTP Basic, VERIFICA_USER/VERIFICA_PASSWORD)
"""

import base64
import logging
import re
import secrets
from datetime import date, datetime, timedelta
from typing import Annotated

import qrcode
import qrcode.image.svg
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .ai import ClientIA
from .assistente import ESEMPI, Assistente, AssistenteNonDisponibile
from .config import Config
from .biglietti import Biglietteria, ErroreBiglietto
from .gtfs import Orario
from .pagamenti import crea_pagamenti
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


class AcquistoIn(BaseModel):
    tipo: str = Field(..., pattern="^(corsa|carnet|abbonamento)$")


class ChiaveIn(BaseModel):
    chiave: str = Field(..., min_length=16, max_length=64)


class EsitoSimulatoIn(ChiaveIn):
    pagato: bool


class PortafoglioIn(BaseModel):
    chiavi: list[str] = Field(default_factory=list, max_length=50)


class VerificaIn(BaseModel):
    codice: str = Field(..., min_length=4, max_length=200)


def qr_immagine(dati: str) -> str:
    """QR come immagine SVG in data URI: il browser lo mostra in un <img>, che non esegue codice."""
    img = qrcode.make(dati, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    return "data:image/svg+xml;base64," + base64.b64encode(img.to_string()).decode()


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
    biglietteria = Biglietteria(cfg, crea_pagamenti(cfg.pagamenti), orologio.adesso) if cfg.biglietti_attivi else None
    basic = HTTPBasic(auto_error=False)
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

    @app.exception_handler(ErroreBiglietto)
    async def _errore_biglietto(_: Request, e: ErroreBiglietto):
        return JSONResponse({"errore": str(e)}, status_code=e.status)

    def cassa() -> Biglietteria:
        if biglietteria is None:
            raise HTTPException(404, "Vendita dei biglietti non attiva (BIGLIETTI_ATTIVI)")
        return biglietteria

    def controllore(cred: Annotated[HTTPBasicCredentials | None, Depends(basic)]) -> str:
        if not (cfg.verifica_user and cfg.verifica_password):
            raise HTTPException(503, "Verifica non configurata (VERIFICA_USER/VERIFICA_PASSWORD)")
        ok = cred is not None and secrets.compare_digest(cred.username, cfg.verifica_user) \
            and secrets.compare_digest(cred.password, cfg.verifica_password)
        if not ok:
            raise HTTPException(401, "Credenziali non valide")
        return cred.username

    def con_qr(titolo: dict) -> dict:
        if titolo.get("attivazione"):
            titolo["attivazione"]["qr_img"] = qr_immagine(titolo["attivazione"]["qr"])
        return titolo

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
                "assistente": ia_attiva, "esempi_assistente": ESEMPI, "biglietti": info_biglietti(),
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

    # ---------------------------------------------------------- biglietti
    def info_biglietti() -> dict:
        if biglietteria is None:
            return {"attivi": False}
        return {"attivi": True, "tariffe": [t.json() for t in biglietteria.tariffe.values()],
                "pagamenti": biglietteria.pagamenti.nome, "fonte": cfg.fonte_tariffe}

    @app.get("/api/v1/biglietti")
    def biglietti():
        return info_biglietti()

    @app.post("/api/v1/biglietti/acquisti", status_code=201)
    def acquista(body: AcquistoIn):
        return cassa().acquista(body.tipo)

    @app.post("/api/v1/biglietti/acquisti/{aid}/pagamento-simulato")
    def pagamento_simulato(aid: str, body: EsitoSimulatoIn):
        cassa().esito_simulato(aid, body.chiave, body.pagato)
        return {"acquisto_id": aid, "pagato": body.pagato}

    @app.post("/api/v1/biglietti/acquisti/{aid}/conferma")
    def conferma(aid: str, body: ChiaveIn):
        return con_qr(cassa().conferma(aid, body.chiave))

    @app.post("/api/v1/biglietti/portafoglio")
    def portafoglio(body: PortafoglioIn):
        return [con_qr(t) for t in cassa().portafoglio(body.chiavi)]

    @app.post("/api/v1/biglietti/titoli/{tid}/attiva")
    def attiva(tid: str, body: ChiaveIn):
        return con_qr(cassa().attiva(tid, body.chiave))

    @app.post("/api/v1/biglietti/verifica")
    def verifica(body: VerificaIn, _: Annotated[str, Depends(controllore)]):
        return cassa().verifica(body.codice)

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
