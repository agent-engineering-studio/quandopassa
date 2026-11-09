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
| `INFO_BIGLIETTI` | testo generico | Risposta dell'assistente su biglietti e tariffe: usare il testo ufficiale dell'ente |

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
