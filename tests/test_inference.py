from fastapi.testclient import TestClient

import rules
from conftest import inference


def test_intenti():
    casi = {
        "Quando passa il prossimo bus da Piazza Plebiscito?": ("prossimo", "piazza plebiscito"),
        "come arrivo al cimitero": ("percorso", "cimitero"),
        "voglio andare alla stazione": ("percorso", "stazione"),
        "dov'è adesso la linea B?": ("dove_bus", None),
        "fermata più vicina": ("vicina", None),
        "orari della circolare A": ("orari_linea", None),
        "quanto costa il biglietto": ("info", None),
        "a che ora passa la B a villaggio azzurro": ("prossimo", "villaggio azzurro"),
    }
    for frase, (intento, luogo) in casi.items():
        r = rules.estrai_intento(frase)
        assert (r["intento"], r["luogo"]) == (intento, luogo), frase
    assert rules.estrai_intento("orari della circolare A")["linea"] == "A"
    assert rules.estrai_intento("prossimo bus alle 10 da seven")["ora"] == "10:00"
    assert rules.estrai_intento("bus alle 6 di pomeriggio")["ora"] == "18:00"


def test_endpoint_rules_offline():
    c = TestClient(inference.app)
    assert c.get("/health").json()["backend"] == "rules"
    r = c.post("/v1/tasks/answer", json={"domanda": "x", "intento": "prossimo", "bozza": "Linea A alle 9:10."}).json()
    assert r == {"risposta": "Linea A alle 9:10.", "backend": "rules", "generato_da_ia": False}
    assert c.post("/v1/tasks/summary", json={"oggetto": "Seven", "recensioni": []}).status_code == 404


def test_controllo_numeri_riformulazione():
    assert inference._stessi_numeri("Linea A alle 09:10, tra 5 min.", "Il bus A passa alle 9.10, cioè tra 5 minuti.") is False
    assert inference._stessi_numeri("Linea A alle 09:10, tra 5 min.", "Il bus della linea A passa alle 09:10, tra 5 minuti.")
    assert not inference._stessi_numeri("Linea A alle 09:10.", "Linea A alle 09:15.")


def test_pii_redatte():
    assert "[EMAIL]" in inference.redigi("scrivi a mario.rossi@example.com")
    assert "[TELEFONO]" in inference.redigi("chiama 333 1234567")
