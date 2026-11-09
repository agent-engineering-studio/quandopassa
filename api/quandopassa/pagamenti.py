"""Pagamento dei titoli di viaggio: adattatore intercambiabile, perché il venditore non è ancora deciso.

    PAGAMENTI=simulato   prototipo: pagamento simulato in stile pagoPA, nessun denaro reale (predefinito)
    PAGAMENTI=pagopa     vende il Comune: dovuto pagoPA tramite l'intermediario dell'ente (MyPay Regione Puglia, SIL)
    PAGAMENTI=gestore    vende l'azienda di trasporto: checkout del suo prestatore di servizi di pagamento

Gli ultimi due sono scheletri da completare con le credenziali dell'ente o del gestore (vedi docs/biglietti.md).
Il resto della biglietteria non cambia: chiede un pagamento, ne verifica l'esito, emette il titolo.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Protocol


@dataclass
class RichiestaPagamento:
    riferimento: str        # IUV pagoPA o identificativo del checkout
    url: str | None         # pagina di pagamento esterna; None per il simulato (la mostra l'app)
    simulato: bool


class Pagamenti(Protocol):
    nome: str

    def crea(self, acquisto_id: str, importo_cent: int, causale: str) -> RichiestaPagamento: ...
    def pagato(self, riferimento: str) -> bool: ...


class PagamentoSimulato:
    """Nessun denaro reale: il pagamento si conclude con `esito` (pulsanti "Paga" / "Annulla" della pagina simulata)."""

    nome = "simulato"

    def __init__(self) -> None:
        self._pagati: set[str] = set()

    def crea(self, acquisto_id: str, importo_cent: int, causale: str) -> RichiestaPagamento:
        return RichiestaPagamento("RF" + secrets.token_hex(8).upper(), None, True)

    def esito(self, riferimento: str, pagato: bool) -> None:
        if pagato:
            self._pagati.add(riferimento)

    def pagato(self, riferimento: str) -> bool:
        return riferimento in self._pagati


class PagoPAMyPay:
    """Vende il Comune. Da completare con l'integrazione SIL di MyPay4 (paaSILInviaDovuti / paaSILChiediPagati),
    come in Spazio Comune: il dovuto nasce con importo e causale esatti, l'esito arriva senza ricevute da caricare.
    Attenzione alle commissioni pagoPA: per importi piccoli conviene vendere carnet e abbonamenti."""

    nome = "pagopa"

    def crea(self, acquisto_id: str, importo_cent: int, causale: str) -> RichiestaPagamento:
        raise NotImplementedError("Integrazione MyPay SIL non configurata: usare PAGAMENTI=simulato")

    def pagato(self, riferimento: str) -> bool:
        raise NotImplementedError


class CheckoutGestore:
    """Vende l'azienda di trasporto con il proprio prestatore di servizi di pagamento (carte, wallet).
    Da completare con l'API di checkout e il webhook di esito scelti dal gestore."""

    nome = "gestore"

    def crea(self, acquisto_id: str, importo_cent: int, causale: str) -> RichiestaPagamento:
        raise NotImplementedError("Checkout del gestore non configurato: usare PAGAMENTI=simulato")

    def pagato(self, riferimento: str) -> bool:
        raise NotImplementedError


def crea_pagamenti(nome: str) -> Pagamenti:
    scelte = {"simulato": PagamentoSimulato, "pagopa": PagoPAMyPay, "gestore": CheckoutGestore}
    if nome not in scelte:
        raise ValueError(f"PAGAMENTI={nome}: valori ammessi {', '.join(scelte)}")
    return scelte[nome]()
