import asyncio
import json

from fastapi.testclient import TestClient

from conftest import MERCOLEDI_9


def _server(client, scrittura=False, ufficio=None):
    from conftest import mcp_quandopassa as mod
    app = mod.ClientApp("http://testserver", client=client, ufficio=ufficio)
    return mod, mod.crea_server(app, scrittura=scrittura)


def _chiama(mcp, strumento, **args):
    risultato = asyncio.run(mcp.call_tool(strumento, args))
    if isinstance(risultato, tuple):  # (contenuti, output strutturato)
        strutturato = risultato[1]
        return strutturato.get("result", strutturato) if set(strutturato) == {"result"} else strutturato
    return json.loads(risultato[0].text)


def _strumenti(mcp):
    return {t.name for t in asyncio.run(mcp.list_tools())}


def test_strumenti_pubblici(client):
    _, mcp = _server(client)
    nomi = _strumenti(mcp)
    assert {"info_servizio", "cerca_fermata", "fermate_vicine", "prossime_partenze", "bus_in_servizio",
            "come_arrivare", "chiedi_assistente", "recensioni", "riepilogo_recensioni"} <= nomi
    assert "lascia_recensione" not in nomi and "modera_recensione" not in nomi
    assert _chiama(mcp, "cerca_fermata", nome="plebiscito")[0]["id"] == "R02"
    p = _chiama(mcp, "prossime_partenze", fermata_id="R05", n=2, ora=MERCOLEDI_9.isoformat())
    assert p[0]["orario"].startswith("2026-11-11T09:10")
    v = _chiama(mcp, "bus_in_servizio", ora=MERCOLEDI_9.isoformat())
    assert v["tempo_reale"] is False and v["veicoli"]


def test_scrittura_e_ufficio(client):
    _, mcp = _server(client, scrittura=True, ufficio=("ufficio", "segreta"))
    assert {"lascia_recensione", "ultime_recensioni", "modera_recensione"} <= _strumenti(mcp)
    r = _chiama(mcp, "lascia_recensione", tipo="linea", id="A", voto=4, testo="Puntuale", tag=["puntuale"])
    assert r["autore"] == "via assistente"
    m = _chiama(mcp, "modera_recensione", id=r["id"])
    assert m["nascosta"] is True


def test_errori_leggibili(client):
    _, mcp = _server(client)
    try:
        asyncio.run(mcp.call_tool("prossime_partenze", {"fermata_id": "NOPE"}))
    except Exception as e:  # noqa: BLE001
        assert "404" in str(e)
    else:
        raise AssertionError("atteso errore")
