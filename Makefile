# QuandoPassa – comandi rapidi per docker compose.  `make` da solo mostra l'elenco.

COMPOSE ?= docker compose
PYTHON  ?= python3
GTFS    ?= data
# servizio per logs/shell, es.  make logs S=app
S       ?=
# con il backoffice configurato nel .env si avvia anche Postgres (profilo "backoffice")
PROFILI := $(shell grep -qE '^ADMIN_USER=.+' .env 2>/dev/null && echo --profile backoffice)

.DEFAULT_GOAL := help
.PHONY: help env build build-nocache up up-llm down restart ps logs shell test gtfs geocode demo video accessibilita docs clean backoffice password

help: ## Mostra questo elenco
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n",$$1,$$2}'

env: ## Crea .env da .env.example (se manca)
	@test -f .env && echo ".env esiste già" || (cp .env.example .env && chmod 600 .env && echo "creato .env: rivedere i valori")

build: env ## Costruisce le immagini (app, inference, mcp)
	$(COMPOSE) build

build-nocache: env ## Costruisce le immagini senza cache
	$(COMPOSE) build --no-cache --pull

up: env ## Avvia app + inferenza + MCP (http://localhost:8000)
	$(COMPOSE) $(PROFILI) up -d --build --force-recreate --remove-orphans
	@echo "app: http://localhost:8000   MCP: http://localhost:8090/mcp"
	@test -z "$(PROFILI)" || echo "backoffice: http://localhost:8000/admin/"

backoffice: env ## Attiva il backoffice /admin: chiede utente e password, configura Postgres e avvia
	$(PYTHON) scripts/backoffice_env.py .env
	$(COMPOSE) --profile backoffice up -d --build --force-recreate --remove-orphans
	@echo "backoffice: http://localhost:8000/admin/"

password: ## Stampa l'hash di una nuova password del backoffice (da mettere in ADMIN_PASSWORD_HASH)
	@cd api && $(PYTHON) -m quandopassa.password

up-llm: env ## Come up, con LLM locale Ollama (profilo llm)
	$(COMPOSE) --profile llm up -d --build --force-recreate

down: ## Ferma e rimuove i container (i volumi restano)
	$(COMPOSE) --profile llm --profile test --profile backoffice down

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

demo: env ## Istanza demo su :8001 con orologio fisso (mercoledì 11/11/2026, 09:00)
	$(COMPOSE) --profile demo up -d --build demo
	@echo "demo: http://localhost:8001"

video: ## Video (demo e come arrivo, 16:9 e 9:16) e screenshot in docs/ (serve make demo, playwright e ffmpeg)
	$(COMPOSE) --profile demo restart demo && sleep 4
	$(PYTHON) scripts/registra_demo.py
	$(COMPOSE) --profile demo restart demo && sleep 4
	$(PYTHON) scripts/registra_demo.py --verticale
	$(COMPOSE) --profile demo restart demo && sleep 4
	$(PYTHON) scripts/registra_demo.py --percorso
	$(COMPOSE) --profile demo restart demo && sleep 4
	$(PYTHON) scripts/registra_demo.py --percorso --verticale
	$(COMPOSE) --profile demo restart demo && sleep 4
	$(PYTHON) scripts/registra_demo.py --screenshot

accessibilita: ## Audit axe-core WCAG 2.1 AA di tutte le schede sull'istanza demo (serve make demo e playwright)
	$(PYTHON) scripts/audit_accessibilita.py

docs: ## Anteprima del sito di documentazione su http://127.0.0.1:8002 (serve zensical)
	zensical serve -a 127.0.0.1:8002

clean: ## ATTENZIONE: ferma tutto e cancella i volumi (modelli Ollama, database e dati del backoffice)
	$(COMPOSE) --profile llm --profile test --profile backoffice down -v --remove-orphans
