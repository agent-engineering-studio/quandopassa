"""Genera i file GTFS di una cartella a partire da fermate.csv e percorsi.json.

    python scripts/build_gtfs.py data

Input (nella cartella):
  fermate.csv     anagrafica delle fermate con coordinate (colonne lat/lon/fonte, vedi geocode_stops.py)
  percorsi.json   agenzia, calendari (con eccezioni), linee con sequenza fermate, minuti di percorrenza e partenze
  forme.json      (facoltativo) tracciati stradali per linea, prodotti da geocode_stops.py --forme

Output: agency.txt stops.txt routes.txt trips.txt stop_times.txt calendar.txt
        calendar_dates.txt feed_info.txt e, se c'è forme.json, shapes.txt.

Le fermate senza coordinate ricevono una posizione PROVVISORIA (su un anello attorno al centro)
così l'app resta utilizzabile; la colonna `posizione` lo dichiara e l'interfaccia lo mostra.

La logica è in api/quandopassa/sources.py, la stessa usata dalla pubblicazione del backoffice.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from quandopassa.sources import InvalidSources, build_gtfs  # noqa: E402

if __name__ == "__main__":
    dest = Path(sys.argv[1] if len(sys.argv) > 1 else "data")
    try:
        print(json.dumps(build_gtfs(dest), ensure_ascii=False))
    except InvalidSources as e:
        raise SystemExit(str(e)) from None
