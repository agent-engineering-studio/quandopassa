---
title: Configurazione (.env)
description: Tutte le variabili del file .env di QuandoPassa.
---

# Configurazione (`.env`)

Tutta la configurazione sta nel file `.env`, creato da `.env.example` (`make env` o `make up`). I commenti vanno
su righe proprie. Dopo ogni modifica: `make up`.

## Feed GTFS

| Variabile | Predefinito | Significato |
|---|---|---|
| `GTFS_DIR` | `./data` | Cartella del feed GTFS, relativa alla radice del repository. Docker la monta in sola lettura. |

## Servizio e Comune

| Variabile | Predefinito | Significato |
|---|---|---|
| `COMUNE_NOME` | `Comune di Gioia del Colle` | Nome dell'ente, nell'header e nel footer |
| `SERVIZIO_NOME` | `Bus urbano di Gioia del Colle` | Nome del servizio sotto il marchio |
| `MAPPA_CENTRO` | `40.7990,16.9230` | Centro iniziale della mappa (`lat,lon`) |
| `INFO_BIGLIETTI` | testo generico | Testo su biglietti e tariffe (scheda Servizio e assistente): usare il testo ufficiale dell'ente |
| `LINK_BIGLIETTI` | vuoto | Indirizzo del sistema di acquisto online dell'azienda di trasporto: mostra il pulsante "Acquista il biglietto". QuandoPassa non vende biglietti né gestisce pagamenti. Vuoto = nessun pulsante. |
| `BIGLIETTERIA_NOME` | vuoto | Nome del gestore della biglietteria, mostrato accanto al pulsante |

## Intestazione dell'app

Si cambiano anche dal [backoffice](backoffice.md) (Impostazioni), dove si carica il logo: il valore salvato lì ha
la precedenza su quello del `.env`.

| Variabile | Predefinito | Significato |
|---|---|---|
| `APP_TITLE` | `QuandoPassa` | Titolo accanto al logo |
| `ENTITY_URL` | vuoto | Sito dell'ente, collegato al nome in alto a sinistra; vuoto = sito dell'azienda di trasporto |
| `LOGO_ALT` | vuoto | Testo alternativo del logo per i lettori di schermo; vuoto = logo decorativo |

## Mappa

| Variabile | Predefinito | Significato |
|---|---|---|
| `MAPPA_TILES` | tile OpenStreetMap | URL delle tile `{z}/{x}/{y}`. Per traffico elevato usare un tile server proprio. |
| `MAPPA_ATTRIBUZIONE` | © OpenStreetMap contributors | Attribuzione mostrata sulla mappa |

## Intelligenza artificiale

| Variabile | Predefinito | Significato |
|---|---|---|
| `INFERENCE_BACKEND` | `rules` | `rules`: motore a regole offline, nessun dato esce dal server. `openai`: LLM compatibile OpenAI. |
| `LLM_BASE_URL` | `http://ollama:11434/v1` | Endpoint OpenAI-compatibile (Ollama del profilo `llm`, vLLM, Azure OpenAI…) |
| `LLM_MODEL` | `qwen2.5:1.5b-instruct` | Modello |
| `LLM_API_KEY` | `ollama` | Chiave dell'endpoint |
| `LLM_TIMEOUT` | `20` | Secondi prima di tornare alle regole |

Con `openai` l'LLM capisce frasi più libere e riformula le risposte, ma orari e minuti restano quelli calcolati
dall'app: una riformulazione con numeri diversi viene scartata.

## Server MCP

| Variabile | Predefinito | Significato |
|---|---|---|
| `MCP_ALLOWED_HOSTS` | `localhost:*,127.0.0.1:*` | Host ammessi sul trasporto HTTP (protezione da DNS rebinding) |

## Varie

| Variabile | Predefinito | Significato |
|---|---|---|
| `BASE_URL` | `http://localhost:8000` | Indirizzo pubblico dell'app |
| `LUOGHI_GEOCODER` | `https://nominatim.openstreetmap.org` | "Come arrivo": ricerca di indirizzi e luoghi, fatta dal server e limitata al territorio servito. Al geocoder arriva solo il testo cercato. In esercizio meglio un'istanza Nominatim dell'ente; vuoto = solo fermate. |
| `DEMO_ORA` | vuoto | Vuoto = **ora reale**. Solo per dimostrazioni: istante ISO (ora di Roma) da cui parte l'orologio del server, es. `2026-11-11T09:00:00`. |
| `TZ_SERVIZIO` | `Europe/Rome` | Fuso orario del servizio |

L'[istanza demo](installazione.md#istanza-demo) imposta da sé `DEMO_ORA` (variabile `DEMO_ORA_ISTANZA_DEMO`
nel `.env` per cambiarla), senza toccare l'app principale.

## Backoffice

Spento finché `ADMIN_USER` è vuoto. Il modo più semplice per attivarlo è `make backoffice` (Docker) o
`sudo ./deploy/install.sh --backoffice` (macchina virtuale), che compilano queste righe. Vedi
[Backoffice](backoffice.md).

| Variabile | Predefinito | Significato |
|---|---|---|
| `ADMIN_USER` | vuoto | Utente del backoffice; vuoto = backoffice spento |
| `ADMIN_PASSWORD_HASH` | vuoto | Hash scrypt della password (`make password`); mai la password in chiaro |
| `ADMIN_SECRET` | vuoto | Chiave casuale che firma le sessioni (almeno 32 caratteri); vuota = nuova a ogni avvio |
| `DATA_DIR` | vuoto | Cartella scrivibile con il feed generato, le impostazioni e il logo (Docker: `/srv/dati`, VM: `/var/lib/quandopassa`). Con `DATA_DIR` l'app legge il feed da qui e non più da `GTFS_DIR`, che serve solo al primo avvio. |
| `DATABASE_URL` | vuoto | Connessione a Postgres, es. `postgresql://quandopassa:PASSWORD@db:5432/quandopassa` |
| `POSTGRES_PASSWORD` | vuoto | Password del database nel profilo Docker `backoffice` (uguale a quella in `DATABASE_URL`) |
| `OSRM_URL` | server OSRM pubblico | Calcolo dei tracciati stradali delle linee dal backoffice. Il server pubblico è solo per prove: in esercizio un'istanza dell'ente, oppure vuoto (funzione spenta). |

Le impostazioni dell'intestazione, della mappa, della ricerca dei luoghi e dei biglietti modificate dal backoffice
hanno la precedenza sul `.env`; nel backoffice "Torna al valore del .env" annulla la modifica.

