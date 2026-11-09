from conftest import MERCOLEDI_9


def test_health_e_info(client):
    assert client.get("/api/v1/health").json()["stato"] == "ok"
    info = client.get("/api/v1/info").json()
    assert info["tempo_reale"] is False and info["assistente"] is True
    assert info["ora"].startswith("2026-11-11T09:0")  # DEMO_ORA
    assert {l["id"] for l in info["linee"]} == {"A", "B"}


def test_veicoli_e_orario(client):
    v = client.get("/api/v1/veicoli", params={"ora": MERCOLEDI_9.isoformat()}).json()
    assert {x["linea"] for x in v["veicoli"]} == {"A", "B"}
    assert client.get("/api/v1/veicoli", params={"ora": "2026-11-11T22:00"}).json()["prossima_corsa"]
    assert client.get("/api/v1/veicoli", params={"ora": "ieri"}).status_code == 422
    o = client.get("/api/v1/orario", params={"giorno": "2026-11-11"}).json()
    assert len(o["corse"]) == 16


def test_fermate_vicine_con_partenze(client, orario):
    f = orario.fermate["R02"]
    r = client.get("/api/v1/fermate/vicine", params={"lat": f.lat, "lon": f.lon, "n": 2,
                                                     "ora": MERCOLEDI_9.isoformat()}).json()
    assert r[0]["id"] == "R02" and r[0]["distanza_m"] == 0 and "partenze" in r[0]
    assert client.get("/api/v1/fermate/NOPE").status_code == 404


def test_assistente(client, orario):
    q = lambda testo, **kw: client.get("/api/v1/assistente", params={"testo": testo, "ora": MERCOLEDI_9.isoformat(), **kw}).json()
    r = q("quando passa il prossimo bus da Piazza Plebiscito?")
    assert r["intento"] == "prossimo" and "09:35" in r["risposta"] and r["generato_da_ia"] is False
    r = q("dov'è la linea B?")
    assert r["intento"] == "dove_bus" and "linea B" in r["risposta"]
    f = orario.fermate["R11"]
    r = q("come arrivo alla stazione?", lat=f.lat, lon=f.lon)
    assert r["intento"] == "percorso" and "linea B" in r["risposta"] and "Via Moro" in r["risposta"]
    r = q("fermata più vicina", lat=f.lat, lon=f.lon)
    assert "Villaggio Azzurro" in r["risposta"]
    assert q("orari della circolare A")["dati"]["A"]["partenze_capolinea"][0] == "08:30"
    assert q("quanto costa il biglietto?")["intento"] == "faq"
    assert q("ghjkl")["intento"] == "sconosciuto"


def test_assistente_spento_se_inference_giu(cfg):
    from fastapi.testclient import TestClient
    from quandopassa.ai import ClientIA
    from quandopassa.main import create_app
    c = TestClient(create_app(cfg, ClientIA("http://127.0.0.1:9")))
    assert c.get("/api/v1/assistente", params={"testo": "prossimo bus"}).status_code == 503
    assert c.get("/api/v1/info").json()["assistente"] is False
    assert c.get("/api/v1/veicoli").status_code == 200  # il resto funziona
