---
title: Installazione
description: Avviare QuandoPassa con Docker o su una macchina virtuale Linux, requisiti minimi, test e istanza demo.
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
| `make up` | Costruisce e avvia app, inferenza e MCP (e Postgres, se il backoffice è attivo) |
| `make backoffice` | Attiva il [backoffice](backoffice.md): chiede utente e password, prepara Postgres e avvia |
| `make password` | Hash di una nuova password del backoffice |
| `make up-llm` | Come `up`, con un LLM locale (Ollama, profilo `llm`) |
| `make down` | Ferma i container |
| `make logs S=app` | Log di un servizio |
| `make test` | Suite pytest nel container |
| `make demo` | Istanza demo su :8001 con orologio fisso |
| `make gtfs` / `make geocode` | Rigenera il feed / geocoding e tracciati |
| `make docs` | Anteprima di questo sito su http://127.0.0.1:8002 |

Dopo ogni modifica al `.env`: `make up` (ricrea i container).

## Su una macchina virtuale Linux, senza Docker

Per le VM dove Docker non è ammesso o non è disponibile c'è uno script di installazione chiavi in mano.
Supporta **Debian 12+, Ubuntu 22.04+, RHEL / Rocky / AlmaLinux 8+ e Fedora**, su x86_64 e arm64, con systemd.

### Requisiti minimi

| | Solo app pubblica | Con backoffice (Postgres) | Con LLM locale (`--llm`) |
|---|---|---|---|
| CPU | 1 vCPU | 2 vCPU | 4 vCPU |
| RAM | 2 GB (1 GB basta dopo l'installazione) | 2 GB | 8 GB |
| Disco | 10 GB | 20 GB (backup compresi) | 30 GB |

- Sistema operativo a 64 bit con systemd: Debian 12 o 13, Ubuntu 22.04 o 24.04 LTS, RHEL / Rocky / AlmaLinux 8
  o 9, Fedora. Meglio un'installazione pulita, senza altri siti web sulla porta 80.
- Un utente con `sudo`.
- Accesso a internet **durante l'installazione** (pacchetti della distribuzione, librerie Python da PyPI,
  Node.js da nodejs.org e pacchetti npm); dopo, l'app funziona anche senza, salvo le tile della mappa che il
  browser scarica dal fornitore configurato.
- Porte 80 e 443 raggiungibili dagli utenti; per HTTPS un nome DNS che punta alla VM.

### Installare

```bash
git clone https://github.com/gzileni/quandopassa.git
cd quandopassa
sudo ./deploy/install.sh                       # app su http://IP-della-VM (nginx sulla porta 80)
sudo ./deploy/install.sh --backoffice          # + backoffice /admin con Postgres e backup giornaliero
```

Con un nome pubblico e il certificato HTTPS di Let's Encrypt (il DNS deve già puntare alla VM e la porta 80
deve essere raggiungibile):

```bash
sudo ./deploy/install.sh --dominio bus.comune.example.it --email it@comune.example.it
```

Lo script installa i pacchetti di sistema, Python ≥ 3.11 (quello della distribuzione oppure, se è più vecchio
come su Ubuntu 22.04, una build scaricata con `uv`), usa Node.js 22 solo per costruire l'interfaccia (scaricato
con verifica SHA-256 e poi rimosso), crea l'utente di sistema `quandopassa` e i servizi systemd, configura
nginx e il firewall, e alla fine controlla che tutto risponda.

| Dove | Cosa |
|---|---|
| `/opt/quandopassa` | Codice (di proprietà di root, in sola lettura per il servizio), ambiente Python `.venv`, interfaccia costruita |
| `/etc/quandopassa/quandopassa.env` | Configurazione: stesse variabili del `.env` di Docker ([Configurazione](configurazione.md)) |
| `/etc/quandopassa/install.conf` | Le scelte fatte con le opzioni, riusate quando lo script viene rilanciato |
| `quandopassa-app`, `-inference`, `-mcp` (e `-demo`) | Servizi systemd raccolti in `quandopassa.target`, non-root, con hardening |
| `/etc/nginx/conf.d/quandopassa.conf` | Reverse proxy con rate limiting sulle API e log senza query string (niente coordinate) |
| `/var/log/quandopassa-install.log` | Log dell'installazione |
| `/var/lib/quandopassa` | Con `--backoffice`: feed generato, impostazioni e logo (scrivibile solo dal servizio) |
| database `quandopassa` | Con `--backoffice`: Postgres locale, accesso dal socket per l'utente di sistema, senza password |
| `/var/backups/quandopassa` | Con `--backoffice`: backup notturno di database e dati, ultimi 14 giorni |

Le porte restano le stesse della versione Docker: app su `127.0.0.1:8000` dietro nginx, inferenza su
`127.0.0.1:8080`, MCP su `127.0.0.1:8090`; dall'esterno è aperta solo la porta 80 (e 443 con HTTPS).

**Opzioni** (`sudo ./deploy/install.sh --aiuto` per l'elenco completo):

| Opzione | Effetto |
|---|---|
| `--dominio NOME` | nginx risponde a quel nome e `BASE_URL` diventa `http(s)://NOME` |
| `--email INDIRIZZO` | con `--dominio`: certificato HTTPS Let's Encrypt e redirect da HTTP |
| `--backoffice` / `--senza-backoffice` | attiva o spegne il [backoffice](backoffice.md): Postgres locale, password (chiesta, o generata e mostrata una volta), backup notturno |
| `--utente-admin NOME` | nome dell'utente del backoffice (predefinito `editor`) |
| `--admin-da RETE` | apre `/admin` solo dalla rete indicata, es. `10.0.0.0/8` (ripetibile) |
| `--senza-nginx` | niente reverse proxy: l'app ascolta direttamente su `0.0.0.0:8000` |
| `--llm` / `--senza-llm` | installa Ollama con il modello di `LLM_MODEL` e usa `INFERENCE_BACKEND=openai` / torna al motore a regole |
| `--demo` / `--senza-demo` | istanza demo con orologio fisso su `127.0.0.1:8001` |
| `--prefisso DIR` | cartella di installazione diversa da `/opt/quandopassa` |
| `--salta-pacchetti` | non installa pacchetti di sistema (VM senza accesso ai repository) |
| `--disinstalla` | rimuove servizi, codice, utente e sito nginx; configurazione, dati, backup e database restano |

**Gestione quotidiana** con il comando `quandopassa`:

```bash
sudo quandopassa stato          # stato dei servizi
sudo quandopassa log app        # log in tempo reale (app, inference, mcp, demo)
sudo quandopassa config         # modifica la configurazione e riavvia
sudo quandopassa riavvia
sudo quandopassa password       # nuova password del backoffice
sudo quandopassa backup         # backup subito (oltre a quello notturno)
quandopassa salute              # GET /api/v1/health
```

**Aggiornare**: `git pull` nel clone e rilanciare `sudo ./deploy/install.sh`. Codice, dipendenze e interfaccia
vengono ricostruiti; configurazione, dati del backoffice e scelte restano. Per riusare il servizio con un **feed GTFS proprio**,
metterlo fuori da `/opt/quandopassa` (es. `/srv/quandopassa/gtfs`) e indicarlo con un percorso assoluto in
`GTFS_DIR`: la cartella `/opt/quandopassa/data` viene riallineata al repository a ogni aggiornamento.

Lo script si può lanciare anche senza clone: in quel caso scarica il repository (`--repo`, `--ref`).

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
API, assistente, server di inferenza, server MCP e backoffice. I test del backoffice usano un Postgres usa e
getta (`make test` lo avvia da solo; in locale serve `TEST_DATABASE_URL`, altrimenti vengono saltati). La CI su
GitHub esegue anche la build dell'interfaccia e delle immagini.

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
- Senza backoffice non ci sono database né segreti applicativi. Con il backoffice: proteggere il `.env`
  (hash della password, chiave delle sessioni, connessione al database), pubblicare `/admin` solo in HTTPS,
  meglio solo dalla rete dell'ente, e conservare i backup. L'app non salva comunque dati dei cittadini.
