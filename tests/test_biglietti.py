"""Scadenze dei titoli di viaggio, con un orologio controllato dal test."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from quandopassa.biglietti import Biglietteria, ErroreBiglietto
from quandopassa.pagamenti import PagamentoSimulato


@pytest.fixture
def cassa(cfg):
    ora = [datetime(2026, 11, 11, 9, 0, tzinfo=ZoneInfo("Europe/Rome"))]
    b = Biglietteria(cfg, PagamentoSimulato(), lambda: ora[0])

    def compra(tipo):
        a = b.acquista(tipo)
        b.esito_simulato(a["acquisto_id"], a["chiave"], True)
        return a["chiave"], b.conferma(a["acquisto_id"], a["chiave"])
    return b, ora, compra


def test_corsa_singola_scade_e_non_si_riattiva(cassa):
    b, ora, compra = cassa
    chiave, t = compra("corsa")
    qr = b.attiva(t["id"], chiave)["attivazione"]["qr"]
    assert b.verifica(qr)["esito"] == "valido"
    ora[0] += timedelta(minutes=61)
    assert b.verifica(qr)["esito"] == "scaduto"
    assert b.portafoglio([chiave])[0]["stato"] == "esaurito"
    with pytest.raises(ErroreBiglietto, match="esaurite"):
        b.attiva(t["id"], chiave)


def test_abbonamento_vale_i_giorni_del_env(cassa):
    b, ora, compra = cassa
    chiave, t = compra("abbonamento")
    att = b.attiva(t["id"], chiave)["attivazione"]
    assert att["scade"] == t["valido_al"]
    ora[0] += timedelta(days=b.cfg.giorni_abbonamento, minutes=1)
    assert b.portafoglio([chiave])[0]["stato"] == "scaduto"
    with pytest.raises(ErroreBiglietto, match="scaduto"):
        b.attiva(t["id"], chiave)
