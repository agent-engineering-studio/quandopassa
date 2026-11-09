"""Configurazione da variabili d'ambiente (file .env letto da docker compose)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]


def _env(nome: str, predefinito: str = "") -> str:
    return os.getenv(nome, predefinito).strip()


def _cartella(nome: str, predefinito: str) -> Path:
    """Percorsi relativi (es. GTFS_DIR=./data/gtfs/resta nel .env) sono relativi alla radice del repository."""
    p = Path(_env(nome, predefinito))
    return p if p.is_absolute() else (RADICE / p).resolve()


@dataclass(frozen=True)
class Config:
    gtfs_dir: Path = field(default_factory=lambda: _cartella("GTFS_DIR", "data/gtfs/resta"))
    fuso: str = field(default_factory=lambda: _env("TZ_SERVIZIO", "Europe/Rome"))
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL"))
    database_schema: str = field(default_factory=lambda: _env("DATABASE_SCHEMA"))
    inference_url: str = field(default_factory=lambda: _env("INFERENCE_URL"))
    secret_key: str = field(default_factory=lambda: _env("SECRET_KEY", "sviluppo-non-usare-in-produzione"))
    ufficio_user: str = field(default_factory=lambda: _env("UFFICIO_USER"))
    ufficio_password: str = field(default_factory=lambda: _env("UFFICIO_PASSWORD"))
    base_url: str = field(default_factory=lambda: _env("BASE_URL", "http://localhost:8000").rstrip("/"))
    comune: str = field(default_factory=lambda: _env("COMUNE_NOME", "Comune di Gioia del Colle"))
    servizio: str = field(default_factory=lambda: _env("SERVIZIO_NOME", "Bus urbano di Gioia del Colle"))
    centro: tuple[float, float] = field(default_factory=lambda: tuple(  # type: ignore[assignment]
        float(x) for x in _env("MAPPA_CENTRO", "40.7990,16.9230").split(",")))
    biglietti: str = field(default_factory=lambda: _env(
        "INFO_BIGLIETTI", "Tariffe e punti vendita dei biglietti: chiedere all'azienda di trasporto o all'Ufficio "
                          "Trasporti del Comune."))
    mappa_tiles: str = field(default_factory=lambda: _env(
        "MAPPA_TILES", "https://tile.openstreetmap.org/{z}/{x}/{y}.png"))
    mappa_attribuzione: str = field(default_factory=lambda: _env(
        "MAPPA_ATTRIBUZIONE", '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'))
    demo_ora: str = field(default_factory=lambda: _env("DEMO_ORA"))
    web_dist: Path = field(default_factory=lambda: _cartella("WEB_DIST", "web/dist"))
