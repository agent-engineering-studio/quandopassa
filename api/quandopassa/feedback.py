"""Recensioni dei cittadini su fermate, linee e servizio (stile "recensioni di Google Maps").

Due implementazioni con la stessa interfaccia:
  - Postgres: produzione (DATABASE_URL);
  - Memoria:  sviluppo e test (DATABASE_URL vuoto), i dati si perdono al riavvio.

Privacy by design: nessun account, nessun dato personale richiesto. Dal testo e dal nome
mostrato vengono rimossi email, telefoni e codici fiscali; dell'indirizzo IP si conserva
solo un'impronta giornaliera (hash con segreto + data) usata per il limite anti-spam.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Protocol

TIPI = ("fermata", "linea", "servizio")
TAG = {
    "fermata": ["pensilina", "seduta", "illuminata", "sicura", "accessibile", "orari esposti", "pulita",
                "senza riparo", "sporca", "pericolosa", "poco visibile"],
    "linea": ["puntuale", "frequente", "comoda", "bus pulito", "autista cortese", "in ritardo",
              "affollata", "frequenza bassa", "percorso lungo"],
    "servizio": ["utile", "economico", "puntuale", "facile da capire", "orari scomodi", "poche corse",
                 "informazioni scarse", "manca la domenica"],
}
MAX_ORA_PER_CLIENT = 5

_PII = [
    (re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b", re.I), "[codice fiscale rimosso]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email rimossa]"),
    (re.compile(r"(?:\+39\s?)?\b3\d{2}[\s.]?\d{6,7}\b|\b0\d{1,3}[\s.]?\d{5,8}\b"), "[telefono rimosso]"),
]


def redigi(testo: str) -> str:
    for rx, sost in _PII:
        testo = rx.sub(sost, testo)
    return testo


def impronta(ip: str, segreto: str, giorno: date | None = None) -> str:
    g = (giorno or date.today()).isoformat()
    return hashlib.sha256(f"{segreto}|{g}|{ip}".encode()).hexdigest()[:32]


class ErroreRecensione(ValueError):
    pass


@dataclass
class NuovaRecensione:
    tipo: str
    oggetto_id: str
    voto: int
    testo: str = ""
    tag: list[str] | None = None
    autore: str = ""

    def valida(self) -> "NuovaRecensione":
        if self.tipo not in TIPI:
            raise ErroreRecensione(f"tipo deve essere uno tra {', '.join(TIPI)}")
        if not isinstance(self.voto, int) or not 1 <= self.voto <= 5:
            raise ErroreRecensione("voto da 1 a 5")
        testo = redigi((self.testo or "").strip())[:1000]
        autore = redigi(re.sub(r"\s+", " ", (self.autore or "").strip()))[:40]
        tag = [t for t in dict.fromkeys(self.tag or []) if t in TAG[self.tipo]][:6]
        return NuovaRecensione(self.tipo, self.oggetto_id, self.voto, testo, tag, autore)


def _riepilogo(righe: list[dict]) -> dict:
    n = len(righe)
    distribuzione = {str(v): 0 for v in range(1, 6)}
    tag = Counter()
    for r in righe:
        distribuzione[str(r["voto"])] += 1
        tag.update(r["tag"])
    return {"conteggio": n, "media": round(sum(r["voto"] for r in righe) / n, 2) if n else None,
            "distribuzione": distribuzione, "tag": [{"tag": t, "conteggio": c} for t, c in tag.most_common(8)]}


class Archivio(Protocol):
    def aggiungi(self, rec: NuovaRecensione, client: str) -> dict: ...
    def elenco(self, tipo: str, oggetto_id: str, limite: int = 20, nascoste: bool = False) -> list[dict]: ...
    def riepilogo(self, tipo: str, oggetto_id: str) -> dict: ...
    def medie(self, tipo: str) -> dict[str, dict]: ...
    def nascondi(self, rec_id: str, nascosta: bool = True) -> bool: ...
    def recenti_del_client(self, client: str, dal: datetime) -> int: ...
    def ultime(self, limite: int = 50, nascoste: bool = True) -> list[dict]: ...


def _controlla_limiti(archivio: Archivio, client: str) -> None:
    if archivio.recenti_del_client(client, datetime.now(timezone.utc) - timedelta(hours=1)) >= MAX_ORA_PER_CLIENT:
        raise ErroreRecensione("Hai già lasciato diverse recensioni: riprova tra un'ora.")


# ------------------------------------------------------------------ memoria
class ArchivioMemoria:
    def __init__(self):
        self._righe: list[dict] = []

    def aggiungi(self, rec: NuovaRecensione, client: str) -> dict:
        rec = rec.valida()
        _controlla_limiti(self, client)
        riga = {"id": str(uuid.uuid4()), "tipo": rec.tipo, "oggetto_id": rec.oggetto_id, "voto": rec.voto,
                "testo": rec.testo, "tag": rec.tag, "autore": rec.autore, "nascosta": False,
                "creata_il": datetime.now(timezone.utc).isoformat(timespec="seconds"), "_client": client}
        self._righe.append(riga)
        return _pubblica(riga)

    def elenco(self, tipo, oggetto_id, limite=20, nascoste=False):
        r = [x for x in self._righe if x["tipo"] == tipo and x["oggetto_id"] == oggetto_id
             and (nascoste or not x["nascosta"])]
        return [_pubblica(x) for x in sorted(r, key=lambda x: x["creata_il"], reverse=True)[:limite]]

    def riepilogo(self, tipo, oggetto_id):
        return _riepilogo([x for x in self._righe if x["tipo"] == tipo and x["oggetto_id"] == oggetto_id
                           and not x["nascosta"]])

    def medie(self, tipo):
        gruppi: dict[str, list[dict]] = {}
        for x in self._righe:
            if x["tipo"] == tipo and not x["nascosta"]:
                gruppi.setdefault(x["oggetto_id"], []).append(x)
        return {k: {"media": _riepilogo(v)["media"], "conteggio": len(v)} for k, v in gruppi.items()}

    def nascondi(self, rec_id, nascosta=True):
        for x in self._righe:
            if x["id"] == rec_id:
                x["nascosta"] = nascosta
                return True
        return False

    def recenti_del_client(self, client, dal):
        return sum(1 for x in self._righe if x["_client"] == client and datetime.fromisoformat(x["creata_il"]) >= dal)

    def ultime(self, limite=50, nascoste=True):
        r = [x for x in self._righe if nascoste or not x["nascosta"]]
        return [_pubblica(x) for x in sorted(r, key=lambda x: x["creata_il"], reverse=True)[:limite]]


def _pubblica(r: dict) -> dict:
    out = {k: v for k, v in r.items() if not k.startswith("_") and k != "client_hash"}
    if isinstance(out.get("creata_il"), datetime):
        out["creata_il"] = out["creata_il"].isoformat(timespec="seconds")
    out["id"] = str(out["id"])
    out["tag"] = list(out.get("tag") or [])
    return out


# ------------------------------------------------------------------ PostgreSQL
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS recensioni (
    id           UUID PRIMARY KEY,
    tipo         TEXT NOT NULL CHECK (tipo IN ('fermata', 'linea', 'servizio')),
    oggetto_id   TEXT NOT NULL CHECK (length(oggetto_id) BETWEEN 1 AND 64),
    voto         SMALLINT NOT NULL CHECK (voto BETWEEN 1 AND 5),
    testo        TEXT NOT NULL DEFAULT '' CHECK (length(testo) <= 1000),
    tag          TEXT[] NOT NULL DEFAULT '{}',
    autore       TEXT NOT NULL DEFAULT '' CHECK (length(autore) <= 40),
    client_hash  TEXT NOT NULL,             -- impronta giornaliera dell'IP, solo anti-spam
    nascosta     BOOLEAN NOT NULL DEFAULT false,
    creata_il    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_recensioni_oggetto ON recensioni (tipo, oggetto_id, creata_il DESC);
CREATE INDEX IF NOT EXISTS ix_recensioni_client ON recensioni (client_hash, creata_il DESC);
"""


class ArchivioPostgres:
    def __init__(self, url: str, schema: str | None = None):
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        opzioni = f"-c search_path={schema}" if schema else None
        self.pool = ConnectionPool(url, min_size=1, max_size=5, open=True,
                                   kwargs={"row_factory": dict_row, "autocommit": True,
                                           **({"options": opzioni} if opzioni else {})})
        with self.pool.connection() as c:
            if schema:
                c.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            c.execute(SCHEMA_SQL)

    def chiudi(self):
        self.pool.close()

    def aggiungi(self, rec: NuovaRecensione, client: str) -> dict:
        rec = rec.valida()
        _controlla_limiti(self, client)
        with self.pool.connection() as c:
            riga = c.execute(
                "INSERT INTO recensioni (id, tipo, oggetto_id, voto, testo, tag, autore, client_hash) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                "RETURNING id, tipo, oggetto_id, voto, testo, tag, autore, nascosta, creata_il",
                (uuid.uuid4(), rec.tipo, rec.oggetto_id, rec.voto, rec.testo, rec.tag, rec.autore, client),
            ).fetchone()
        return _pubblica(riga)

    def elenco(self, tipo, oggetto_id, limite=20, nascoste=False):
        with self.pool.connection() as c:
            righe = c.execute(
                "SELECT id, tipo, oggetto_id, voto, testo, tag, autore, nascosta, creata_il FROM recensioni "
                "WHERE tipo=%s AND oggetto_id=%s AND (%s OR NOT nascosta) ORDER BY creata_il DESC LIMIT %s",
                (tipo, oggetto_id, nascoste, limite)).fetchall()
        return [_pubblica(r) for r in righe]

    def riepilogo(self, tipo, oggetto_id):
        with self.pool.connection() as c:
            righe = c.execute("SELECT voto, tag FROM recensioni WHERE tipo=%s AND oggetto_id=%s AND NOT nascosta",
                              (tipo, oggetto_id)).fetchall()
        return _riepilogo([{"voto": r["voto"], "tag": r["tag"] or []} for r in righe])

    def medie(self, tipo):
        with self.pool.connection() as c:
            righe = c.execute("SELECT oggetto_id, round(avg(voto)::numeric, 2) AS media, count(*) AS n "
                              "FROM recensioni WHERE tipo=%s AND NOT nascosta GROUP BY oggetto_id", (tipo,)).fetchall()
        return {r["oggetto_id"]: {"media": float(r["media"]), "conteggio": r["n"]} for r in righe}

    def nascondi(self, rec_id, nascosta=True):
        try:
            uuid.UUID(rec_id)
        except ValueError:
            return False
        with self.pool.connection() as c:
            return c.execute("UPDATE recensioni SET nascosta=%s WHERE id=%s", (nascosta, rec_id)).rowcount == 1

    def recenti_del_client(self, client, dal):
        with self.pool.connection() as c:
            return c.execute("SELECT count(*) AS n FROM recensioni WHERE client_hash=%s AND creata_il >= %s",
                             (client, dal)).fetchone()["n"]

    def ultime(self, limite=50, nascoste=True):
        with self.pool.connection() as c:
            righe = c.execute(
                "SELECT id, tipo, oggetto_id, voto, testo, tag, autore, nascosta, creata_il FROM recensioni "
                "WHERE %s OR NOT nascosta ORDER BY creata_il DESC LIMIT %s", (nascoste, limite)).fetchall()
        return [_pubblica(r) for r in righe]


def crea_archivio(url: str | None, schema: str | None = None) -> Archivio:
    return ArchivioPostgres(url, schema) if url else ArchivioMemoria()
