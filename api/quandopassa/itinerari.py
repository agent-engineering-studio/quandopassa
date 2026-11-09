"""Itinerari porta a porta, come su un navigatore: a piedi, bus (diretto o con un cambio), a piedi.

Tutto viene dall'orario GTFS: orari di salita e discesa, attese al cambio e tratti di percorso lungo il tracciato
stradale. I tratti a piedi sono stimati in linea d'aria corretta per la tortuosità delle strade.
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta

from .gtfs import Corsa, Orario, Tracciato, metri, minuti_a_piedi

RAGGIO_PIEDI = 1000          # metri massimi a piedi per raggiungere o lasciare una fermata
FERMATE_CANDIDATE = 6        # fermate di salita/discesa considerate attorno a origine e destinazione
CAMBIO_MIN_S = 60            # tempo minimo per cambiare bus alla stessa fermata
ATTESA_MAX_CAMBIO_S = 3600   # oltre un'ora di attesa il cambio non è una soluzione sensata
SOLO_PIEDI_MAX_MIN = 30      # oltre questa durata "solo a piedi" si propone solo se arriva prima del bus
SOLO_PIEDI_SOTTO_M = 600     # più vicino di così il bus non serve
PIEDI_TRASCURABILI_M = 25    # tratti a piedi più corti non si mostrano (sei già alla fermata)
GIORNI_AVANTI = 3            # quanti giorni avanti cercare (la domenica non circola)


@dataclass
class _Passaggio:
    """Un bus che parte da una fermata a un istante preciso (indice nella sequenza della corsa)."""
    partenza: datetime
    mezzanotte: datetime
    corsa: Corsa
    indice: int


def _iso(d: datetime) -> str:
    return d.isoformat(timespec="minutes")


def _punto(nome: str, lat: float, lon: float, fid: str | None = None) -> dict:
    out = {"nome": nome, "lat": round(lat, 6), "lon": round(lon, 6)}
    if fid:
        out["id"] = fid
    return out


def _tratto_tracciato(tr: Tracciato, i: int, j: int) -> list[list[float]]:
    """Punti del tracciato stradale tra la fermata i e la fermata j della sequenza."""
    da, a = tr.distanze_fermate[i], tr.distanze_fermate[j]
    (p0, _), (p1, _) = tr.punto_a(da), tr.punto_a(a)
    k0, k1 = bisect_left(tr.progressive, da), bisect_left(tr.progressive, a)
    punti = [p0, *tr.punti[k0:k1], p1]
    return [[round(p[0], 6), round(p[1], 6)] for p in punti]


class Pianificatore:
    def __init__(self, orario: Orario):
        self.orario = orario

    # ------------------------------------------------------------------ indice dei passaggi
    def _passaggi(self, ora: datetime) -> dict[str, list[_Passaggio]]:
        """Per ogni fermata, i bus in partenza da `ora` in poi, in ordine di tempo."""
        per_fermata: dict[str, list[_Passaggio]] = {}
        for k in range(-1, GIORNI_AVANTI + 1):
            giorno = ora.date() + timedelta(days=k)
            mezzanotte = self.orario._mezzanotte(giorno)
            for c in self.orario.corse_del_giorno(giorno):
                for i, sid in enumerate(c.fermate[:-1]):
                    t = mezzanotte + timedelta(seconds=c.partenze[i])
                    if t >= ora:
                        per_fermata.setdefault(sid, []).append(_Passaggio(t, mezzanotte, c, i))
        for v in per_fermata.values():
            v.sort(key=lambda p: p.partenza)
        return per_fermata

    def _attorno(self, lat: float, lon: float) -> dict[str, tuple[float, int]]:
        righe = self.orario.vicine(lat, lon, n=FERMATE_CANDIDATE, raggio=RAGGIO_PIEDI)
        return {r["id"]: (r["distanza_m"], r["a_piedi_min"]) for r in righe}

    # ------------------------------------------------------------------ ricerca
    def pianifica(self, origine: tuple[float, float], destinazione: tuple[float, float],
                  istante: datetime | None = None, opzioni: int = 3,
                  nome_origine: str = "Partenza", nome_destinazione: str = "Destinazione") -> dict:
        ora = (istante or self.orario.adesso()).astimezone(self.orario.fuso).replace(second=0, microsecond=0)
        diretta = metri(origine, destinazione)
        o, d = _punto(nome_origine, *origine), _punto(nome_destinazione, *destinazione)
        salite, discese = self._attorno(*origine), self._attorno(*destinazione)
        passaggi = self._passaggi(ora)

        candidati: list[dict] = []
        if diretta <= SOLO_PIEDI_SOTTO_M:
            salite = {}
        for sid, (m_o, min_o) in salite.items():
            pronto = ora + timedelta(minutes=min_o)
            for p in passaggi.get(sid, []):
                if p.partenza < pronto:
                    continue
                c, i = p.corsa, p.indice
                j = self._discesa(p, discese)
                if j is not None:
                    candidati.append(self._itinerario(o, d, ora, [(p, j)], m_o, min_o, discese[c.fermate[j]]))
                for k in range(i + 1, len(c.fermate)):
                    s2 = c.fermate[k]
                    if s2 in discese or s2 in salite:
                        continue  # vicino alla meta si scende, vicino alla partenza si poteva salire qui
                    arrivo_bus = p.mezzanotte + timedelta(seconds=c.arrivi[k])
                    for p2 in self._coincidenze(passaggi.get(s2, []), arrivo_bus, c):
                        n = self._discesa(p2, discese)
                        if n is not None:
                            candidati.append(self._itinerario(o, d, ora, [(p, k), (p2, n)], m_o, min_o,
                                                              discese[p2.corsa.fermate[n]]))
                if candidati and p.partenza > pronto + timedelta(hours=3):
                    break  # le corse ancora più tarde non arrivano prima di quelle già trovate

        piedi = self._solo_piedi(o, d, ora, diretta)
        return {"ora": _iso(ora), "origine": o, "destinazione": d,
                "opzioni": self._scegli(candidati, piedi, opzioni),
                "avviso": "Orari dall'orario programmato (nessun GPS): verifica sempre alla fermata."}

    @staticmethod
    def _discesa(p: _Passaggio, discese: dict[str, tuple[float, int]]) -> int | None:
        """La fermata della corsa da cui si arriva prima a destinazione, contando il tratto finale a piedi."""
        c = p.corsa
        utili = [n for n in range(p.indice + 1, len(c.fermate)) if c.fermate[n] in discese]
        return min(utili, key=lambda n: c.arrivi[n] + 60 * discese[c.fermate[n]][1], default=None)

    @staticmethod
    def _coincidenze(elenco: list[_Passaggio], arrivo: datetime, corsa: Corsa, quante: int = 3) -> list[_Passaggio]:
        out, linee = [], set()
        for p in elenco:
            if p.partenza < arrivo + timedelta(seconds=CAMBIO_MIN_S) or p.corsa.id == corsa.id:
                continue
            if p.partenza > arrivo + timedelta(seconds=ATTESA_MAX_CAMBIO_S) or len(out) >= quante:
                break
            if p.corsa.linea_id in linee:
                continue
            linee.add(p.corsa.linea_id)
            out.append(p)
        return out

    # ------------------------------------------------------------------ costruzione
    def _itinerario(self, o: dict, d: dict, ora: datetime, corse: list[tuple[_Passaggio, int]],
                    m_o: float, min_o: int, fine: tuple[float, int]) -> dict:
        orario = self.orario
        tratti: list[dict] = []
        prima = corse[0][0]
        f0 = orario.fermate[prima.corsa.fermate[prima.indice]]
        uscita = prima.partenza - timedelta(minutes=min_o)
        if m_o <= PIEDI_TRASCURABILI_M:
            uscita = prima.partenza
        else:
            tratti.append({"tipo": "piedi", "da": o, "a": _punto(f0.nome, f0.lat, f0.lon, f0.id), "metri": round(m_o),
                           "minuti": min_o, "partenza": _iso(uscita), "arrivo": _iso(uscita + timedelta(minutes=min_o)),
                           "punti": [[o["lat"], o["lon"]], [f0.lat, f0.lon]]})
        precedente: datetime | None = None
        for p, j in corse:
            c, i = p.corsa, p.indice
            linea = orario.linee[c.linea_id]
            fs, fd = orario.fermate[c.fermate[i]], orario.fermate[c.fermate[j]]
            arrivo = p.mezzanotte + timedelta(seconds=c.arrivi[j])
            attesa = 0 if precedente is None else int((p.partenza - precedente).total_seconds() // 60)
            tratti.append({
                "tipo": "bus", "linea": linea.nome, "linea_id": c.linea_id, "nome_linea": linea.nome_esteso,
                "colore": f"#{linea.colore}", "corsa_id": c.id, "destinazione": c.destinazione,
                "salita": {**_punto(fs.nome, fs.lat, fs.lon, fs.id), "orario": _iso(p.partenza)},
                "discesa": {**_punto(fd.nome, fd.lat, fd.lon, fd.id), "orario": _iso(arrivo)},
                "fermate_intermedie": j - i - 1, "minuti": int((arrivo - p.partenza).total_seconds() // 60),
                "attesa_min": attesa, "punti": _tratto_tracciato(orario.tracciati[c.tracciato_id], i, j),
            })
            precedente = arrivo
        ultima = orario.fermate[corse[-1][0].corsa.fermate[corse[-1][1]]]
        m_d, min_d = fine
        arrivo_finale = precedente + timedelta(minutes=min_d if m_d > PIEDI_TRASCURABILI_M else 0)
        if m_d > PIEDI_TRASCURABILI_M:
            tratti.append({"tipo": "piedi", "da": _punto(ultima.nome, ultima.lat, ultima.lon, ultima.id), "a": d,
                           "metri": round(m_d), "minuti": min_d, "partenza": _iso(precedente),
                           "arrivo": _iso(arrivo_finale), "punti": [[ultima.lat, ultima.lon], [d["lat"], d["lon"]]]})
        a_piedi_m = round(sum(t["metri"] for t in tratti if t["tipo"] == "piedi"))
        return {
            "partenza": _iso(uscita), "arrivo": _iso(arrivo_finale),
            "durata_min": int((arrivo_finale - uscita).total_seconds() // 60),
            "attesa_iniziale_min": int((uscita - ora).total_seconds() // 60),
            "cambi": len(corse) - 1, "a_piedi_m": a_piedi_m, "a_piedi_min": minuti_a_piedi(a_piedi_m) if a_piedi_m else 0,
            "linee": [t["linea"] for t in tratti if t["tipo"] == "bus"], "tratti": tratti,
        }

    @staticmethod
    def _solo_piedi(o: dict, d: dict, ora: datetime, diretta: float) -> dict:
        minuti = minuti_a_piedi(diretta)
        return {"partenza": _iso(ora), "arrivo": _iso(ora + timedelta(minutes=minuti)), "durata_min": minuti,
                "attesa_iniziale_min": 0, "cambi": 0, "a_piedi_m": round(diretta), "a_piedi_min": minuti, "linee": [],
                "tratti": [{"tipo": "piedi", "da": o, "a": d, "metri": round(diretta), "minuti": minuti,
                            "partenza": _iso(ora), "arrivo": _iso(ora + timedelta(minutes=minuti)),
                            "punti": [[o["lat"], o["lon"]], [d["lat"], d["lon"]]]}]}

    @staticmethod
    def _scegli(candidati: list[dict], piedi: dict, quante: int) -> list[dict]:
        """Prima chi arriva prima, poi meno cambi e meno strada a piedi; una soluzione per corsa di partenza."""
        candidati.sort(key=lambda x: (x["arrivo"], x["cambi"], x["a_piedi_m"]))
        out, viste = [], set()
        for c in candidati:
            chiave = next(t["corsa_id"] for t in c["tratti"] if t["tipo"] == "bus")
            if chiave in viste:
                continue
            # scartata se un'altra soluzione esce non prima e arriva non dopo, con meno o uguali cambi
            if any(x["partenza"] >= c["partenza"] and x["arrivo"] <= c["arrivo"] and x["cambi"] <= c["cambi"]
                   for x in out):
                continue
            viste.add(chiave)
            out.append(c)
            if len(out) >= quante:
                break
        if not out or piedi["arrivo"] <= out[0]["arrivo"]:
            out.insert(0, piedi)          # a piedi si arriva prima: è la prima proposta
        elif piedi["durata_min"] <= SOLO_PIEDI_MAX_MIN:
            out.append(piedi)
        return out[: quante + 1]
