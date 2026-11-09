"""Motore GTFS statico: dove sono i bus ADESSO secondo l'orario, prossime partenze, percorsi.

Nessun dato in tempo reale (niente GPS/IoT): la posizione di ogni bus è stimata interpolando
tra gli orari di passaggio delle fermate (stop_times) lungo il tracciato (shapes.txt, se c'è,
altrimenti la spezzata tra le fermate). È la stessa logica che usa l'interfaccia per animare
i bus; qui serve alle API e al server MCP.

Gli orari GTFS sono "secondi dalla mezzanotte del giorno di servizio" e possono superare le 24h.
"""
from __future__ import annotations

import csv
import difflib
import hashlib
import math
import re
import unicodedata
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

VELOCITA_PIEDI = 1.2      # m/s, passo tranquillo
TORTUOSITA = 1.3          # strada reale / linea d'aria
GIORNI = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


# ------------------------------------------------------------------ geometria
def metri(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distanza haversine in metri tra (lat, lon)."""
    r = 6_371_000
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def rotta(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Direzione in gradi (0 = nord, senso orario) da a verso b."""
    y = math.sin(math.radians(b[1] - a[1])) * math.cos(math.radians(b[0]))
    x = (math.cos(math.radians(a[0])) * math.sin(math.radians(b[0]))
         - math.sin(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.cos(math.radians(b[1] - a[1])))
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def minuti_a_piedi(m: float) -> int:
    return max(1, round(m * TORTUOSITA / VELOCITA_PIEDI / 60))


def normalizza(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"\bp\.?\s?za\b", "piazza", t)
    t = re.sub(r"\bc\.?\s?so\b", "corso", t)
    t = re.sub(r"\bs\.\s?", "san ", t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


_VUOTE = set("via viale piazza piazzetta corso largo della del dei di da la le il lo e a fermata".split())


# ------------------------------------------------------------------ modello
@dataclass
class Fermata:
    id: str
    codice: str
    nome: str
    lat: float
    lon: float
    descrizione: str = ""
    posizione: str = "gtfs"     # osm:<strategia> | manuale | provvisoria | gtfs

    @property
    def provvisoria(self) -> bool:
        return self.posizione == "provvisoria"

    def json(self) -> dict:
        return {"id": self.id, "codice": self.codice, "nome": self.nome, "lat": self.lat, "lon": self.lon,
                "descrizione": self.descrizione, "posizione": self.posizione, "provvisoria": self.provvisoria}


@dataclass
class Linea:
    id: str
    nome: str
    nome_esteso: str
    colore: str
    colore_testo: str

    def json(self) -> dict:
        return {"id": self.id, "nome": self.nome, "nome_esteso": self.nome_esteso,
                "colore": f"#{self.colore}", "colore_testo": f"#{self.colore_testo}"}


@dataclass
class Tracciato:
    """Polilinea con distanze progressive e posizione (in metri) di ogni fermata della sequenza."""
    id: str
    linea_id: str
    fermate: tuple[str, ...]
    punti: list[tuple[float, float]]
    progressive: list[float]
    distanze_fermate: list[float]

    def punto_a(self, d: float) -> tuple[tuple[float, float], float]:
        """Punto e rotta alla distanza d lungo il tracciato."""
        d = max(0.0, min(d, self.progressive[-1]))
        i = max(0, min(bisect_right(self.progressive, d) - 1, len(self.punti) - 2))
        a, b = self.punti[i], self.punti[i + 1]
        seg = self.progressive[i + 1] - self.progressive[i]
        f = 0.0 if seg <= 0 else (d - self.progressive[i]) / seg
        return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f), rotta(a, b)

    def json(self) -> dict:
        return {"id": self.id, "linea_id": self.linea_id, "fermate": list(self.fermate),
                "punti": [[round(p[0], 6), round(p[1], 6)] for p in self.punti],
                "progressive": [round(x, 1) for x in self.progressive],
                "distanze_fermate": [round(x, 1) for x in self.distanze_fermate]}


@dataclass
class Corsa:
    id: str
    linea_id: str
    servizio_id: str
    destinazione: str
    tracciato_id: str
    fermate: list[str] = field(default_factory=list)
    arrivi: list[int] = field(default_factory=list)       # secondi dalla mezzanotte del giorno di servizio
    partenze: list[int] = field(default_factory=list)

    def json(self) -> dict:
        return {"id": self.id, "linea_id": self.linea_id, "destinazione": self.destinazione,
                "tracciato_id": self.tracciato_id, "fermate": self.fermate,
                "arrivi": self.arrivi, "partenze": self.partenze}


def _secondi(hms: str) -> int:
    h, m, s = (int(x) for x in hms.strip().split(":"))
    return h * 3600 + m * 60 + s


def _leggi(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as f:
        return [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(f)]


def _progressive(punti: list[tuple[float, float]]) -> list[float]:
    out = [0.0]
    for a, b in zip(punti, punti[1:]):
        out.append(out[-1] + metri(a, b))
    return out


def _proietta(punti: list[tuple[float, float]], prog: list[float], p: tuple[float, float], da: int) -> tuple[float, int]:
    """Proiezione del punto p sulla polilinea, cercando in avanti dal segmento `da`
    (le circolari passano due volte dalla stessa fermata: la ricerca in avanti sceglie il passaggio giusto)."""
    migliore = (float("inf"), prog[da], da)
    lat0 = math.cos(math.radians(p[0]))
    for i in range(da, len(punti) - 1):
        a, b = punti[i], punti[i + 1]
        ax, ay = (a[1] - p[1]) * lat0, a[0] - p[0]
        bx, by = (b[1] - p[1]) * lat0, b[0] - p[0]
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / L))
        qx, qy = ax + t * dx, ay + t * dy
        dist = math.hypot(qx, qy)
        if dist < migliore[0] - 1e-9:
            migliore = (dist, prog[i] + t * (prog[i + 1] - prog[i]), i)
        # la prima "buona" corrispondenza vince: evita di saltare al passaggio successivo
        if migliore[0] < 0.0003 and dist > migliore[0] * 4 and i > migliore[2] + 3:
            break
    return migliore[1], migliore[2]


class Orario:
    """Un feed GTFS caricato in memoria (i feed urbani sono piccoli)."""

    def __init__(self, cartella: str | Path, fuso: str = "Europe/Rome"):
        self.cartella = Path(cartella)
        self.fuso = ZoneInfo(fuso)
        c = self.cartella
        if not (c / "stops.txt").exists():
            raise FileNotFoundError(f"Feed GTFS non trovato in {c} (manca stops.txt)")
        self.agenzia = (_leggi(c / "agency.txt") or [{}])[0]
        self.info_feed = (_leggi(c / "feed_info.txt") or [{}])[0]
        self.fermate: dict[str, Fermata] = {}
        for r in _leggi(c / "stops.txt"):
            if r.get("location_type") not in (None, "", "0"):
                continue
            lat, lon = float(r.get("stop_lat") or 0), float(r.get("stop_lon") or 0)
            posizione = r.get("posizione") or ("provvisoria" if lat == 0 and lon == 0 else "gtfs")
            self.fermate[r["stop_id"]] = Fermata(r["stop_id"], r.get("stop_code", ""), r["stop_name"], lat, lon,
                                                 r.get("stop_desc", ""), posizione)
        self.linee: dict[str, Linea] = {
            r["route_id"]: Linea(r["route_id"], r.get("route_short_name") or r["route_id"],
                                 r.get("route_long_name", ""), r.get("route_color") or "0066CC",
                                 r.get("route_text_color") or "FFFFFF")
            for r in _leggi(c / "routes.txt")}
        self.calendario = {r["service_id"]: r for r in _leggi(c / "calendar.txt")}
        self.eccezioni: dict[tuple[str, str], str] = {
            (r["service_id"], r["date"]): r["exception_type"] for r in _leggi(c / "calendar_dates.txt")}

        forme: dict[str, list[tuple[int, tuple[float, float]]]] = {}
        for r in _leggi(c / "shapes.txt"):
            forme.setdefault(r["shape_id"], []).append(
                (int(r["shape_pt_sequence"]), (float(r["shape_pt_lat"]), float(r["shape_pt_lon"]))))

        self.corse: dict[str, Corsa] = {}
        for r in _leggi(c / "trips.txt"):
            self.corse[r["trip_id"]] = Corsa(r["trip_id"], r["route_id"], r["service_id"],
                                             r.get("trip_headsign") or self.linee[r["route_id"]].nome_esteso,
                                             r.get("shape_id", ""))
        righe = sorted(_leggi(c / "stop_times.txt"), key=lambda r: (r["trip_id"], int(r["stop_sequence"])))
        for r in righe:
            corsa = self.corse.get(r["trip_id"])
            if corsa is None or r["stop_id"] not in self.fermate:
                continue
            arr = r.get("arrival_time") or r.get("departure_time")
            par = r.get("departure_time") or arr
            if not arr:
                continue  # fermate non "timepoint" senza orario: non gestite in questa versione
            corsa.fermate.append(r["stop_id"])
            corsa.arrivi.append(_secondi(arr))
            corsa.partenze.append(_secondi(par))
        self.corse = {k: v for k, v in self.corse.items() if len(v.fermate) >= 2}

        # tracciati: uno per (linea, sequenza di fermate, shape)
        self.tracciati: dict[str, Tracciato] = {}
        for corsa in self.corse.values():
            chiave = (corsa.linea_id, tuple(corsa.fermate), corsa.tracciato_id)
            tid = f"{corsa.linea_id}:{hashlib.sha1(repr(chiave).encode(), usedforsecurity=False).hexdigest()[:8]}"
            if tid not in self.tracciati:
                self.tracciati[tid] = self._tracciato(tid, corsa, sorted(forme.get(corsa.tracciato_id, [])))
            corsa.tracciato_id = tid

    def _tracciato(self, tid: str, corsa: Corsa, forma: list[tuple[int, tuple[float, float]]]) -> Tracciato:
        pos = [(self.fermate[s].lat, self.fermate[s].lon) for s in corsa.fermate]
        if len(forma) >= 2:
            punti = [p for _, p in forma]
            prog = _progressive(punti)
            dist, da = [], 0
            for p in pos:
                d, da = _proietta(punti, prog, p, da)
                dist.append(max(d, dist[-1] if dist else 0.0))
            if dist[-1] < prog[-1] * 0.5:  # tracciato incoerente con le fermate: meglio la spezzata
                punti, prog, dist = pos, _progressive(pos), _progressive(pos)
        else:
            punti, prog = pos, _progressive(pos)
            dist = list(prog)
        return Tracciato(tid, corsa.linea_id, tuple(corsa.fermate), punti, prog, dist)

    # -------------------------------------------------------------- calendario
    def adesso(self) -> datetime:
        return datetime.now(self.fuso)

    def servizi_attivi(self, giorno: date) -> set[str]:
        ymd = giorno.strftime("%Y%m%d")
        attivi = set()
        for sid, c in self.calendario.items():
            if c["start_date"] <= ymd <= c["end_date"] and c.get(GIORNI[giorno.weekday()]) == "1":
                attivi.add(sid)
        for (sid, d), tipo in self.eccezioni.items():
            if d == ymd:
                (attivi.add if tipo == "1" else attivi.discard)(sid)
        return attivi

    def corse_del_giorno(self, giorno: date) -> list[Corsa]:
        attivi = self.servizi_attivi(giorno)
        return sorted((c for c in self.corse.values() if c.servizio_id in attivi), key=lambda c: c.partenze[0])

    def _mezzanotte(self, giorno: date) -> datetime:
        return datetime.combine(giorno, time(0), self.fuso)

    # -------------------------------------------------------------- bus in servizio
    def veicoli(self, istante: datetime | None = None) -> list[dict]:
        """Bus in servizio all'istante dato, con posizione stimata dall'orario."""
        ora = (istante or self.adesso()).astimezone(self.fuso)
        out = []
        for giorno in (ora.date() - timedelta(days=1), ora.date()):
            t = (ora - self._mezzanotte(giorno)).total_seconds()
            for c in self.corse_del_giorno(giorno):
                if not (c.partenze[0] <= t <= c.arrivi[-1]):
                    continue
                out.append(self._stato_corsa(c, t, giorno))
        return out

    def _stato_corsa(self, c: Corsa, t: float, giorno: date) -> dict:
        tr = self.tracciati[c.tracciato_id]
        i = max(0, bisect_right(c.partenze, t) - 1)
        if t <= c.partenze[i] or (c.arrivi[i] <= t <= c.partenze[i]):
            stato, d = "in_fermata", tr.distanze_fermate[i]
        else:
            j = min(i + 1, len(c.fermate) - 1)
            dur = max(1, c.arrivi[j] - c.partenze[i])
            f = max(0.0, min(1.0, (t - c.partenze[i]) / dur))
            stato = "in_viaggio"
            d = tr.distanze_fermate[i] + f * (tr.distanze_fermate[j] - tr.distanze_fermate[i])
        (lat, lon), direzione = tr.punto_a(d)
        if stato == "in_fermata":
            _, direzione = tr.punto_a(d + 5)
        prossima = next((k for k in range(len(c.fermate)) if c.arrivi[k] > t), len(c.fermate) - 1)
        mezzanotte = self._mezzanotte(giorno)
        return {
            "corsa_id": c.id, "linea_id": c.linea_id, "linea": self.linee[c.linea_id].nome,
            "colore": f"#{self.linee[c.linea_id].colore}", "destinazione": c.destinazione,
            "lat": round(lat, 6), "lon": round(lon, 6), "direzione": round(direzione),
            "stato": stato,
            "prossima_fermata": self.fermate[c.fermate[prossima]].nome,
            "prossima_fermata_id": c.fermate[prossima],
            "arrivo_prossima": (mezzanotte + timedelta(seconds=c.arrivi[prossima])).isoformat(timespec="minutes"),
            "avanzamento": round((t - c.partenze[0]) / max(1, c.arrivi[-1] - c.partenze[0]), 3),
            "fonte": "orario programmato (nessun GPS)",
        }

    # -------------------------------------------------------------- partenze
    def partenze(self, fermata_id: str, istante: datetime | None = None, n: int = 5,
                 giorni: int = 7) -> list[dict]:
        """Prossimi passaggi dalla fermata (cerca fino a `giorni` giorni avanti: niente corse la domenica)."""
        if fermata_id not in self.fermate:
            raise KeyError(fermata_id)
        ora = (istante or self.adesso()).astimezone(self.fuso)
        out: list[dict] = []
        for k in range(-1, giorni):
            giorno = ora.date() + timedelta(days=k)
            mezzanotte = self._mezzanotte(giorno)
            for c in self.corse_del_giorno(giorno):
                for idx, sid in enumerate(c.fermate):
                    if sid != fermata_id or idx == len(c.fermate) - 1:  # al capolinea finale non si sale
                        continue
                    quando = mezzanotte + timedelta(seconds=c.partenze[idx])
                    if quando < ora:
                        continue
                    out.append({
                        "corsa_id": c.id, "linea_id": c.linea_id, "linea": self.linee[c.linea_id].nome,
                        "colore": f"#{self.linee[c.linea_id].colore}", "destinazione": c.destinazione,
                        "orario": quando.isoformat(timespec="minutes"),
                        "tra_minuti": int((quando - ora).total_seconds() // 60),
                        "in_corsa": c.partenze[0] <= (ora - mezzanotte).total_seconds(),
                    })
            if len(out) >= n and k >= 0:
                break
        out.sort(key=lambda x: x["orario"])
        return out[:n]

    # -------------------------------------------------------------- fermate
    def vicine(self, lat: float, lon: float, n: int = 5, raggio: float | None = None) -> list[dict]:
        righe = []
        for f in self.fermate.values():
            d = metri((lat, lon), (f.lat, f.lon))
            if raggio is None or d <= raggio:
                righe.append({**f.json(), "distanza_m": round(d), "a_piedi_min": minuti_a_piedi(d),
                              "linee": self.linee_della_fermata(f.id)})
        righe.sort(key=lambda r: r["distanza_m"])
        return righe[:n]

    def linee_della_fermata(self, fermata_id: str) -> list[str]:
        return sorted({c.linea_id for c in self.corse.values() if fermata_id in c.fermate})

    def cerca(self, testo: str, n: int = 3) -> list[dict]:
        """Ricerca tollerante per nome ("plebiscito", "p.za martiri", "cimitero", "seven")."""
        q = normalizza(testo)
        qt = [w for w in q.split() if w not in _VUOTE] or q.split()
        if not qt:
            return []
        risultati = []
        for f in self.fermate.values():
            nome = normalizza(f.nome + " " + f.descrizione.split("–")[0])
            parole = nome.split()
            punteggio = 0.0
            for w in qt:
                if w in parole:
                    punteggio += 1.0
                else:
                    simile = difflib.get_close_matches(w, parole, n=1, cutoff=0.78)
                    if simile:
                        punteggio += 0.7
                    elif len(w) >= 4 and any(p.startswith(w) for p in parole):
                        punteggio += 0.6
            punteggio /= len(qt)
            if punteggio >= 0.5:
                risultati.append((punteggio, f))
        risultati.sort(key=lambda x: (-x[0], x[1].codice))
        return [{**f.json(), "punteggio": round(s, 2)} for s, f in risultati[:n]]

    # -------------------------------------------------------------- come arrivo
    def percorso(self, lat: float, lon: float, destinazioni: list[str], istante: datetime | None = None,
                 raggio: float = 1500, opzioni: int = 3) -> list[dict]:
        """Viaggi diretti (senza cambi): a piedi fino a una fermata vicina, bus, discesa a destinazione."""
        ora = (istante or self.adesso()).astimezone(self.fuso)
        partenze = self.vicine(lat, lon, n=6, raggio=raggio)
        dest = set(destinazioni)
        candidati = []
        for k in range(-1, 7):
            giorno = ora.date() + timedelta(days=k)
            mezzanotte = self._mezzanotte(giorno)
            for c in self.corse_del_giorno(giorno):
                for p in partenze:
                    if p["id"] in dest:
                        continue
                    for i, sid in enumerate(c.fermate[:-1]):
                        if sid != p["id"]:
                            continue
                        salita = mezzanotte + timedelta(seconds=c.partenze[i])
                        if salita < ora + timedelta(minutes=p["a_piedi_min"]):
                            continue
                        j = next((j for j in range(i + 1, len(c.fermate)) if c.fermate[j] in dest), None)
                        if j is None:
                            continue
                        discesa = mezzanotte + timedelta(seconds=c.arrivi[j])
                        candidati.append({
                            "linea": self.linee[c.linea_id].nome, "linea_id": c.linea_id,
                            "colore": f"#{self.linee[c.linea_id].colore}", "corsa_id": c.id,
                            "fermata_salita": p["nome"], "fermata_salita_id": p["id"],
                            "a_piedi_m": p["distanza_m"], "a_piedi_min": p["a_piedi_min"],
                            "esci_entro": (salita - timedelta(minutes=p["a_piedi_min"])).isoformat(timespec="minutes"),
                            "partenza": salita.isoformat(timespec="minutes"),
                            "fermata_discesa": self.fermate[c.fermate[j]].nome,
                            "fermata_discesa_id": c.fermate[j],
                            "arrivo": discesa.isoformat(timespec="minutes"),
                            "fermate_intermedie": j - i - 1,
                            "durata_min": int((discesa - ora).total_seconds() // 60),
                        })
            if len(candidati) >= opzioni and k >= 0:
                break
        candidati.sort(key=lambda x: (x["arrivo"], x["a_piedi_m"]))
        visti, out = set(), []
        for c in candidati:
            if c["corsa_id"] in visti:
                continue
            visti.add(c["corsa_id"])
            out.append(c)
        return out[:opzioni]

    # -------------------------------------------------------------- per l'interfaccia
    def orario_del_giorno(self, giorno: date) -> dict:
        """Tutto quello che serve al browser per animare i bus da solo per l'intera giornata."""
        corse = self.corse_del_giorno(giorno) + [
            c for c in self.corse_del_giorno(giorno - timedelta(days=1)) if c.arrivi[-1] > 86400]
        usati = {c.tracciato_id for c in corse}
        return {
            "giorno": giorno.isoformat(),
            "mezzanotte": self._mezzanotte(giorno).isoformat(),
            "corse": [c.json() for c in corse],
            "tracciati": [self.tracciati[t].json() for t in usati],
        }

    def prossima_corsa(self, istante: datetime | None = None) -> dict | None:
        ora = (istante or self.adesso()).astimezone(self.fuso)
        for k in range(0, 8):
            giorno = ora.date() + timedelta(days=k)
            mezzanotte = self._mezzanotte(giorno)
            for c in self.corse_del_giorno(giorno):
                inizio = mezzanotte + timedelta(seconds=c.partenze[0])
                if inizio > ora:
                    return {"corsa_id": c.id, "linea": self.linee[c.linea_id].nome,
                            "partenza": inizio.isoformat(timespec="minutes"),
                            "fermata": self.fermate[c.fermate[0]].nome}
        return None

    def info(self) -> dict:
        provv = sum(1 for f in self.fermate.values() if f.provvisoria)
        return {
            "agenzia": self.agenzia.get("agency_name", ""), "telefono": self.agenzia.get("agency_phone", ""),
            "sito": self.agenzia.get("agency_url", ""), "fuso": str(self.fuso),
            "versione_feed": self.info_feed.get("feed_version", ""),
            "validita": [self.info_feed.get("feed_start_date", ""), self.info_feed.get("feed_end_date", "")],
            "fermate": len(self.fermate), "fermate_provvisorie": provv,
            "linee": [l.json() for l in self.linee.values()], "corse": len(self.corse),
            "tracciati_stradali": any(len(t.punti) > len(t.fermate) for t in self.tracciati.values()),
            "tempo_reale": False,
        }
