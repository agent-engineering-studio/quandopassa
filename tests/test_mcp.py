import asyncio
import json

from fastapi.testclient import TestClient

from conftest import MERCOLEDI_9


def _server(client):
    from conftest import mcp_quandopassa as mod
    app = mod.ClientApp("http://testserver", client=client)
    return mod, mod.crea_server(app)


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
            "come_arrivare", "orari_linea", "chiedi_assistente"} == nomi
    assert _chiama(mcp, "cerca_fermata", nome="plebiscito")[0]["id"] == "R02"
    p = _chiama(mcp, "prossime_partenze", fermata_id="R05", n=2, ora=MERCOLEDI_9.isoformat())
    assert p[0]["orario"].startswith("2026-11-11T09:10")
    it = _chiama(mcp, "come_arrivare", lat=40.7835, lon=16.9334, destinazione="Piazza Plebiscito",
                 ora=MERCOLEDI_9.isoformat())
    assert it["destinazione"]["nome"] == "Piazza Plebiscito" and it["opzioni"]
    v = _chiama(mcp, "bus_in_servizio", ora=MERCOLEDI_9.isoformat())
    assert v["tempo_reale"] is False and v["veicoli"]


def test_errori_leggibili(client):
    _, mcp = _server(client)
    try:
        asyncio.run(mcp.call_tool("prossime_partenze", {"fermata_id": "NOPE"}))
    except Exception as e:  # noqa: BLE001
        assert "404" in str(e)
    else:
        raise AssertionError("atteso errore")
