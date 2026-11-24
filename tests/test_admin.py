"""Backoffice: accesso, modifiche su Postgres che aggiornano subito il feed GTFS, avvisi, impostazioni, logo.

Servono un Postgres di prova e TEST_DATABASE_URL (docker compose --profile test lo prepara da solo);
senza, questi test vengono saltati.
"""
from __future__ import annotations

import io
import os
import zipfile

import pytest
from fastapi.testclient import TestClient

from conftest import GTFS
from quandopassa.config import Config
from quandopassa.main import create_app
from quandopassa.password import hash_password, verify_password

DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL non impostato")

USER, PASSWORD = "editor", "password-di-prova"
PASSWORD_HASH = hash_password(PASSWORD)
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")


@pytest.fixture
def admin_cfg(tmp_path):
    import psycopg

    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    return Config(gtfs_dir=GTFS, web_dist=tmp_path / "web", demo_ora="2026-11-11T09:05:00", geocoder="",
                  data_dir=tmp_path / "dati", database_url=DATABASE_URL, admin_user=USER,
                  admin_password=PASSWORD, admin_secret="segreto-di-prova-" * 3, osrm_url="")


@pytest.fixture
def app_client(admin_cfg, ia):
    return TestClient(create_app(admin_cfg, ia))


@pytest.fixture
def admin(app_client):
    r = app_client.post("/api/admin/login", json={"username": USER, "password": PASSWORD})
    assert r.status_code == 200, r.text
    app_client.headers["X-CSRF-Token"] = r.json()["csrf"]
    return app_client


def test_password_hash():
    assert verify_password(PASSWORD, PASSWORD_HASH)
    assert not verify_password("altra", PASSWORD_HASH)
    assert "$" not in PASSWORD_HASH  # il .env di docker compose interpreterebbe i $


def test_backoffice_disattivato_senza_configurazione(client):
    r = client.post("/api/admin/login", json={"username": USER, "password": PASSWORD})
    assert r.status_code == 404 and "ADMIN_USER" in r.json()["detail"]


def test_password_troppo_corta(admin_cfg, ia):
    import dataclasses

    cfg = dataclasses.replace(admin_cfg, admin_password="corta")
    assert "troppo corta" in cfg.admin_problem
    r = TestClient(create_app(cfg, ia)).post("/api/admin/login", json={"username": USER, "password": "corta"})
    assert r.status_code == 404


def test_accesso_con_hash(admin_cfg, ia):
    import dataclasses

    cfg = dataclasses.replace(admin_cfg, admin_password="", admin_password_hash=PASSWORD_HASH)
    c = TestClient(create_app(cfg, ia))
    assert c.post("/api/admin/login", json={"username": USER, "password": PASSWORD}).status_code == 200
    assert c.post("/api/admin/login", json={"username": USER, "password": "altra-password-lunga"}).status_code == 401


def test_accesso_e_csrf(app_client):
    assert app_client.get("/api/admin/session").status_code == 401
    assert app_client.post("/api/admin/login", json={"username": USER, "password": "sbagliata"}).status_code == 401
    r = app_client.post("/api/admin/login", json={"username": USER, "password": PASSWORD})
    assert r.status_code == 200
    assert "httponly" in r.headers["set-cookie"].lower() and "samesite=strict" in r.headers["set-cookie"].lower()
    assert app_client.get("/api/admin/session").json()["username"] == USER
    # modifica senza token CSRF: rifiutata
    r = app_client.put("/api/admin/stops/R02", json={"stop_id": "R02", "stop_name": "X"})
    assert r.status_code == 403
    assert app_client.get("/api/admin/session").headers["cache-control"] == "no-store"


def test_troppi_tentativi(app_client):
    for _ in range(5):
        app_client.post("/api/admin/login", json={"username": USER, "password": "sbagliata"})
    r = app_client.post("/api/admin/login", json={"username": USER, "password": PASSWORD})
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_popolamento_iniziale(admin):
    data = admin.get("/api/admin/data").json()
    assert len(data["stops"]) == len(admin.get("/api/v1/fermate").json()) and {v["variant_id"] for v in data["variants"]} == {"A", "B"}
    a = next(v for v in data["variants"] if v["variant_id"] == "A")
    assert a["stops"][0] == {"stop_id": "R01", "minutes": 0} and "08:30" in a["departures"]
    assert data["feed_info"]["feed_start_date"] == "2026-01-01"
    assert admin.get("/api/admin/status").json()["feed"]["trips"] == 16


def test_modifica_fermata_subito_sulla_mappa(admin):
    stop = next(s for s in admin.get("/api/admin/data").json()["stops"] if s["stop_id"] == "R02")
    stop.update(stop_name="Piazza Plebiscito (lato chiesa)", lat=40.79891, lon=16.92171)
    stop.pop("updated_at")
    before = admin.get("/api/v1/health").json()["feed"]
    r = admin.put("/api/admin/stops/R02", json=stop)
    assert r.status_code == 200, r.text
    pub = admin.get("/api/v1/fermate/R02").json()
    assert pub["nome"] == "Piazza Plebiscito (lato chiesa)" and pub["lat"] == pytest.approx(40.79891)
    assert admin.get("/api/v1/health").json()["feed"] != before  # le interfacce aperte si aggiornano
    z = zipfile.ZipFile(io.BytesIO(admin.get("/api/admin/export.zip").content))
    assert "stops.txt" in z.namelist() and "lato chiesa" in z.read("stops.txt").decode()
    assert admin.get("/api/admin/audit").json()[0]["action"] == "modifica fermata"


def test_modifica_non_valida_lascia_il_feed_intatto(admin):
    data = admin.get("/api/admin/data").json()
    feed = {"agency": data["agency"], "feed_info": {**data["feed_info"], "feed_start_date": "2027-01-01",
                                                    "feed_end_date": "2026-01-01"}}
    feed["feed_info"].pop("feed_version", None)
    r = admin.put("/api/admin/feed", json=feed)
    assert r.status_code == 422 and any("inizio" in e for e in r.json()["detail"]["errors"])
    assert admin.get("/api/admin/data").json()["feed_info"]["feed_start_date"] == "2026-01-01"
    assert admin.get("/api/v1/info").json()["validita"] == ["20260101", "20261231"]


def test_fermata_in_uso_non_si_elimina(admin):
    r = admin.delete("/api/admin/stops/R02")
    assert r.status_code == 409 and "A" in r.json()["detail"]


def test_nuova_fermata_calendario_e_linea(admin):
    assert admin.post("/api/admin/stops", json={"stop_id": "R99", "stop_code": "99", "stop_name": "Stazione",
                                                "lat": 40.80, "lon": 16.93}).status_code == 200
    assert admin.post("/api/admin/calendars", json={"service_id": "FESTIVO", "days": "0000001",
                                                    "exceptions": [{"day": "2026-12-25", "type": 2}]}).status_code == 200
    r = admin.post("/api/admin/variants", json={
        "variant_id": "C", "route_id": "C", "short_name": "C", "long_name": "Navetta stazione", "color": "a61d2a",
        "text_color": "FFFFFF", "service_id": "SVC_MON_SAT", "headsign": "Stazione",
        "stops": [{"stop_id": "R02", "minutes": 0}, {"stop_id": "R99", "minutes": 6}],
        "departures": ["9:10", "10:10"]})
    assert r.status_code == 200, r.text
    linee = {l["id"] for l in admin.get("/api/v1/linee").json()}
    assert "C" in linee
    partenze = admin.get("/api/v1/fermate/R02/partenze?n=30&ora=2026-11-11T09:00").json()
    assert any(p["linea_id"] == "C" and "T09:10" in p["orario"] for p in partenze)
    # una linea con una fermata inesistente non passa
    r = admin.post("/api/admin/variants", json={
        "variant_id": "D", "route_id": "D", "short_name": "D", "color": "000000", "text_color": "FFFFFF",
        "service_id": "SVC_MON_SAT", "stops": [{"stop_id": "R02", "minutes": 0}, {"stop_id": "NO", "minutes": 3}]})
    assert r.status_code == 409


def _fermate_usate(admin, url: str) -> set[str]:
    out = set()
    for opzione in admin.get(url).json()["opzioni"]:
        for tratto in opzione["tratti"]:
            if tratto["tipo"] == "bus":
                out |= {tratto["salita"]["id"], tratto["discesa"]["id"]}
    return out


def test_fermata_sospesa(admin):
    r02 = admin.get("/api/v1/fermate/R02").json()
    da_r02 = (f"/api/v1/itinerari?da_lat={r02['lat']}&da_lon={r02['lon']}&a_lat=40.8045&a_lon=16.931"
              "&ora=2026-11-11T09:05&n=6")
    assert "R02" in _fermate_usate(admin, da_r02)  # senza avvisi si sale proprio lì
    r = admin.post("/api/admin/alerts", json={
        "kind": "stop_closed", "title": "Fermata sospesa per lavori", "description": "Usare la fermata R03",
        "starts_at": "2026-11-10T00:00:00+01:00", "ends_at": "2026-11-20T00:00:00+01:00", "stop_ids": ["R02"]})
    assert r.status_code == 200, r.text
    pub = admin.get("/api/v1/fermate/R02?ora=2026-11-11T09:05").json()
    assert pub["alerts"][0]["kind"] == "stop_closed" and pub["alerts"][0]["active"]
    assert pub["partenze"] and all(p.get("suspended") for p in pub["partenze"])
    assert admin.get("/api/v1/fermate/R03?ora=2026-11-11T09:05").json()["alerts"] == []
    assert any(a["title"] == "Fermata sospesa per lavori" for a in admin.get("/api/v1/info").json()["alerts"])
    assert next(f for f in admin.get("/api/v1/fermate").json() if f["id"] == "R02")["closed"]
    # gli itinerari non passano dalla fermata sospesa
    usate = _fermate_usate(admin, da_r02)
    assert usate and "R02" not in usate


def test_servizio_sospeso(admin):
    assert admin.get("/api/v1/veicoli?ora=2026-11-11T09:05").json()["veicoli"]
    r = admin.post("/api/admin/alerts", json={
        "kind": "service_suspended", "title": "Sciopero", "starts_at": "2026-11-11T00:00:00+01:00",
        "ends_at": "2026-11-12T00:00:00+01:00"})
    assert r.status_code == 200, r.text
    assert admin.get("/api/v1/veicoli?ora=2026-11-11T09:05").json()["veicoli"] == []
    assert admin.get("/api/v1/veicoli?ora=2026-11-12T09:05").json()["veicoli"]
    z = zipfile.ZipFile(io.BytesIO(admin.get("/api/admin/export.zip").content))
    assert "20261111,2" in z.read("calendar_dates.txt").decode()
    alert_id = r.json()["result"]
    assert admin.delete(f"/api/admin/alerts/{alert_id}").status_code == 200
    assert admin.get("/api/v1/veicoli?ora=2026-11-11T09:05").json()["veicoli"]


def test_avviso_non_coerente(admin):
    r = admin.post("/api/admin/alerts", json={"kind": "service_suspended", "title": "Senza fine",
                                              "starts_at": "2026-11-11T00:00:00+01:00"})
    assert r.status_code == 422
    r = admin.post("/api/admin/alerts", json={"kind": "detour", "title": "Deviazione", "route_ids": ["Z"],
                                              "starts_at": "2026-11-11T00:00:00+01:00"})
    assert r.status_code == 422 and "inesistenti" in str(r.json())


def test_impostazioni_e_logo(admin):
    r = admin.put("/api/admin/settings", json={"comune": "Comune di Prova", "app_title": "Bus di Prova",
                                               "entity_url": "https://www.comune.example.it"})
    assert r.status_code == 200, r.text
    info = admin.get("/api/v1/info").json()
    assert info["comune"] == "Comune di Prova"
    assert info["header"]["title"] == "Bus di Prova" and info["header"]["entity_url"] == "https://www.comune.example.it"
    assert admin.put("/api/admin/settings", json={"mappa_tiles": "https://x.example/{z}.png"}).status_code == 422
    assert admin.put("/api/admin/settings", json={"mappa_attribuzione": "<img src=x onerror=alert(1)>"}).status_code == 422
    assert admin.put("/api/admin/settings", json={"GTFS_DIR": "/tmp"}).status_code == 422
    # torna al valore del .env
    assert admin.put("/api/admin/settings", json={"comune": None}).status_code == 200
    assert admin.get("/api/v1/info").json()["comune"] == "Comune di Gioia del Colle"

    assert admin.put("/api/admin/logo", content=PNG, headers={"Content-Type": "image/png"}).status_code == 200
    url = admin.get("/api/v1/info").json()["header"]["logo_url"]
    r = admin.get(url)
    assert r.status_code == 200 and r.content == PNG and r.headers["content-type"] == "image/png"
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    assert admin.put("/api/admin/logo", content=svg).status_code == 415
    assert admin.delete("/api/admin/logo").status_code == 200
    assert admin.get("/api/v1/info").json()["header"]["logo_url"] is None


# ===================================================================== bike sharing
def _gbfs_zip() -> bytes:
    from test_bikes import FEED

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for f in FEED.glob("*.json"):
            z.write(f, f.name)
    return buf.getvalue()


def test_bike_sharing_import_e_pubblicazione(admin, monkeypatch):
    from quandopassa import admin as admin_module
    from test_bikes import mock_client

    assert admin.post("/api/admin/bikes/systems", json={"system_id": "bici", "name": "Bici Gioia"}).status_code == 200
    # anteprima: nessuna modifica
    r = admin.post("/api/admin/bikes/systems/bici/import/file", content=_gbfs_zip())
    assert r.status_code == 200, r.text
    preview = r.json()
    assert preview["dry_run"] and preview["plan"]["added"] == ["101", "102", "103"] and preview["warnings"]
    assert preview["status_url"].endswith("station_status.json")
    assert admin.get("/api/v1/bikes/stations").json()["stations"] == []
    # import vero: stazioni pubblicate, indirizzi e app presi dal feed
    r = admin.post("/api/admin/bikes/systems/bici/import/file?dry_run=false", content=_gbfs_zip())
    assert r.status_code == 200, r.text
    data = admin.get("/api/admin/bikes").json()
    system = data["systems"][0]
    assert system["stations"] == 3 and system["status_url"].endswith("station_status.json")
    assert system["app_url"].startswith("https://play.google.com") and system["last_import"]["added"] == 3
    plebiscito = next(s for s in data["stations"] if s["station_id"] == "101")
    assert plebiscito["source"] == "gbfs" and plebiscito["nearby_stops"][0]["stop_id"] == "R02"
    admin.app.state.app_state.bike_status.client = mock_client()
    pub = admin.get("/api/v1/bikes/stations").json()
    assert len(pub["stations"]) == 3 and next(s for s in pub["stations"] if s["id"] == "101")["bikes"] == 4
    assert admin.get("/api/admin/status").json()["bikes"] == {"systems": 1, "stations": 3}
    assert admin.get("/api/admin/audit").json()[0]["action"] == "import GBFS"

    # l'ufficio sposta una stazione: il re-import non la sovrascrive
    station = {k: plebiscito[k] for k in ("station_id", "name", "short_name", "address", "lat", "lon", "capacity")}
    r = admin.put("/api/admin/bikes/systems/bici/stations/101", json={**station, "lat": 40.79895})
    assert r.status_code == 200, r.text
    r = admin.post("/api/admin/bikes/systems/bici/import/file", content=_gbfs_zip())
    assert r.json()["plan"]["kept_manual"] == ["101"]

    # stazione aggiunta a mano e disattivata: non compare nell'app
    r = admin.post("/api/admin/bikes/systems/bici/stations", json={
        "station_id": "M1", "name": "Villa comunale", "lat": 40.801, "lon": 16.925, "active": False})
    assert r.status_code == 200, r.text
    assert "M1" not in {s["id"] for s in admin.get("/api/v1/bikes/stations").json()["stations"]}

    # verifica della disponibilità dal backoffice
    monkeypatch.setattr(admin_module, "http_client", lambda timeout=8: mock_client())
    live = admin.get("/api/admin/bikes/systems/bici/live").json()
    assert live["matched"] == 2 and live["bikes"] == 4 and "M1" in live["without_status"]

    z = zipfile.ZipFile(io.BytesIO(admin.get("/api/admin/export.zip?sources=true").content))
    assert "sorgenti/bike_sharing.json" in z.namelist()
    assert admin.delete("/api/admin/bikes/systems/bici").status_code == 200
    assert admin.get("/api/v1/bikes/stations").json() == {"systems": [], "stations": []}


def test_bike_sharing_import_da_url_e_errori(admin, monkeypatch):
    from quandopassa import bikes
    from test_bikes import BASE, mock_client

    monkeypatch.setattr(bikes, "http_client", lambda timeout=10: mock_client())
    assert admin.post("/api/admin/bikes/systems", json={"system_id": "bici", "name": "Bici"}).status_code == 200
    r = admin.post("/api/admin/bikes/systems/bici/import/url",
                   json={"url": BASE + "gbfs.json", "dry_run": False})
    assert r.status_code == 200, r.text
    assert admin.get("/api/admin/bikes").json()["systems"][0]["gbfs_url"] == BASE + "gbfs.json"
    assert admin.post("/api/admin/bikes/systems/nessuno/import/file", content=_gbfs_zip()).status_code == 404
    assert admin.post("/api/admin/bikes/systems/bici/import/file", content=b"{}").status_code == 422
    assert admin.post("/api/admin/bikes/systems", json={"system_id": "x", "name": "X",
                                                        "app_url": "javascript:alert(1)"}).status_code == 422
    r = admin.post("/api/admin/bikes/systems/bici/stations", json={"station_id": "a/b", "name": "X", "lat": 1, "lon": 1})
    assert r.status_code == 422
