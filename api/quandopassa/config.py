"""Configurazione da variabili d'ambiente (file .env letto da docker compose)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]


def _env(nome: str, predefinito: str = "") -> str:
    return os.getenv(nome, predefinito).strip()


def _cartella(nome: str, predefinito: str) -> Path:
    """Percorsi relativi (es. GTFS_DIR=./data nel .env) sono relativi alla radice del repository."""
    p = Path(_env(nome, predefinito))
    return p if p.is_absolute() else (RADICE / p).resolve()


@dataclass(frozen=True)
class Config:
    gtfs_dir: Path = field(default_factory=lambda: _cartella("GTFS_DIR", "data"))
    fuso: str = field(default_factory=lambda: _env("TZ_SERVIZIO", "Europe/Rome"))
    inference_url: str = field(default_factory=lambda: _env("INFERENCE_URL"))
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
    # ricerca di indirizzi e luoghi per "come arrivo" (Nominatim o istanza dell'ente; vuoto = solo fermate)
    geocoder: str = field(default_factory=lambda: _env("LUOGHI_GEOCODER", "https://nominatim.openstreetmap.org"))
    # biglietti: QuandoPassa non li vende; rimanda al sistema di acquisto online dell'azienda di trasporto
    link_biglietti: str = field(default_factory=lambda: _env("LINK_BIGLIETTI"))
    biglietteria_nome: str = field(default_factory=lambda: _env("BIGLIETTERIA_NOME"))
    demo_ora: str = field(default_factory=lambda: _env("DEMO_ORA"))
    web_dist: Path = field(default_factory=lambda: _cartella("WEB_DIST", "web/dist"))
    # intestazione dell'app (anche dal backoffice): titolo, sito dell'ente, testo alternativo del logo
    app_title: str = field(default_factory=lambda: _env("APP_TITLE", "QuandoPassa"))
    entity_url: str = field(default_factory=lambda: _env("ENTITY_URL"))
    logo_alt: str = field(default_factory=lambda: _env("LOGO_ALT"))
    # backoffice: cartella dati scrivibile (feed generato e impostazioni), database e credenziali
    data_dir: Path | None = field(default_factory=lambda: _cartella("DATA_DIR", "") if _env("DATA_DIR") else None)
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL"))
    admin_user: str = field(default_factory=lambda: _env("ADMIN_USER"))
    admin_password_hash: str = field(default_factory=lambda: _env("ADMIN_PASSWORD_HASH"))
    admin_secret: str = field(default_factory=lambda: _env("ADMIN_SECRET"))
    # tracciati stradali calcolati dal backoffice (vuoto = funzione disattivata)
    osrm_url: str = field(default_factory=lambda: _env("OSRM_URL", "https://router.project-osrm.org/route/v1/driving"))

    @property
    def admin_enabled(self) -> bool:
        return bool(self.data_dir and self.database_url and self.admin_user and self.admin_password_hash)


# Impostazioni modificabili dal backoffice: campo di Config -> (variabile del .env, etichetta, aiuto).
# Il resto (credenziali, cartelle, indirizzi interni, IA) si cambia solo nel .env.
EDITABLE_SETTINGS = {
    "comune": ("COMUNE_NOME", "Nome dell'ente", "In alto a sinistra nell'intestazione, es. «Comune di Gioia del Colle»."),
    "entity_url": ("ENTITY_URL", "Sito dell'ente", "Collegamento del nome dell'ente nell'intestazione; vuoto = sito "
                   "dell'azienda di trasporto."),
    "app_title": ("APP_TITLE", "Titolo dell'app", "Accanto al logo, es. «QuandoPassa» o «Bus urbano»."),
    "servizio": ("SERVIZIO_NOME", "Sottotitolo", "Sotto il titolo, es. «Bus urbano di Gioia del Colle»."),
    "logo_alt": ("LOGO_ALT", "Testo alternativo del logo", "Per chi usa un lettore di schermo, es. «Stemma del Comune "
                 "di Gioia del Colle». Vuoto = logo decorativo."),
    "centro": ("MAPPA_CENTRO", "Centro della mappa", "Latitudine e longitudine, es. 40.7990,16.9230."),
    "mappa_tiles": ("MAPPA_TILES", "Tile della mappa", "URL con {z}, {x} e {y}. In esercizio un tile server dell'ente "
                    "o un fornitore con accordo."),
    "mappa_attribuzione": ("MAPPA_ATTRIBUZIONE", "Attribuzione della mappa",
                           "Testo dei crediti; ammessi solo collegamenti <a href=\"https://…\">."),
    "geocoder": ("LUOGHI_GEOCODER", "Ricerca di indirizzi e luoghi",
                 "URL di un servizio Nominatim; vuoto = si cercano solo le fermate."),
    "biglietti": ("INFO_BIGLIETTI", "Informazioni sui biglietti", "Testo ufficiale dell'ente su tariffe e punti vendita."),
    "link_biglietti": ("LINK_BIGLIETTI", "Biglietteria online", "URL del sistema di acquisto del gestore; vuoto = "
                       "nessun pulsante."),
    "biglietteria_nome": ("BIGLIETTERIA_NOME", "Nome della biglietteria", "Es. «Biglietteria Sabato Viaggi»."),
}
