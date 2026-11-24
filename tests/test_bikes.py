"""Bike sharing: lettura dei feed GBFS (v2 e v3), import, disponibilità con cache e API pubbliche."""
from __future__ import annotations

import io
import json
import shutil
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import GTFS
from quandopassa import bikes
from quandopassa.bikes import (BIKES_FILE, GbfsError, StatusCache, detect, fetch_feed, parse_station_information,
                               parse_station_status, parse_system_information, plan_import, read_upload, ttl_of)
from quandopassa.config import Config
from quandopassa.main import create_app

FEED = GTFS.parent / "tests" / "gbfs"
BASE = "https://gbfs.example.org/gioia/"


def doc(name: str) -> dict:
    return json.loads((FEED / f"{name}.json").read_text())


def mock_client(calls: list | None = None, status: dict | None = None, fail: bool = False) -> httpx.Client:
    """Client HTTP che risponde con i file di tests/gbfs (o con `status` per station_status)."""
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(request.url))
        if fail:
            return httpx.Response(503)
        name = str(request.url).removeprefix(BASE).removesuffix(".json")
        if name == "station_status" and status is not None:
            return httpx.Response(200, json=status)
        path = FEED / f"{name}.json"
        return httpx.Response(200, content=path.read_bytes()) if path.exists() else httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(handler))


# ===================================================================== lettura
def test_riconosce_i_file_gbfs():
    assert [detect(doc(n)) for n in ("gbfs", "system_information", "station_information", "station_status")] == [
        "gbfs", "system_information", "station_information", "station_status"]
    assert detect({"data": {"pippo": 1}}) is None and detect([1, 2]) is None


def test_stazioni_v2_con_righe_scartate():
    stations, warnings = parse_station_information(doc("station_information"))
    assert [s["station_id"] for s in stations] == ["101", "102", "103"]
    assert stations[0] == {"station_id": "101", "name": "Piazza Plebiscito", "short_name": "PLB",
                           "address": "Piazza Plebiscito", "lat": 40.7989, "lon": 16.9216, "capacity": 10}
    assert any("104" in w for w in warnings)


def test_stazioni_e_sistema_v3_nomi_localizzati():
    v3 = {"version": "3.0", "ttl": 0, "data": {"stations": [
        {"station_id": "a-1", "name": [{"text": "Station", "language": "en"}, {"text": "Stazione", "language": "it"}],
         "lat": 41.1, "lon": 16.8}]}}
    stations, _ = parse_station_information(v3)
    assert stations[0]["name"] == "Stazione" and stations[0]["capacity"] is None
    info = parse_system_information({"data": {"system_id": "x", "name": [{"text": "Bici", "language": "it"}],
                                              "rental_apps": {"ios": {"store_uri": "https://apps.apple.com/x"}}}})
    assert info["name"] == "Bici" and info["app_url"] == "https://apps.apple.com/x"
    status = parse_station_status({"data": {"stations": [{"station_id": "a-1", "num_vehicles_available": 2,
                                                          "num_docks_available": 3,
                                                          "last_reported": "2026-11-11T09:00:00+01:00"}]}})
    assert status["a-1"]["bikes"] == 2 and status["a-1"]["reported_at"].startswith("2026-11-11")


def test_disponibilita_esclude_le_stazioni_non_installate():
    status = parse_station_status(doc("station_status"))
    assert set(status) == {"101", "102"} and status["101"]["bikes"] == 4 and status["102"]["docks"] == 8
    assert ttl_of(doc("station_status")) == 45 and ttl_of({"ttl": 0}) == bikes.STATUS_TTL_DEFAULT
    assert ttl_of({"ttl": 86400}) == bikes.STATUS_TTL_MAX


def test_file_caricato_json_e_zip():
    assert set(read_upload((FEED / "station_information.json").read_bytes())) == {"station_information"}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for f in FEED.glob("*.json"):
            z.write(f, f"feed/{f.name}")
        z.writestr("leggimi.txt", "ignorato")
    assert set(read_upload(buf.getvalue())) == {"gbfs", "system_information", "station_information", "station_status"}
    with pytest.raises(GbfsError):
        read_upload(b"non json")
    with pytest.raises(GbfsError):
        read_upload(b'{"data": {"altro": 1}}')


def test_autodiscovery_da_url():
    calls: list[str] = []
    docs, urls = fetch_feed(BASE + "gbfs.json", mock_client(calls))
    assert set(docs) == {"gbfs", "system_information", "station_information"}
    assert urls["station_status"] == BASE + "station_status.json"
    assert not any("station_status" in c for c in calls)   # la disponibilità non si importa
    with pytest.raises(GbfsError, match="download"):
        fetch_feed(BASE + "gbfs.json", mock_client(fail=True))
    with pytest.raises(GbfsError):
        fetch_feed("ftp://example.org/gbfs.json", mock_client())


def test_piano_di_import():
    incoming, _ = parse_station_information(doc("station_information"))
    existing = [
        {**incoming[0], "source": "gbfs", "active": True},                           # uguale
        {**incoming[1], "name": "Rinominata dall'ufficio", "source": "manuale"},    # modificata a mano: si tiene
        {"station_id": "099", "name": "Dismessa", "lat": 40.8, "lon": 16.9, "source": "gbfs"},
        {"station_id": "M1", "name": "Manuale", "lat": 40.8, "lon": 16.9, "source": "manuale"},
    ]
    plan = plan_import(existing, incoming, remove_missing=False)
    assert [s["station_id"] for s in plan["added"]] == ["103"] and plan["unchanged"] == ["101"]
    assert plan["kept_manual"] == ["102"] and plan["missing"] == ["099"] and plan["removed"] == []
    assert plan_import(existing, incoming, remove_missing=True)["removed"] == ["099"]   # mai le manuali
    moved = [{**incoming[0], "lat": 40.0}]
    assert plan_import([{**incoming[0], "source": "gbfs"}], moved, False)["updated"] == moved


# ===================================================================== disponibilità con cache
def test_cache_rispetta_il_ttl_e_sopravvive_agli_errori():
    now = [1000.0]
    calls: list[str] = []
    cache = StatusCache(mock_client(calls), clock=lambda: now[0])
    url = BASE + "station_status.json"
    data, age, error = cache.get(url)
    assert data["101"]["bikes"] == 4 and age == 0 and not error
    now[0] += 30
    cache.get(url)
    assert len(calls) == 1                     # ttl 45 s: nessuna nuova richiesta
    now[0] += 30
    cache.client = mock_client(calls, fail=True)
    data, age, error = cache.get(url)
    assert data["101"]["bikes"] == 4 and age == 60 and "download" in error   # resta l'ultimo dato
    now[0] += bikes.STATUS_STALE_AFTER
    assert cache.get(url)[0] == {}              # troppo vecchio: niente numeri


# ===================================================================== API pubbliche
@pytest.fixture
def bike_client(tmp_path, ia):
    feed = tmp_path / "gtfs"
    shutil.copytree(GTFS, feed)
    stations, _ = parse_station_information(doc("station_information"))
    (feed / BIKES_FILE).write_text(json.dumps({
        "systems": [{"system_id": "bici_gioia", "name": "Bici Gioia", "operator": "Gestore", "live": True,
                     "app_url": "https://play.google.com/store/apps/details?id=org.example.bici",
                     "status_url": BASE + "station_status.json"}],
        "stations": [{**s, "system_id": "bici_gioia", "active": True} for s in stations]}))
    app = create_app(Config(gtfs_dir=feed, web_dist=tmp_path, demo_ora="2026-11-11T09:05:00", geocoder=""), ia)
    app.state.app_state.bike_status.client = mock_client()
    return TestClient(app)


def test_api_stazioni_con_disponibilita(bike_client):
    data = bike_client.get("/api/v1/bikes/stations").json()
    assert data["systems"][0]["live"] and data["systems"][0]["app_url"].startswith("https://")
    by_id = {s["id"]: s for s in data["stations"]}
    assert by_id["101"]["live"] and by_id["101"]["bikes"] == 4 and by_id["101"]["docks"] == 6
    assert not by_id["103"]["live"] and by_id["103"]["bikes"] is None    # non installata: nessun numero
    assert bike_client.get("/api/v1/info").json()["bike_sharing"][0]["name"] == "Bici Gioia"


def test_api_stazioni_vicine_e_scheda_fermata(bike_client):
    near = bike_client.get("/api/v1/bikes/nearby?lat=40.7988&lon=16.9217&n=2").json()
    assert near[0]["id"] == "101" and near[0]["distance_m"] < 50 and near[0]["walk_min"] >= 1
    r02 = bike_client.get("/api/v1/fermate/R02").json()
    assert [b["id"] for b in r02["bikes_nearby"]] == ["101"]
    assert bike_client.get("/api/v1/bikes/nearby?lat=45&lon=9").json() == []


def test_api_senza_bike_sharing(client):
    assert client.get("/api/v1/bikes/stations").json() == {"systems": [], "stations": []}
    assert client.get("/api/v1/fermate/R02").json()["bikes_nearby"] == []
