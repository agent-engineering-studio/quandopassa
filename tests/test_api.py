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


def test_log_di_accesso_senza_posizione_ne_domande():
    import logging
    from quandopassa.main import SenzaDatiPersonali
    r = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d', (
        "1.2.3.4:5", "GET", "/api/v1/fermate/vicine?lat=40.8099&lon=16.922&n=3", "1.1", 200), None)
    SenzaDatiPersonali().filter(r)
    assert "40.8099" not in r.getMessage() and "lat=***" in r.getMessage() and "n=3" in r.getMessage()
    for percorso in ("/api/v1/assistente?testo=mi+chiamo+Mario",
                     "/api/v1/itinerari?da_lat=40.78&da_lon=16.93&a_lat=40.80&a_lon=16.91&a_nome=Casa+di+Mario",
                     "/api/v1/luoghi?q=via+Mario+Rossi+12"):
        r = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "%s", (percorso,), None)
        SenzaDatiPersonali().filter(r)
        assert "Mario" not in r.getMessage() and "40.78" not in r.getMessage(), r.getMessage()


def test_itinerari_con_cambio_e_a_piedi(client, orario):
    va, cim = orario.fermate["R11"], orario.fermate["R10"]
    r = client.get("/api/v1/itinerari", params={"da_lat": va.lat, "da_lon": va.lon, "a_lat": cim.lat, "a_lon": cim.lon,
                                                "ora": MERCOLEDI_9.isoformat()}).json()
    opz = r["opzioni"]
    assert opz and all(a["arrivo"] <= b["arrivo"] for a, b in zip(opz[1:], opz[2:]))
    cambio = next(o for o in opz if o["cambi"] == 1)
    bus = [t for t in cambio["tratti"] if t["tipo"] == "bus"]
    assert [t["linea"] for t in bus] == ["B", "A"] and bus[0]["discesa"]["id"] == bus[1]["salita"]["id"] == "R05"
    assert bus[1]["attesa_min"] >= 1 and bus[0]["discesa"]["orario"] < bus[1]["salita"]["orario"]
    assert len(bus[0]["punti"]) > 10  # segue il tracciato stradale
    # a meno di 600 m si va a piedi
    p = orario.fermate["R02"]
    vicino = client.get("/api/v1/itinerari", params={"da_lat": p.lat, "da_lon": p.lon, "a_lat": p.lat + 0.002,
                                                     "a_lon": p.lon}).json()["opzioni"]
    assert len(vicino) == 1 and vicino[0]["linee"] == []


def test_luoghi_senza_geocoder_restituisce_le_fermate(client):
    r = client.get("/api/v1/luoghi", params={"q": "plebiscito"}).json()
    assert r[0]["tipo"] == "fermata" and r[0]["id"] == "R02"
    assert client.get("/api/v1/luoghi", params={"q": "x"}).status_code == 422


def _compra(client, tipo):
    a = client.post("/api/v1/biglietti/acquisti", json={"tipo": tipo}).json()
    assert client.post(f"/api/v1/biglietti/acquisti/{a['acquisto_id']}/pagamento-simulato",
                       json={"chiave": a["chiave"], "pagato": True}).status_code == 200
    t = client.post(f"/api/v1/biglietti/acquisti/{a['acquisto_id']}/conferma", json={"chiave": a["chiave"]}).json()
    return a, t


def test_tariffe_dal_env(cfg, ia):
    from dataclasses import replace
    from fastapi.testclient import TestClient
    from quandopassa.main import create_app
    c = TestClient(create_app(replace(cfg, tariffa_corsa="1,30", corse_carnet=5), ia))
    tariffe = {t["tipo"]: t for t in c.get("/api/v1/biglietti").json()["tariffe"]}
    assert tariffe["corsa"]["importo_cent"] == 130 and tariffe["carnet"]["corse"] == 5
    assert "1,30" in c.get("/api/v1/assistente", params={"testo": "quanto costa il biglietto?"}).json()["risposta"]
    spenta = TestClient(create_app(replace(cfg, biglietti_attivi=False), ia))
    assert spenta.get("/api/v1/info").json()["biglietti"] == {"attivi": False}
    assert spenta.post("/api/v1/biglietti/acquisti", json={"tipo": "corsa"}).status_code == 404


def test_carnet_attivazione_e_verifica(client):
    a, t = _compra(client, "carnet")
    assert t["stato"] == "pronto" and t["corse_rimaste"] == 10
    # conferma idempotente, chiave obbligatoria
    assert client.post(f"/api/v1/biglietti/acquisti/{a['acquisto_id']}/conferma", json={"chiave": a["chiave"]}).json()["id"] == t["id"]
    assert client.post(f"/api/v1/biglietti/titoli/{t['id']}/attiva", json={"chiave": "x" * 20}).status_code == 404
    att = client.post(f"/api/v1/biglietti/titoli/{t['id']}/attiva", json={"chiave": a["chiave"]}).json()
    assert att["stato"] == "attivo" and att["corse_rimaste"] == 9 and att["attivazione"]["qr_img"].startswith("data:image/svg+xml;base64,")
    # riattivare mentre è valido non consuma un'altra corsa
    assert client.post(f"/api/v1/biglietti/titoli/{t['id']}/attiva", json={"chiave": a["chiave"]}).json()["corse_rimaste"] == 9
    # portafoglio dalle chiavi del dispositivo
    assert [x["id"] for x in client.post("/api/v1/biglietti/portafoglio", json={"chiavi": [a["chiave"]]}).json()] == [t["id"]]
    # verifica del controllore: QR, codice, contraffazione, credenziali
    auth = ("controllore", "verifica-segreta")
    qr, codice = att["attivazione"]["qr"], att["attivazione"]["codice"]
    assert client.post("/api/v1/biglietti/verifica", json={"codice": qr}).status_code == 401
    assert client.post("/api/v1/biglietti/verifica", json={"codice": qr}, auth=auth).json()["esito"] == "valido"
    assert client.post("/api/v1/biglietti/verifica", json={"codice": codice.lower()}, auth=auth).json()["esito"] == "valido"
    falso = qr[:-4] + "0000"
    assert client.post("/api/v1/biglietti/verifica", json={"codice": falso}, auth=auth).json()["esito"] == "non_valido"


def test_acquisto_non_pagato_non_emette(client):
    a = client.post("/api/v1/biglietti/acquisti", json={"tipo": "corsa"}).json()
    assert client.post(f"/api/v1/biglietti/acquisti/{a['acquisto_id']}/conferma",
                       json={"chiave": a["chiave"]}).status_code == 409


def test_pagamento_annullato_non_emette(client):
    a = client.post("/api/v1/biglietti/acquisti", json={"tipo": "corsa"}).json()
    client.post(f"/api/v1/biglietti/acquisti/{a['acquisto_id']}/pagamento-simulato", json={"chiave": a["chiave"], "pagato": False})
    r = client.post(f"/api/v1/biglietti/acquisti/{a['acquisto_id']}/conferma", json={"chiave": a["chiave"]})
    assert r.status_code == 409 and "annullato" in r.json()["errore"]
