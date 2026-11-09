# QuandoPassa – comandi rapidi per docker compose.  `make` da solo mostra l'elenco.

COMPOSE ?= docker compose
PYTHON  ?= python3
GTFS    ?= data
# servizio per logs/shell, es.  make logs S=app
S       ?=

.DEFAULT_GOAL := help
.PHONY: help env build build-nocache up up-llm down restart ps logs shell test gtfs geocode clean

help: ## Mostra questo elenco
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n",$$1,$$2}'

env: ## Crea .env da .env.example (se manca)
	@test -f .env && echo ".env esiste già" || (cp .env.example .env && chmod 600 .env && echo "creato .env: rivedere i valori")

build: env ## Costruisce le immagini (app, inference, mcp)
	$(COMPOSE) build

build-nocache: env ## Costruisce le immagini senza cache
	$(COMPOSE) build --no-cache --pull

up: env ## Avvia app + inferenza + MCP (http://localhost:8000)
	$(COMPOSE) up -d --build --force-recreate --remove-orphans
	@echo "app: http://localhost:8000   MCP: http://localhost:8090/mcp"

up-llm: env ## Come up, con LLM locale Ollama (profilo llm)
	$(COMPOSE) --profile llm up -d --build --force-recreate

down: ## Ferma e rimuove i container (i volumi restano)
	$(COMPOSE) --profile llm --profile test down

restart: down up ## Riavvia tutto

ps: ## Stato dei container
	$(COMPOSE) ps

logs: ## Log in tempo reale (tutti, o S=app)
	$(COMPOSE) logs -f --tail=200 $(S)

shell: ## Shell in un container (S=app predefinito)
	$(COMPOSE) exec $(or $(S),app) sh

test: env ## Suite pytest nel container
	$(COMPOSE) --profile test run --rm --build test

gtfs: ## Rigenera i file GTFS .txt da fermate.csv e percorsi.json
	$(PYTHON) scripts/build_gtfs.py $(GTFS)

geocode: ## Geocoding fermate + tracciati stradali, poi rigenera il GTFS
	$(PYTHON) scripts/geocode_stops.py $(GTFS) --forme
	$(PYTHON) scripts/build_gtfs.py $(GTFS)

clean: ## ATTENZIONE: ferma tutto e cancella i volumi (modelli Ollama)
	$(COMPOSE) --profile llm --profile test down -v --remove-orphans
