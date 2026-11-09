"""Ricerca di luoghi per "come arrivo": prima le fermate, poi indirizzi e punti di interesse da OpenStreetMap.

La ricerca su OSM passa dal server (Nominatim o un'istanza dell'ente, `LUOGHI_GEOCODER`), limitata al territorio
servito: il browser non parla con terzi e al geocoder arriva solo il testo cercato, mai la posizione della persona.
Rispetta la policy di Nominatim: User-Agent identificativo, al massimo una richiesta al secondo, cache dei risultati.
"""
from __future__ import annotations

import logging
import threading
import time

import httpx

from .gtfs import Orario, normalizza

log = logging.getLogger("quandopassa.luoghi")
UA = "quandopassa/0.1 (+https://github.com/gzileni/quandopassa)"
MARGINE_GRADI = 0.03  # circa 3 km attorno alle fermate


class Luoghi:
    def __init__(self, orario: Orario, geocoder: str, comune: str, client: httpx.Client | None = None):
        self.orario, self.geocoder, self.comune = orario, geocoder.rstrip("/"), comune
        self._http = client or httpx.Client(timeout=6.0, headers={"User-Agent": UA, "Accept-Language": "it"})
        lat = [f.lat for f in orario.fermate.values()]
        lon = [f.lon for f in orario.fermate.values()]
        # ovest, nord, est, sud (formato viewbox di Nominatim)
        self.riquadro = (min(lon) - MARGINE_GRADI, max(lat) + MARGINE_GRADI,
                         max(lon) + MARGINE_GRADI, min(lat) - MARGINE_GRADI)
        self._cache: dict[str, list[dict]] = {}
        self._blocco = threading.Lock()
        self._ultima = 0.0

    def _dentro(self, lat: float, lon: float) -> bool:
        o, n, e, s = self.riquadro
        return s <= lat <= n and o <= lon <= e

    def cerca(self, testo: str, n: int = 8) -> list[dict]:
        fermate = [{"tipo": "fermata", "id": f["id"], "nome": f["nome"], "dettaglio": f"Fermata {f['codice']}",
                    "lat": f["lat"], "lon": f["lon"]} for f in self.orario.cerca(testo, n=4)]
        return (fermate + self._osm(testo))[:n]

    def _osm(self, testo: str) -> list[dict]:
        chiave = normalizza(testo)
        if not self.geocoder or len(chiave) < 3:
            return []
        if chiave in self._cache:
            return self._cache[chiave]
        o, n, e, s = self.riquadro
        with self._blocco:  # una richiesta al secondo, come chiede la policy di Nominatim
            attesa = 1.0 - (time.monotonic() - self._ultima)
            if attesa > 0:
                time.sleep(attesa)
            try:
                r = self._http.get(f"{self.geocoder}/search", params={
                    "q": f"{testo}, {self.comune}", "format": "jsonv2", "limit": 6, "countrycodes": "it",
                    "viewbox": f"{o},{n},{e},{s}", "bounded": 1, "addressdetails": 1})
                r.raise_for_status()
                righe = r.json()
            except Exception as ex:  # noqa: BLE001 - senza geocoder restano le fermate
                log.warning("geocoder non disponibile: %s", ex)
                return []
            finally:
                self._ultima = time.monotonic()
        out, visti = [], set()
        for x in righe:
            lat, lon = float(x["lat"]), float(x["lon"])
            if not self._dentro(lat, lon):
                continue
            a = x.get("address", {})
            nome = x.get("name") or " ".join(v for v in (a.get("road"), a.get("house_number")) if v) or testo
            dettaglio = ", ".join(v for v in (a.get("road") if x.get("name") else None, a.get("suburb"),
                                               a.get("town") or a.get("city") or a.get("village")) if v)
            if (nome, dettaglio) in visti:  # una strada spezzata in più tratti su OSM: basta una voce
                continue
            visti.add((nome, dettaglio))
            out.append({"tipo": "luogo", "nome": nome, "dettaglio": dettaglio, "lat": round(lat, 6), "lon": round(lon, 6)})
        if len(self._cache) > 500:
            self._cache.clear()
        self._cache[chiave] = out
        return out
