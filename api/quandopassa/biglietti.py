"""Biglietteria del prototipo: titoli di viaggio digitali con tariffe dal file .env.

Titoli: corsa singola (vale N minuti dall'attivazione), carnet (N corse, ognuna da attivare alla salita) e
abbonamento (N giorni dall'acquisto). L'acquisto è anonimo: il telefono riceve una chiave segreta e il server ne
conserva solo l'impronta, quindi nessun account e nessun dato personale. Ogni attivazione produce un codice
breve da mostrare e un QR firmato (HMAC) che il controllore verifica da /verifica.

L'archivio è SQLite (un file su volume Docker, oppure in memoria per test e demo): le tabelle sono semplici e
passano a PostgreSQL senza cambiamenti se il servizio cresce.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable

from .config import Config
from .pagamenti import Pagamenti, PagamentoSimulato

ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # niente 0/O/1/I: si legge e si detta senza errori
SCHEMA = """
CREATE TABLE IF NOT EXISTS acquisti (
  id TEXT PRIMARY KEY, tipo TEXT NOT NULL, importo_cent INTEGER NOT NULL, stato TEXT NOT NULL,
  riferimento TEXT NOT NULL, chiave_hash TEXT NOT NULL, creato TEXT NOT NULL, pagato TEXT);
CREATE TABLE IF NOT EXISTS titoli (
  id TEXT PRIMARY KEY, acquisto_id TEXT NOT NULL UNIQUE REFERENCES acquisti(id), tipo TEXT NOT NULL,
  chiave_hash TEXT NOT NULL, corse_totali INTEGER, corse_usate INTEGER NOT NULL DEFAULT 0,
  valido_dal TEXT NOT NULL, valido_al TEXT, creato TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS titoli_chiave ON titoli(chiave_hash);
CREATE TABLE IF NOT EXISTS attivazioni (
  id TEXT PRIMARY KEY, titolo_id TEXT NOT NULL REFERENCES titoli(id), codice TEXT NOT NULL UNIQUE,
  attivata TEXT NOT NULL, scade TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS attivazioni_titolo ON attivazioni(titolo_id);
CREATE TABLE IF NOT EXISTS verifiche (
  id INTEGER PRIMARY KEY AUTOINCREMENT, codice TEXT NOT NULL, esito TEXT NOT NULL, quando TEXT NOT NULL);
"""


class ErroreBiglietto(Exception):
    def __init__(self, messaggio: str, status: int = 422):
        super().__init__(messaggio)
        self.status = status


@dataclass(frozen=True)
class Tariffa:
    tipo: str
    nome: str
    importo_cent: int
    corse: int | None = None
    validita_min: int | None = None
    giorni: int | None = None

    def descrizione(self) -> str:
        if self.tipo == "corsa":
            return f"Una corsa su tutte le linee, valida {self.validita_min} minuti dall'attivazione"
        if self.tipo == "carnet":
            return f"{self.corse} corse da attivare una alla volta, ognuna valida {self.validita_min} minuti"
        return f"Corse illimitate su tutte le linee per {self.giorni} giorni dall'acquisto"

    def json(self) -> dict:
        return {"tipo": self.tipo, "nome": self.nome, "importo_cent": self.importo_cent, "corse": self.corse,
                "validita_min": self.validita_min, "giorni": self.giorni, "descrizione": self.descrizione()}


def _cent(valore: str) -> int:
    return int((Decimal(valore.replace(",", ".")) * 100).to_integral_value())


def tariffe(cfg: Config) -> dict[str, Tariffa]:
    return {
        "corsa": Tariffa("corsa", "Corsa singola", _cent(cfg.tariffa_corsa), 1, cfg.validita_corsa_min),
        "carnet": Tariffa("carnet", f"Carnet {cfg.corse_carnet} corse", _cent(cfg.tariffa_carnet), cfg.corse_carnet,
                          cfg.validita_corsa_min),
        "abbonamento": Tariffa("abbonamento", f"Abbonamento {cfg.giorni_abbonamento} giorni",
                               _cent(cfg.tariffa_abbonamento), giorni=cfg.giorni_abbonamento),
    }


def _impronta(chiave: str) -> str:
    return hashlib.sha256(chiave.encode()).hexdigest()


class Biglietteria:
    def __init__(self, cfg: Config, pagamenti: Pagamenti, adesso: Callable[[], datetime]):
        self.cfg, self.pagamenti, self.adesso = cfg, pagamenti, adesso
        self.tariffe = tariffe(cfg)
        self._segreto = cfg.biglietti_segreto.encode()
        self._db = sqlite3.connect(cfg.biglietti_db, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        if cfg.biglietti_db != ":memory:":
            self._db.execute("PRAGMA journal_mode = WAL")
        self._db.executescript(SCHEMA)
        self._blocco = threading.Lock()

    # ------------------------------------------------------------------ acquisto
    def acquista(self, tipo: str) -> dict:
        t = self.tariffe.get(tipo)
        if t is None:
            raise ErroreBiglietto(f"Titolo sconosciuto: {tipo}")
        acquisto_id, chiave = secrets.token_hex(8), secrets.token_urlsafe(24)
        causale = f"QuandoPassa - {t.nome}"
        richiesta = self.pagamenti.crea(acquisto_id, t.importo_cent, causale)
        with self._blocco:
            self._db.execute("INSERT INTO acquisti VALUES (?,?,?,?,?,?,?,NULL)",
                             (acquisto_id, tipo, t.importo_cent, "in_attesa", richiesta.riferimento, _impronta(chiave),
                              self.adesso().isoformat()))
        return {"acquisto_id": acquisto_id, "chiave": chiave, "tipo": tipo, "nome": t.nome,
                "importo_cent": t.importo_cent, "causale": causale, "riferimento": richiesta.riferimento,
                "url_pagamento": richiesta.url, "simulato": richiesta.simulato}

    def esito_simulato(self, acquisto_id: str, chiave: str, pagato: bool) -> None:
        if not isinstance(self.pagamenti, PagamentoSimulato):
            raise ErroreBiglietto("Pagamento simulato non attivo", 404)
        a = self._acquisto(acquisto_id, chiave)
        self.pagamenti.esito(a["riferimento"], pagato)
        if not pagato:
            with self._blocco:
                self._db.execute("UPDATE acquisti SET stato='annullato' WHERE id=? AND stato='in_attesa'", (acquisto_id,))

    def conferma(self, acquisto_id: str, chiave: str) -> dict:
        """Emette il titolo quando il pagamento risulta riuscito. Idempotente: richiamarla restituisce lo stesso titolo."""
        a = self._acquisto(acquisto_id, chiave)
        with self._blocco:
            esistente = self._db.execute("SELECT * FROM titoli WHERE acquisto_id=?", (acquisto_id,)).fetchone()
            if esistente:
                return self._vista(esistente)
            if a["stato"] == "annullato":
                raise ErroreBiglietto("Pagamento annullato: nessun biglietto emesso", 409)
            if not self.pagamenti.pagato(a["riferimento"]):
                raise ErroreBiglietto("Pagamento non ancora riuscito", 409)
            ora = self.adesso()
            t = self.tariffe[a["tipo"]]
            valido_al = (ora + timedelta(days=t.giorni)).isoformat() if t.giorni else None
            titolo_id = secrets.token_hex(8)
            self._db.execute("UPDATE acquisti SET stato='pagato', pagato=? WHERE id=?", (ora.isoformat(), acquisto_id))
            self._db.execute("INSERT INTO titoli VALUES (?,?,?,?,?,0,?,?,?)",
                             (titolo_id, acquisto_id, a["tipo"], a["chiave_hash"], t.corse, ora.isoformat(), valido_al,
                              ora.isoformat()))
            return self._vista(self._db.execute("SELECT * FROM titoli WHERE id=?", (titolo_id,)).fetchone())

    def _acquisto(self, acquisto_id: str, chiave: str) -> sqlite3.Row:
        a = self._db.execute("SELECT * FROM acquisti WHERE id=?", (acquisto_id,)).fetchone()
        if a is None or not hmac.compare_digest(a["chiave_hash"], _impronta(chiave)):
            raise ErroreBiglietto("Acquisto non trovato", 404)
        return a

    # ------------------------------------------------------------------ portafoglio e attivazione
    def portafoglio(self, chiavi: list[str]) -> list[dict]:
        impronte = [_impronta(c) for c in chiavi[:50]]
        if not impronte:
            return []
        segnaposti = ",".join("?" * len(impronte))  # solo "?": i valori passano come parametri
        righe = self._db.execute(f"SELECT * FROM titoli WHERE chiave_hash IN ({segnaposti}) "  # nosec B608
                                 "ORDER BY creato DESC", impronte).fetchall()
        return [self._vista(r) for r in righe]

    def attiva(self, titolo_id: str, chiave: str) -> dict:
        with self._blocco:
            r = self._db.execute("SELECT * FROM titoli WHERE id=?", (titolo_id,)).fetchone()
            if r is None or not hmac.compare_digest(r["chiave_hash"], _impronta(chiave)):
                raise ErroreBiglietto("Biglietto non trovato", 404)
            ora = self.adesso()
            if self._attivazione_corrente(titolo_id, ora):
                return self._vista(r)  # già attivo: non si consuma un'altra corsa
            t = self.tariffe[r["tipo"]]
            if r["valido_al"]:
                if ora >= datetime.fromisoformat(r["valido_al"]):
                    raise ErroreBiglietto("Abbonamento scaduto", 409)
                scade = datetime.fromisoformat(r["valido_al"])
            else:
                if r["corse_usate"] >= r["corse_totali"]:
                    raise ErroreBiglietto("Corse esaurite", 409)
                scade = ora + timedelta(minutes=t.validita_min or 60)
                self._db.execute("UPDATE titoli SET corse_usate = corse_usate + 1 WHERE id=?", (titolo_id,))
            while True:
                codice = "".join(secrets.choice(ALFABETO) for _ in range(6))
                if not self._db.execute("SELECT 1 FROM attivazioni WHERE codice=?", (codice,)).fetchone():
                    break
            self._db.execute("INSERT INTO attivazioni VALUES (?,?,?,?,?)",
                             (secrets.token_hex(8), titolo_id, codice, ora.isoformat(), scade.isoformat()))
            return self._vista(self._db.execute("SELECT * FROM titoli WHERE id=?", (titolo_id,)).fetchone())

    def _attivazione_corrente(self, titolo_id: str, ora: datetime) -> sqlite3.Row | None:
        a = self._db.execute("SELECT * FROM attivazioni WHERE titolo_id=? ORDER BY attivata DESC LIMIT 1",
                             (titolo_id,)).fetchone()
        return a if a and datetime.fromisoformat(a["scade"]) > ora else None

    def _firma(self, attivazione_id: str) -> str:
        return hmac.new(self._segreto, attivazione_id.encode(), hashlib.sha256).hexdigest()[:20]

    def _vista(self, r: sqlite3.Row) -> dict:
        ora = self.adesso()
        t = self.tariffe[r["tipo"]]
        a = self._attivazione_corrente(r["id"], ora)
        rimaste = None if r["corse_totali"] is None else r["corse_totali"] - r["corse_usate"]
        if a:
            stato = "attivo"
        elif r["valido_al"] and ora >= datetime.fromisoformat(r["valido_al"]):
            stato = "scaduto"
        elif rimaste == 0:
            stato = "esaurito"
        else:
            stato = "pronto"
        out = {"id": r["id"], "tipo": r["tipo"], "nome": t.nome, "stato": stato, "corse_totali": r["corse_totali"],
               "corse_rimaste": rimaste, "valido_dal": r["valido_dal"], "valido_al": r["valido_al"],
               "validita_min": t.validita_min, "attivazione": None}
        if a:
            out["attivazione"] = {"codice": a["codice"], "attivata": a["attivata"], "scade": a["scade"],
                                  "qr": f"QP1.{a['id']}.{self._firma(a['id'])}"}
        return out

    # ------------------------------------------------------------------ verifica a bordo
    def verifica(self, dato: str) -> dict:
        """Esito per il controllore, da QR (QP1.<id>.<firma>) o dal codice di 6 caratteri."""
        dato = dato.strip()
        ora = self.adesso()
        if dato.startswith("QP1."):
            parti = dato.split(".")
            if len(parti) != 3 or not hmac.compare_digest(parti[2], self._firma(parti[1])):
                return self._esito(dato[:40], "non_valido", "QR non valido o contraffatto", ora)
            a = self._db.execute("SELECT * FROM attivazioni WHERE id=?", (parti[1],)).fetchone()
        else:
            codice = "".join(c for c in dato.upper() if c.isalnum())
            a = self._db.execute("SELECT * FROM attivazioni WHERE codice=?", (codice,)).fetchone()
        if a is None:
            return self._esito(dato[:40], "non_valido", "Biglietto inesistente", ora)
        titolo = self._db.execute("SELECT tipo FROM titoli WHERE id=?", (a["titolo_id"],)).fetchone()
        scade = datetime.fromisoformat(a["scade"])
        base = {"codice": a["codice"], "titolo": self.tariffe[titolo["tipo"]].nome, "attivata": a["attivata"],
                "scade": a["scade"]}
        if scade <= ora:
            return {**self._esito(a["codice"], "scaduto", f"Scaduto alle {scade.strftime('%H:%M')}", ora), **base}
        return {**self._esito(a["codice"], "valido", f"Valido fino alle {scade.strftime('%H:%M')}", ora), **base}

    def _esito(self, codice: str, esito: str, messaggio: str, ora: datetime) -> dict:
        with self._blocco:
            self._db.execute("INSERT INTO verifiche (codice, esito, quando) VALUES (?,?,?)", (codice, esito, ora.isoformat()))
        return {"esito": esito, "messaggio": messaggio, "verificato": ora.isoformat(timespec="seconds")}
