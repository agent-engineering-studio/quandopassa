"""QuandoPassa – API e interfaccia web del bus urbano.

    uvicorn --factory quandopassa.main:create_app --reload

API pubbliche (JSON, /api/v1):
  GET  /health                         stato di app, feed, database e IA
  GET  /info                           servizio, linee, versione del feed, avvisi
  GET  /ora                            orologio del servizio (per sincronizzare l'interfaccia)
  GET  /fermate                        tutte le fermate con media recensioni
  GET  /fermate/vicine?lat&lon&n       fermate più vicine con distanza e minuti a piedi
  GET  /fermate/cerca?q                ricerca per nome
  GET  /fermate/{id}                   dettaglio + prossime partenze + riepilogo recensioni
  GET  /fermate/{id}/partenze?n&ora    prossimi passaggi
  GET  /linee                          linee con tracciati e fermate
  GET  /orario?giorno                  corse e tracciati del giorno (l'interfaccia anima i bus da sola)
  GET  /veicoli?ora                    bus in servizio con posizione stimata dall'orario
  GET  /percorso?lat&lon&a             come arrivo: a piedi + bus diretto
  GET  /assistente?testo&lat&lon       assistente IA
  GET  /recensioni?tipo&id             recensioni di fermata / linea / servizio
  GET  /recensioni/riepilogo?tipo&id   media, distribuzione, etichette, sintesi IA
  GET  /recensioni/etichette           etichette ammesse per tipo
  POST /recensioni                     nuova recensione (anonima, senza dati personali)
Ufficio (HTTP Basic, UFFICIO_USER/UFFICIO_PASSWORD):
  GET  /ufficio/recensioni             ultime recensioni, comprese le nascoste
  POST /ufficio/recensioni/{id}/nascondi | /mostra
"""

import logging
import secrets
from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .ai import ClientIA
from .assistente import ESEMPI, Assistente, AssistenteNonDisponibile
from .config import Config
from .feedback import TAG, TIPI, Archivio, ErroreRecensione, NuovaRecensione, crea_archivio, impronta
from .gtfs import Orario

log = logging.getLogger("quandopassa")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


class RecensioneIn(BaseModel):
    tipo: str = Field(..., pattern="^(fermata|linea|servizio)$")
    id: str = Field(..., min_length=1, max_length=64)
    voto: int = Field(..., ge=1, le=5)
    testo: str = Field("", max_length=1000)
    tag: list[str] = Field(default_factory=list, max_length=12)
    autore: str = Field("", max_length=40)


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


def create_app(cfg: Config | None = None, archivio: Archivio | None = None, ia: ClientIA | None = None) -> FastAPI:
    cfg = cfg or Config()
    orario = Orario(cfg.gtfs_dir, cfg.fuso)
    archivio = archivio or crea_archivio(cfg.database_url, cfg.database_schema or None)
    ia = ia or ClientIA(cfg.inference_url)
    orologio = Orologio(orario.fuso, cfg.demo_ora)
    assistente = Assistente(cfg, orario, archivio, ia)
    log.info("feed %s: %s fermate (%s provvisorie), %s corse", cfg.gtfs_dir, len(orario.fermate),
             orario.info()["fermate_provvisorie"], len(orario.corse))

    app = FastAPI(title="QuandoPassa", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.orario, app.state.archivio, app.state.orologio = orario, archivio, orologio
    basic = HTTPBasic(auto_error=False)

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

    def ufficio(cred: Annotated[HTTPBasicCredentials | None, Depends(basic)]) -> str:
        if not (cfg.ufficio_user and cfg.ufficio_password):
            raise HTTPException(503, "Area ufficio non configurata (UFFICIO_USER/UFFICIO_PASSWORD)")
        ok = cred is not None and secrets.compare_digest(cred.username, cfg.ufficio_user) \
            and secrets.compare_digest(cred.password, cfg.ufficio_password)
        if not ok:
            raise HTTPException(401, "Credenziali non valide", headers={"WWW-Authenticate": "Basic"})
        return cred.username

    @app.exception_handler(ErroreRecensione)
    async def _errore_recensione(_: Request, e: ErroreRecensione):
        return JSONResponse({"errore": str(e)}, status_code=422)

    # ---------------------------------------------------------- servizio
    @app.get("/api/v1/health")
    def health():
        stato_ia = ia.stato()
        return {"stato": "ok", "feed": orario.info()["versione_feed"], "database": type(archivio).__name__,
                "ia": stato_ia or ("non configurata" if not ia.attivo else "non raggiungibile")}

    @app.get("/api/v1/info")
    def info():
        ora = orologio.adesso()
        ia_attiva = ia.stato() is not None
        return {**orario.info(), "comune": cfg.comune, "servizio": cfg.servizio, "centro": list(cfg.centro),
                "mappa": {"tiles": cfg.mappa_tiles, "attribuzione": cfg.mappa_attribuzione},
                "ora": ora.isoformat(timespec="seconds"), "prossima_corsa": orario.prossima_corsa(ora),
                "assistente": ia_attiva, "esempi_assistente": ESEMPI, "etichette": TAG,
                "avvisi": _avvisi(orario)}

    @app.get("/api/v1/ora")
    def ora_servizio():
        return {"ora": orologio.adesso().isoformat(timespec="milliseconds"), "fuso": str(orario.fuso),
                "demo": bool(cfg.demo_ora)}

    # ---------------------------------------------------------- fermate
    @app.get("/api/v1/fermate")
    def fermate():
        medie = archivio.medie("fermata")
        return [{**f.json(), "linee": orario.linee_della_fermata(f.id), "recensioni": medie.get(f.id)}
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
                "partenze": orario.partenze(fid, istante(ora), n=6),
                "recensioni": archivio.riepilogo("fermata", fid)}

    @app.get("/api/v1/fermate/{fid}/partenze")
    def partenze(fid: str, n: int = Query(5, ge=1, le=30), ora: str | None = None):
        fermata_o_404(fid)
        return orario.partenze(fid, istante(ora), n=n)

    # ---------------------------------------------------------- linee e bus
    @app.get("/api/v1/linee")
    def linee():
        medie = archivio.medie("linea")
        out = []
        for l in orario.linee.values():
            tracciati = [t.json() for t in orario.tracciati.values() if t.linea_id == l.id]
            fermate_linea = list(dict.fromkeys(s for t in tracciati for s in t["fermate"]))
            out.append({**l.json(), "tracciati": tracciati, "fermate": fermate_linea, "recensioni": medie.get(l.id)})
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

    # ---------------------------------------------------------- assistente
    @app.get("/api/v1/assistente")
    def chiedi(testo: str = Query(..., min_length=2, max_length=500), lat: float | None = None,
               lon: float | None = None, ora: str | None = None):
        try:
            return assistente.rispondi(testo, istante(ora), lat, lon)
        except AssistenteNonDisponibile:
            raise HTTPException(503, "Assistente non disponibile: mappa e orari funzionano comunque") from None

    # ---------------------------------------------------------- recensioni
    def _verifica_oggetto(tipo: str, oid: str) -> str:
        if tipo == "fermata" and oid in orario.fermate:
            return orario.fermate[oid].nome
        if tipo == "linea" and oid in orario.linee:
            return orario.linee[oid].nome_esteso
        if tipo == "servizio" and oid == "generale":
            return cfg.servizio
        raise HTTPException(404, f"{tipo} {oid} non trovata")

    @app.get("/api/v1/recensioni/etichette")
    def etichette():
        return TAG

    @app.get("/api/v1/recensioni")
    def recensioni(tipo: str = Query(..., pattern="^(fermata|linea|servizio)$"), id: str = "generale",
                   n: int = Query(20, ge=1, le=100)):
        _verifica_oggetto(tipo, id)
        return {"riepilogo": archivio.riepilogo(tipo, id), "recensioni": archivio.elenco(tipo, id, n)}

    @app.get("/api/v1/recensioni/riepilogo")
    def riepilogo(tipo: str = Query(..., pattern="^(fermata|linea|servizio)$"), id: str = "generale"):
        nome = _verifica_oggetto(tipo, id)
        r = archivio.riepilogo(tipo, id)
        sintesi = None
        if r["conteggio"]:
            ultime = [{"voto": x["voto"], "testo": x["testo"], "tag": x["tag"]} for x in archivio.elenco(tipo, id, 30)]
            sintesi = ia.sintesi(nome, ultime)
        return {**r, "oggetto": nome, "sintesi": sintesi}

    @app.post("/api/v1/recensioni", status_code=201)
    def nuova(body: RecensioneIn, request: Request):
        _verifica_oggetto(body.tipo, body.id)
        ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0]
        rec = NuovaRecensione(body.tipo, body.id, body.voto, body.testo, body.tag, body.autore)
        return archivio.aggiungi(rec, impronta(ip.strip(), cfg.secret_key))

    # ---------------------------------------------------------- ufficio
    @app.get("/api/v1/ufficio/recensioni")
    def ufficio_recensioni(_: Annotated[str, Depends(ufficio)], n: int = Query(100, ge=1, le=500)):
        return archivio.ultime(n, nascoste=True)

    @app.post("/api/v1/ufficio/recensioni/{rid}/{azione}")
    def ufficio_modera(rid: str, azione: str, _: Annotated[str, Depends(ufficio)]):
        if azione not in ("nascondi", "mostra"):
            raise HTTPException(404, "azione: nascondi | mostra")
        if not archivio.nascondi(rid, azione == "nascondi"):
            raise HTTPException(404, "Recensione non trovata")
        return {"id": rid, "nascosta": azione == "nascondi"}

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
