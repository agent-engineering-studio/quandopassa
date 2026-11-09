---
title: Conformità normativa
description: Matrice di conformità di QuandoPassa rispetto alle norme per i servizi digitali della PA.
---

# Matrice di conformità

Documento tecnico di supporto alla proposta. Da validare con Segretario comunale, RPD e Responsabile per la
transizione digitale.

## Design e accessibilità – L. 4/2004, Linee guida AgID, WCAG 2.1 AA
Bootstrap Italia 2.18.3 impacchettato con l'app (font Titillium Web e icone in locale, nessuna CDN di terzi);
skip link, landmark, etichette sui campi, ricerca fermate navigabile da tastiera (`combobox`), `aria-live` su
assistente e bus in arrivo, esiti "fai in tempo / affrettati / non fai in tempo" con colore **e** testo.
Audit automatico axe-core (WCAG 2 A/AA, 2.1 A/AA) su tutte le schede, desktop e telefono: **0 violazioni**.
Serve comunque un test con utenti e la dichiarazione di accessibilità su form.agid.gov.it.

## Protezione dati – GDPR
Nessun account e nessun cookie; l'unico archivio è quello anonimo dei biglietti. La posizione del telefono si usa solo se la persona la attiva:
le fermate vicine sono calcolate dal server per quella richiesta e le coordinate **non vengono salvate né scritte
nei log** (filtro sui log di accesso, verificato dai test); lo stesso vale per il testo delle domande
all'assistente. Restano nei log di accesso l'indirizzo IP e il percorso richiesto: conservazione da definire con
il RPD. Per "come arrivo" la ricerca di indirizzi e luoghi passa dal server, che invia al geocoder (`LUOGHI_GEOCODER`)
solo il testo cercato, mai la posizione; anche queste ricerche sono oscurate nei log. Le tile della mappa vengono scaricate dal browser dal fornitore indicato in `MAPPA_TILES`: in esercizio
scegliere un tile server proprio o un fornitore con accordo ex art. 28.

## Biglietti (prototipo) – pagamenti e dati
Acquisto anonimo: il server conserva l'impronta della chiave del dispositivo, non dati della persona; i log non
contengono chiavi né codici. Pagamento simulato nel prototipo; per la vendita reale: pagoPA se vende il Comune
(CAD art. 5, intermediario MyPay) oppure il prestatore di pagamento del gestore. QR firmati HMAC-SHA256, verifica
riservata al controllore. Da definire: chi vende secondo il contratto di servizio, trattamento fiscale dei titoli,
informativa. Vedi [Biglietti](biglietti.md).

## Intelligenza artificiale – AI Act, L. 132/2025, Linee guida AgID
Uso a basso rischio (assistente informativo, non decisionale). Trasparenza: l'interfaccia dichiara che è IA
(AI Act art. 50) e ogni risposta riporta il backend usato. Orari e minuti calcolati dal codice dall'orario
ufficiale; le riformulazioni dell'LLM con numeri diversi vengono scartate. Redazione dei dati personali prima di
qualsiasi chiamata a modelli; backend predefinito interamente locale. Prima di attivare un LLM: valutazione
d'impatto secondo le Linee guida AgID e registrazione nel registro dei sistemi IA dell'ente.

## Informazione corretta al cittadino
Le posizioni dei bus sono stime dall'orario programmato e l'app lo dichiara (header, scheda servizio, bus in
arrivo, API con `tempo_reale: false`, istruzioni del server MCP). Il ritardo è indicato come "non rilevabile".

## Dati aperti e interoperabilità – CAD art. 50, Linee guida AgID
Feed GTFS standard; API REST documentate in OpenAPI (`/api/docs`); server MCP in sola lettura per assistenti e
agenti. Valutare la pubblicazione del feed sul portale open data dell'ente.

## Riuso e open source – CAD artt. 68-69
Licenza EUPL-1.2, `publiccode.yml` per la pubblicazione su Developers Italia, configurazione dell'ente fuori dal
codice (`.env`, feed GTFS). Vedi [Riuso e Catalogo](riuso.md).

## Sicurezza
Container non-root, server di inferenza non esposto, MCP solo su localhost con protezione da DNS rebinding,
nessun segreto applicativo, dipendenze senza vulnerabilità note (`pip-audit`, `npm audit`), analisi statica
`bandit`. Da aggiungere in esercizio: HTTPS, rate limiting, aggiornamenti, vulnerability assessment.
