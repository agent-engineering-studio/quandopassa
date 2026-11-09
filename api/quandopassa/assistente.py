"""Assistente: dalla frase del cittadino a una risposta fondata sull'orario GTFS.

Divisione dei compiti (come in Spazio Comune):
  - il server di inferenza CAPISCE la frase (intento, luogo, linea, ora);
  - l'app CALCOLA la risposta dai dati (orario, posizione) e scrive una bozza;
  - un LLM, se configurato, può solo RIFORMULARE la bozza con i dati forniti.
Così orari e minuti non sono mai inventati dal modello.
"""
from __future__ import annotations

from datetime import datetime, time

from .ai import ClientIA, base_conoscenza
from .config import Config
from .gtfs import Orario

ESEMPI = [
    "Quando passa il prossimo bus?",
    "Come arrivo al cimitero?",
    "Dov'è adesso la linea B?",
    "Orari della circolare A",
    "Quanto costa il biglietto?",
]


class AssistenteNonDisponibile(Exception):
    pass


def _hhmm(iso: str) -> str:
    return iso[11:16]


def _tra(minuti: int) -> str:
    if minuti <= 0:
        return "adesso"
    if minuti < 60:
        return f"tra {minuti} min"
    h, m = divmod(minuti, 60)
    return f"tra {h} h {m:02d} min" if h < 24 else f"tra {h // 24} giorni"


def _quando(iso: str, ora: datetime) -> str:
    d = datetime.fromisoformat(iso)
    if d.date() == ora.date():
        return f"alle {_hhmm(iso)}"
    giorni = (d.date() - ora.date()).days
    if giorni == 1:
        return f"domani alle {_hhmm(iso)}"
    nomi = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
    return f"{nomi[d.weekday()]} alle {_hhmm(iso)}"


class Assistente:
    def __init__(self, cfg: Config, orario: Orario, ia: ClientIA):
        self.cfg, self.orario, self.ia = cfg, orario, ia

    def rispondi(self, testo: str, ora: datetime, lat: float | None = None, lon: float | None = None) -> dict:
        intento = self.ia.interpreta(testo)
        if intento is None:
            raise AssistenteNonDisponibile()
        tipo = intento.get("intento") or "sconosciuto"
        istante = ora
        if intento.get("ora"):
            h, m = (int(x) for x in intento["ora"].split(":"))
            candidato = datetime.combine(ora.date(), time(h, m), ora.tzinfo)
            if candidato >= ora.replace(second=0, microsecond=0):
                istante = candidato
        fermata = None
        if intento.get("luogo"):
            trovate = self.orario.cerca(intento["luogo"], n=1)
            fermata = trovate[0] if trovate else None
        posizione = (lat, lon) if lat is not None and lon is not None else None

        gestore = {
            "vicina": self._vicina, "prossimo": self._prossimo, "dove_bus": self._dove_bus,
            "percorso": self._percorso, "orari_linea": self._orari_linea,
        }.get(tipo)
        if gestore:
            bozza, dati = gestore(intento=intento, fermata=fermata, posizione=posizione, ora=istante)
            fonti = ["orario GTFS " + self.orario.info()["versione_feed"]]
        else:
            bozza, dati, fonti = self._faq(testo)
            tipo = "faq" if dati.get("trovata") else "sconosciuto"

        risposta, backend, da_ia = bozza, intento.get("backend", "rules"), bool(intento.get("generato_da_ia"))
        if tipo not in ("sconosciuto",):
            riformulata = self.ia.formula(testo, tipo, dati, bozza)
            if riformulata and riformulata.get("risposta"):
                risposta = riformulata["risposta"]
                backend = riformulata.get("backend", backend)
                da_ia = da_ia or bool(riformulata.get("generato_da_ia"))
        return {"risposta": risposta, "intento": tipo, "interpretazione": intento, "dati": dati, "fonti": fonti,
                "backend": backend, "generato_da_ia": da_ia,
                "avviso": "Risposta automatica basata sull'orario programmato: verifica sempre alla fermata."}

    # ---------------------------------------------------------- gestori
    def _vicina(self, posizione, ora, **_):
        if not posizione:
            return ("Per trovare la fermata più vicina attiva la posizione del telefono (icona del mirino sulla mappa).",
                    {"serve_posizione": True})
        f = self.orario.vicine(*posizione, n=1)[0]
        bozza = (f"La fermata più vicina è {f['nome']}, a {f['distanza_m']} m "
                 f"(circa {f['a_piedi_min']} min a piedi), linee {', '.join(f['linee'])}.")
        dati = {"fermata": f}
        p = self.orario.partenze(f["id"], ora, n=3)
        if p:
            dati["partenze"] = p
            bozza += " " + self._frase_partenze(p, ora, f["a_piedi_min"])
        return bozza, dati

    def _frase_partenze(self, p: list[dict], ora: datetime, a_piedi: int | None = None) -> str:
        primo = p[0]
        frase = f"Prossimo bus: linea {primo['linea']} {_quando(primo['orario'], ora)} ({_tra(primo['tra_minuti'])})"
        if a_piedi is not None and primo["tra_minuti"] < 24 * 60:
            if primo["tra_minuti"] >= a_piedi:
                frase += f": se esci ora fai in tempo, hai {primo['tra_minuti'] - a_piedi} min di margine."
            else:
                frase += ": a piedi non fai in tempo."
                if len(p) > 1:
                    frase += f" Il successivo è {_quando(p[1]['orario'], ora)} (linea {p[1]['linea']})."
                return frase
        else:
            frase += "."
        if len(p) > 1:
            frase += " Poi: " + ", ".join(f"{x['linea']} {_quando(x['orario'], ora)}" for x in p[1:3]) + "."
        return frase

    def _prossimo(self, fermata, posizione, ora, **kw):
        a_piedi = None
        if fermata is None:
            if not posizione:
                return ("Da quale fermata? Scrivi per esempio \"prossimo bus da Piazza Plebiscito\", oppure attiva "
                        "la posizione e ti dico la fermata più vicina.", {"serve_fermata": True})
            fermata = self.orario.vicine(*posizione, n=1)[0]
            a_piedi = fermata["a_piedi_min"]
        p = self.orario.partenze(fermata["id"], ora, n=3)
        if not p:
            return f"Nei prossimi giorni non risultano corse da {fermata['nome']}.", {"fermata": fermata, "partenze": []}
        return f"Da {fermata['nome']}: " + self._frase_partenze(p, ora, a_piedi), {"fermata": fermata, "partenze": p}

    def _dove_bus(self, intento, ora, **_):
        veicoli = self.orario.veicoli(ora)
        if intento.get("linea"):
            veicoli = [v for v in veicoli if v["linea"].upper() == intento["linea"].upper()]
        if not veicoli:
            nxt = self.orario.prossima_corsa(ora)
            testo = "In questo momento non ci sono bus in servizio"
            testo += f" sulla linea {intento['linea']}." if intento.get("linea") else "."
            if nxt:
                testo += f" La prossima corsa (linea {nxt['linea']}) parte {_quando(nxt['partenza'], ora)} da {nxt['fermata']}."
            return testo, {"veicoli": [], "prossima_corsa": nxt}
        parti = []
        for v in veicoli:
            stato = "è fermo a" if v["stato"] == "in_fermata" else "sta arrivando a"
            parti.append(f"il bus della linea {v['linea']} {stato} {v['prossima_fermata']} "
                         f"(previsto alle {_hhmm(v['arrivo_prossima'])})")
        return "Secondo l'orario " + "; ".join(parti) + ". Lo vedi muoversi sulla mappa.", {"veicoli": veicoli}

    def _percorso(self, fermata, posizione, ora, **_):
        if fermata is None:
            return ("Non ho riconosciuto la destinazione tra le fermate. Prova con il nome di una via o di un luogo, "
                    "per esempio \"come arrivo a Piazza Plebiscito\".", {"serve_fermata": True})
        if not posizione:
            p = self.orario.partenze(fermata["id"], ora, n=2)
            return (f"Per calcolare il percorso fino a {fermata['nome']} attiva la posizione. Intanto: da lì passano "
                    f"le linee {', '.join(self.orario.linee_della_fermata(fermata['id']))}.",
                    {"fermata": fermata, "partenze": p, "serve_posizione": True})
        vicine = self.orario.vicine(*posizione, n=1)
        if vicine and vicine[0]["id"] == fermata["id"] and vicine[0]["distanza_m"] <= 500:
            return (f"{fermata['nome']} è a {vicine[0]['distanza_m']} m da te: ci arrivi a piedi in "
                    f"{vicine[0]['a_piedi_min']} min.", {"fermata": fermata, "a_piedi": True})
        opzioni = self.orario.percorso(*posizione, [fermata["id"]], ora)
        if not opzioni:
            return (f"Non trovo un bus diretto dalle fermate vicine a te fino a {fermata['nome']}. "
                    "Guarda le linee sulla mappa o chiedi gli orari di una fermata.", {"fermata": fermata, "opzioni": []})
        o = opzioni[0]
        bozza = (f"Cammina fino a {o['fermata_salita']} ({o['a_piedi_m']} m, {o['a_piedi_min']} min, esci entro le "
                 f"{_hhmm(o['esci_entro'])}), prendi la linea {o['linea']} {_quando(o['partenza'], ora)} e scendi a "
                 f"{o['fermata_discesa']} alle {_hhmm(o['arrivo'])}"
                 + (f" dopo {o['fermate_intermedie']} fermate." if o['fermate_intermedie'] else ", fermata successiva."))
        return bozza, {"fermata": fermata, "opzioni": opzioni}

    def _orari_linea(self, intento, ora, **_):
        linee = [intento["linea"].upper()] if intento.get("linea") else list(self.orario.linee)
        dati, frasi = {}, []
        for lid in linee:
            if lid not in self.orario.linee:
                continue
            corse = [c for c in self.orario.corse_del_giorno(ora.date()) if c.linea_id == lid]
            orari = [f"{c.partenze[0] // 3600:02d}:{c.partenze[0] % 3600 // 60:02d}" for c in corse]
            dati[lid] = {"partenze_capolinea": orari, "capolinea": self.orario.fermate[corse[0].fermate[0]].nome if corse else None}
            nome = self.orario.linee[lid].nome_esteso
            if orari:
                frasi.append(f"{nome} oggi parte da {dati[lid]['capolinea']} alle {', '.join(orari)}.")
            else:
                frasi.append(f"{nome} oggi non circola.")
        if not frasi:
            return f"Non conosco la linea {intento.get('linea')}. Linee: {', '.join(self.orario.linee)}.", {}
        return " ".join(frasi), dati

    def _faq(self, testo: str):
        r = self.ia.faq(testo, base_conoscenza(self.cfg, self.orario))
        if r and r.get("trovata"):
            return r["risposta"], {"trovata": True}, r.get("fonti", [])
        return ("Non ho capito la domanda. Puoi chiedermi, per esempio: " + "; ".join(f"\"{e}\"" for e in ESEMPI[:4])
                + ".", {"trovata": False, "esempi": ESEMPI}, [])
