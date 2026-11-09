---
title: Installazione
description: Avviare QuandoPassa con Docker o in sviluppo, eseguire i test e l'istanza demo.
---

# Installazione

## Con Docker (consigliato)

Servono Docker con Compose e `make`.

```bash
git clone https://github.com/gzileni/quandopassa.git
cd quandopassa
make up            # crea .env da .env.example se manca, costruisce e avvia
```

| Servizio | Indirizzo |
|---|---|
| App | http://localhost:8000 |
| Documentazione API | http://localhost:8000/api/docs |
| Server MCP | http://localhost:8090/mcp (solo da localhost) |

Comandi utili (`make` da solo mostra l'elenco):

| Comando | Cosa fa |
|---|---|
| `make up` | Costruisce e avvia app, inferenza e MCP |
| `make up-llm` | Come `up`, con un LLM locale (Ollama, profilo `llm`) |
| `make down` | Ferma i container |
| `make logs S=app` | Log di un servizio |
| `make test` | Suite pytest nel container |
| `make demo` | Istanza demo su :8001 con orologio fisso |
| `make gtfs` / `make geocode` | Rigenera il feed / geocoding e tracciati |
| `make docs` | Anteprima di questo sito su http://127.0.0.1:8002 |

Dopo ogni modifica al `.env`: `make up` (ricrea i container).

## In sviluppo, senza Docker

```bash
pip install -r api/requirements.txt -r inference/requirements.txt
(cd inference && uvicorn server:app --port 8080) &
(cd api && INFERENCE_URL=http://127.0.0.1:8080 uvicorn --factory quandopassa.main:create_app --reload) &
(cd web && npm install && npm run dev)        # http://localhost:5173, le chiamate /api vanno a :8000
```

## Test

```bash
make test                 # nel container
pytest                    # in locale, dopo aver installato i requisiti e pytest
```

I test usano il feed reale di `data/` e un orologio fisso (mercoledì 11/11/2026, 09:05): coprono motore GTFS,
API, assistente, server di inferenza e server MCP. La CI su GitHub esegue anche la build dell'interfaccia e
delle immagini.

## Istanza demo

```bash
make demo                 # http://localhost:8001
```

È la stessa app con l'orologio che parte da **mercoledì 11/11/2026 alle 09:00**, quando circolano entrambe le
linee: serve per presentazioni e video fuori dall'orario di servizio. L'app principale resta sempre sull'ora
reale. L'orologio parte dall'avvio del container: `docker compose restart demo` lo riporta alle 09:00.

## Messa in esercizio

- Pubblicare l'app dietro un reverse proxy HTTPS; il server MCP resta su `127.0.0.1` salvo necessità.
- Per traffico elevato usare un tile server proprio o un fornitore: la policy dei tile OpenStreetMap non
  consente un uso intensivo (`MAPPA_TILES`).
- Tenere `INFERENCE_BACKEND=rules` finché non è stata fatta la valutazione prevista dalle Linee guida AgID per
  un LLM. Vedi [Intelligenza artificiale](intelligenza-artificiale.md).
- Non ci sono database né segreti applicativi da proteggere: l'app non salva dati delle persone.
