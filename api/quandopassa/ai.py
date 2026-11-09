"""Client del server di inferenza e base di conoscenza del servizio.

Se il server di inferenza non risponde l'app funziona lo stesso: l'assistente si spegne,
mappa e orari restano (degrado controllato, come in Spazio Comune).
"""
from __future__ import annotations

import logging

import httpx

from .config import Config
from .gtfs import Orario

log = logging.getLogger("quandopassa.ai")


def _testo_biglietti(cfg: Config) -> str:
    if not cfg.biglietti_attivi:
        return cfg.biglietti
    from .biglietti import tariffe  # import qui: la biglietteria è facoltativa
    euro = lambda c: f"{c / 100:.2f}".replace(".", ",") + " €"  # noqa: E731
    voci = "; ".join(f"{t.nome} {euro(t.importo_cent)} ({t.descrizione().lower()})" for t in tariffe(cfg).values())
    return (f"Tariffe: {voci}. Si comprano nella scheda Biglietti dell'app, senza registrazione: il biglietto resta "
            f"sul telefono e si attiva quando sali, mostrando codice e QR all'autista. {cfg.biglietti}")


def base_conoscenza(cfg: Config, orario: Orario) -> list[dict]:
    info = orario.info()
    linee = ", ".join(f"{l['nome']} ({l['nome_esteso']})" for l in info["linee"])
    return [
        {"id": "tempo_reale", "titolo": "Posizione bus tempo reale GPS mappa dove si trova affidabile ritardo",
         "testo": "La posizione dei bus sulla mappa è stimata dall'orario ufficiale (GTFS): non c'è un GPS a bordo. "
                  "Se il bus è in ritardo la mappa non lo sa; per questo l'app mostra sempre l'orario programmato."},
        {"id": "biglietti", "titolo": "Biglietto costo prezzo tariffa abbonamento carnet dove comprare quanto costa",
         "testo": _testo_biglietti(cfg)},
        {"id": "linee", "titolo": "Linee circolari percorso quali bus servizio urbano",
         "testo": f"Il servizio urbano ha {len(info['linee'])} linee: {linee}. Sono circolari: partono e tornano "
                  "allo stesso capolinea. Tocca una linea sulla mappa per vederne il percorso."},
        {"id": "giorni", "titolo": "Domenica festivi giorni circola orari settimana martedì mercato",
         "testo": "Le linee circolano dal lunedì al sabato, la domenica non c'è servizio. La Circolare A ordinaria "
                  "non circola il martedì (giorno di mercato, con un percorso diverso)."},
        {"id": "contatti", "titolo": "Contatti telefono azienda reclamo segnalazione oggetti smarriti",
         "testo": f"Azienda: {info['agenzia']}, telefono {info['telefono']}. Per segnalazioni sulle fermate o sul "
                  "servizio contatta l'azienda o l'Ufficio Trasporti del Comune."},
        {"id": "fermate_nuove", "titolo": "Pensiline nuove fermate proposta localizzazione progetto",
         "testo": "Le fermate mostrate sono le 20 aree della proposta preliminare di localizzazione delle pensiline "
                  "(Circolari A e B). Le posizioni sono indicative e saranno verificate con sopralluogo."},
        {"id": "privacy", "titolo": "Privacy posizione geolocalizzazione dati personali",
         "testo": "La tua posizione resta sul telefono: serve solo a trovare la fermata più vicina e non viene salvata. "
                  "L'assistente IA non riceve dati personali."},
    ]


class ClientIA:
    def __init__(self, base_url: str | None, timeout: float = 8.0, client: httpx.Client | None = None):
        self.base_url = (base_url or "").rstrip("/")
        self._http = client or httpx.Client(timeout=timeout)

    @property
    def attivo(self) -> bool:
        return bool(self.base_url)

    def _post(self, percorso: str, corpo: dict) -> dict | None:
        if not self.attivo:
            return None
        try:
            r = self._http.post(f"{self.base_url}{percorso}", json=corpo)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            log.warning("inference %s non disponibile: %s", percorso, e)
            return None

    def stato(self) -> dict | None:
        if not self.attivo:
            return None
        try:
            r = self._http.get(f"{self.base_url}/health")
            r.raise_for_status()
            return r.json()
        except Exception:  # noqa: BLE001
            return None

    def interpreta(self, testo: str) -> dict | None:
        return self._post("/v1/tasks/intent", {"testo": testo})

    def formula(self, domanda: str, intento: str, dati: dict, bozza: str) -> dict | None:
        return self._post("/v1/tasks/answer", {"domanda": domanda, "intento": intento, "dati": dati, "bozza": bozza})

    def faq(self, domanda: str, documenti: list[dict]) -> dict | None:
        return self._post("/v1/tasks/faq", {"domanda": domanda, "documenti": documenti})
