"""Server MCP di QuandoPassa: il bus urbano come strumento per assistenti e sistemi agentici.

Espone ad agenti esterni (Claude, Copilot, orchestratori, IDE) le stesse informazioni dell'app
passando dalle sue API HTTP: non legge il database e non conosce i segreti dell'app.

Strumenti per tutti:
  info_servizio, cerca_fermata, fermate_vicine, prossime_partenze, bus_in_servizio,
  come_arrivare, orari_linea, chiedi_assistente, recensioni, riepilogo_recensioni
Strumento di scrittura (solo con MCP_RECENSIONI_SCRITTURA=true):
  lascia_recensione  – l'agente deve avere il consenso esplicito della persona
Strumenti per l'ufficio (solo con QUANDOPASSA_UFFICIO_USER/PASSWORD):
  ultime_recensioni, modera_recensione

    python mcp_server/server.py                         # stdio (Claude Desktop, Claude Code, IDE)
    MCP_TRANSPORT=http python mcp_server/server.py      # HTTP streamable su :8090/mcp
"""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

ISTRUZIONI = (
    "Strumenti per il bus urbano di Gioia del Colle: fermate, prossimi passaggi, bus in servizio, percorsi a piedi + "
    "bus, orari delle linee e recensioni dei cittadini. Le posizioni dei bus sono STIMATE dall'orario programmato "
    "(GTFS), non da GPS: dillo quando riporti dove si trova un bus. Orari in fuso Europe/Rome. Non chiedere né "
    "inviare dati personali; la posizione della persona usala solo per la richiesta in corso."
)


class ErroreApp(Exception):
    pass


class ClientApp:
    """Chiamate alle API di QuandoPassa; gli errori diventano messaggi leggibili per l'agente."""

    def __init__(self, base_url: str, client: httpx.Client | None = None,
                 ufficio: tuple[str, str] | None = None, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.ufficio = ufficio
        self._http = client or httpx.Client(timeout=timeout)

    def _richiesta(self, metodo: str, percorso: str, riservato: bool = False, json: dict | None = None,
                   **params: Any) -> Any:
        params = {k: v for k, v in params.items() if v is not None}
        try:
            r = self._http.request(metodo, f"{self.base_url}{percorso}", params=params, json=json,
                                   auth=self.ufficio if riservato else None)
        except httpx.HTTPError as e:
            raise ErroreApp(f"QuandoPassa non raggiungibile su {self.base_url}: {e}") from None
        if r.status_code >= 400:
            try:
                corpo = r.json()
                messaggio = corpo.get("errore") or corpo.get("detail")
            except ValueError:
                messaggio = r.text[:200]
            raise ErroreApp(f"Errore {r.status_code}: {messaggio}")
        return r.json()

    def get(self, percorso: str, riservato: bool = False, **params: Any) -> Any:
        return self._richiesta("GET", percorso, riservato, **params)

    def post(self, percorso: str, json: dict | None = None, riservato: bool = False) -> Any:
        return self._richiesta("POST", percorso, riservato, json=json)


def _tipo(tipo: str) -> str:
    if tipo not in ("fermata", "linea", "servizio"):
        raise ErroreApp("tipo deve essere fermata, linea o servizio")
    return tipo


def crea_server(app: ClientApp | None = None, scrittura: bool | None = None) -> FastMCP:
    if app is None:
        user, pwd = os.getenv("QUANDOPASSA_UFFICIO_USER"), os.getenv("QUANDOPASSA_UFFICIO_PASSWORD")
        app = ClientApp(os.getenv("QUANDOPASSA_URL", "http://localhost:8000"),
                        ufficio=(user, pwd) if user and pwd else None)
    if scrittura is None:
        scrittura = os.getenv("MCP_RECENSIONI_SCRITTURA", "false").lower() in ("1", "true", "si", "yes")
    consentiti = [h.strip() for h in os.getenv("MCP_ALLOWED_HOSTS", "localhost:*,127.0.0.1:*").split(",") if h.strip()]
    mcp = FastMCP(
        "quandopassa", instructions=ISTRUZIONI, host=os.getenv("MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("MCP_PORT", "8090")),
        transport_security=TransportSecuritySettings(  # protezione da DNS rebinding sul trasporto HTTP
            enable_dns_rebinding_protection=True, allowed_hosts=consentiti,
            allowed_origins=[f"http://{h.replace(':*', '')}" for h in consentiti]),
    )

    @mcp.tool()
    def info_servizio() -> dict:
        """Il servizio: azienda, linee (colori), validità dell'orario, ora attuale, prossima corsa e avvisi."""
        return app.get("/api/v1/info")

    @mcp.tool()
    def cerca_fermata(nome: str) -> list[dict]:
        """Fermate il cui nome somiglia a `nome` (es. "plebiscito", "cimitero", "seven"), con id e coordinate."""
        return app.get("/api/v1/fermate/cerca", q=nome[:100], n=5)

    @mcp.tool()
    def fermate_vicine(lat: float, lon: float, n: int = 3) -> list[dict]:
        """Fermate più vicine al punto (WGS84) con distanza, minuti a piedi, linee e prossimi 2 passaggi."""
        return app.get("/api/v1/fermate/vicine", lat=lat, lon=lon, n=max(1, min(n, 10)))

    @mcp.tool()
    def prossime_partenze(fermata_id: str, n: int = 5, ora: str | None = None) -> list[dict]:
        """Prossimi passaggi dalla fermata (id da cerca_fermata). `ora` facoltativa ISO 8601 (es. 2026-11-10T09:00)."""
        return app.get(f"/api/v1/fermate/{quote(fermata_id)}/partenze", n=max(1, min(n, 20)), ora=ora)

    @mcp.tool()
    def bus_in_servizio(linea: str | None = None, ora: str | None = None) -> dict:
        """Bus in servizio adesso (o all'`ora` ISO indicata) con posizione STIMATA dall'orario, prossima fermata
        e orario previsto. Se non ce ne sono, indica la prossima corsa."""
        return app.get("/api/v1/veicoli", linea=linea, ora=ora)

    @mcp.tool()
    def come_arrivare(lat: float, lon: float, destinazione: str, ora: str | None = None) -> dict:
        """Dal punto (lat, lon) alla destinazione (nome o id di fermata): fermata dove salire, minuti a piedi,
        orario entro cui uscire, linea, discesa e arrivo. Solo viaggi diretti senza cambi."""
        return app.get("/api/v1/percorso", lat=lat, lon=lon, a=destinazione[:100], ora=ora)

    @mcp.tool()
    def orari_linea(linea: str) -> dict:
        """Tracciato e fermate della linea (A, B, ...) e, tramite bus_in_servizio/prossime_partenze, i suoi passaggi."""
        for l in app.get("/api/v1/linee"):
            if l["id"].upper() == linea.upper():
                return {k: v for k, v in l.items() if k != "tracciati"} | {
                    "tracciati": [{"id": t["id"], "fermate": t["fermate"]} for t in l["tracciati"]]}
        raise ErroreApp(f"Linea {linea} inesistente")

    @mcp.tool()
    def chiedi_assistente(domanda: str, lat: float | None = None, lon: float | None = None) -> dict:
        """Domanda in italiano all'assistente del servizio (es. "come arrivo al cimitero?"). La risposta è
        calcolata sull'orario ufficiale; passa lat/lon se la persona ha condiviso la posizione."""
        return app.get("/api/v1/assistente", testo=domanda[:500], lat=lat, lon=lon)

    @mcp.tool()
    def recensioni(tipo: str, id: str = "generale", n: int = 10) -> dict:
        """Recensioni dei cittadini. tipo: fermata (id fermata), linea (id linea) o servizio (id "generale")."""
        return app.get("/api/v1/recensioni", tipo=_tipo(tipo), id=id, n=max(1, min(n, 50)))

    @mcp.tool()
    def riepilogo_recensioni(tipo: str, id: str = "generale") -> dict:
        """Media, distribuzione delle stelle, etichette più citate e sintesi (IA o regole) delle recensioni."""
        return app.get("/api/v1/recensioni/riepilogo", tipo=_tipo(tipo), id=id)

    if scrittura:
        @mcp.tool()
        def lascia_recensione(tipo: str, id: str, voto: int, testo: str = "", tag: list[str] | None = None) -> dict:
            """Pubblica una recensione anonima PER CONTO della persona, solo dopo che ti ha confermato voto e testo.
            Etichette ammesse: vedi info_servizio().etichette[tipo]. Niente dati personali nel testo."""
            return app.post("/api/v1/recensioni", {"tipo": _tipo(tipo), "id": id, "voto": voto, "testo": testo[:1000],
                                                   "tag": tag or [], "autore": "via assistente"})

    if app.ufficio:
        @mcp.tool()
        def ultime_recensioni(n: int = 50) -> list[dict]:
            """[Ufficio] Ultime recensioni, comprese quelle nascoste, per moderazione e analisi."""
            return app.get("/api/v1/ufficio/recensioni", riservato=True, n=max(1, min(n, 500)))

        @mcp.tool()
        def modera_recensione(id: str, nascondi: bool = True) -> dict:
            """[Ufficio] Nasconde (o rende di nuovo visibile) una recensione offensiva o fuori tema."""
            return app.post(f"/api/v1/ufficio/recensioni/{quote(id)}/{'nascondi' if nascondi else 'mostra'}",
                            riservato=True)

    return mcp


if __name__ == "__main__":
    trasporto = os.getenv("MCP_TRANSPORT", "stdio")
    crea_server().run("streamable-http" if trasporto == "http" else "stdio")
