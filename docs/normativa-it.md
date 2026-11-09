---
title: Installazione conforme per la PA
description: Checklist per l'ufficio IT per mettere in esercizio QuandoPassa secondo le norme ICT della Pubblica Amministrazione.
---

# Installazione conforme per la PA

Questa pagina è per l'**ufficio IT** e il **Responsabile per la transizione digitale (RTD)**. Elenca, norma per
norma, cosa fa già il software e cosa resta da fare in fase di installazione e messa in esercizio.

!!! warning "Da validare"
    La checklist è un supporto tecnico. Classificazione dei dati, valutazioni d'impatto e atti formali vanno
    confermati con RTD, RPD e Segretario comunale.

## Checklist

| Ambito | Riferimento | Cosa fa il software | Cosa fa l'IT all'installazione |
|---|---|---|---|
| **Riuso e open source** | CAD artt. 68-69; Linee guida AgID su acquisizione e riuso | Licenza EUPL-1.2, `publiccode.yml` | Valutazione comparativa ex art. 68 nell'atto di adozione; pubblicazione su Developers Italia |
| **Cloud** | Regolamento ACN per le infrastrutture e i servizi cloud della PA | Tre container Docker, archivio SQLite dei biglietti su volume, nessun servizio esterno obbligatorio | Ospitare su infrastruttura o servizio cloud **qualificato ACN** |
| **Design** | Linee guida di design per i servizi digitali della PA | Bootstrap Italia 2.18.3 impacchettato con l'app | Link dalla sezione trasporti del portale del Comune |
| **Accessibilità** | L. 4/2004; Linee guida AgID; WCAG 2.1 AA / EN 301 549 | Audit axe-core senza violazioni, tastiera e screen reader | Test con utenti; **dichiarazione di accessibilità** su form.agid.gov.it |
| **Protezione dati** | GDPR artt. 5, 25, 28, 30, 32 | Nessun account, database o cookie; posizione e domande non salvate né nei log | Registro dei trattamenti, informativa validata dal RPD, conservazione dei log, fornitore delle tile |
| **Sicurezza ICT** | Misure minime di sicurezza ICT per le PA (circolare AgID 2/2017) | Container non-root, inferenza non esposta, MCP in sola lettura su localhost | HTTPS, rate limiting, aggiornamenti, backup della configurazione, vulnerability assessment |
| **Dati aperti e interoperabilità** | CAD art. 50; Linee guida AgID sull'interoperabilità | Feed GTFS, API REST in OpenAPI (`/api/docs`), server MCP | Pubblicare il feed sul portale open data; valutare PDND se le API servono ad altri enti |
| **Pagamenti (biglietti)** | CAD art. 5; Linee guida pagoPA; contratto di servizio TPL | Adattatore `PAGAMENTI` (simulato, pagoPA, gestore), titolo emesso solo a pagamento riuscito | Decidere chi vende; completare l'adattatore; trattamento fiscale con la ragioneria |
| **Intelligenza artificiale** | AI Act (Reg. UE 2024/1689) art. 50; L. 132/2025; Linee guida AgID per l'IA nella PA | Trasparenza in interfaccia, orari calcolati dal codice, redazione dei dati personali, backend tracciato | Valutazione d'impatto prima di attivare un LLM; registro dei sistemi IA dell'ente |

## Messa in esercizio passo per passo

### 1. Infrastruttura

- Una VM o un servizio container su cloud **qualificato ACN**: 1 vCPU e 1 GB di RAM bastano per app, motore a
  regole e MCP. Un LLM locale (`make up-llm`) richiede almeno 4 vCPU e 8 GB di RAM.
- Docker Engine e Compose v2, con aggiornamenti di sicurezza automatici del sistema operativo.

### 2. Rete e HTTPS

Mettere un reverse proxy davanti all'app, con TLS 1.2 o superiore e certificato valido. Pubblicare **solo** la
porta dell'app: inferenza e Ollama restano sulla rete interna, il server MCP su `127.0.0.1`.

```nginx
server {
  listen 443 ssl http2;
  server_name bus.comune.example.it;
  ssl_protocols TLSv1.2 TLSv1.3;
  add_header Strict-Transport-Security "max-age=31536000" always;
  limit_req zone=bus burst=30 nodelay;     # rate limiting

  location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  }
}
```

Anche nei log del reverse proxy la query string contiene le coordinate: escluderla dal formato di log
(ad esempio usando `$uri` invece di `$request`).

### 3. Configurazione

```bash
cp .env.example .env && chmod 600 .env
# BASE_URL=https://bus.comune.example.it
# COMUNE_NOME, SERVIZIO_NOME, MAPPA_CENTRO, INFO_BIGLIETTI (testo ufficiale)
# MAPPA_TILES: tile server proprio o fornitore con accordo
# LUOGHI_GEOCODER: istanza Nominatim dell'ente o fornitore con accordo (vuoto = solo fermate)
# DEMO_ORA vuoto (ora reale)
make up
```

### 4. Tile della mappa

Le tile vengono scaricate dal browser del cittadino: il fornitore vede l'indirizzo IP e la zona della mappa.
La policy dei tile pubblici di OpenStreetMap non consente un uso intensivo. In esercizio usare un tile server
dell'ente o un fornitore con nomina a responsabile del trattamento.

### 5. Log, monitoraggio e aggiornamenti

- Healthcheck: `GET /api/v1/health` (app) e `GET /health` (inferenza), già usati dai container.
- I log di accesso dell'app non contengono coordinate né domande; conservare IP e percorsi per il tempo
  stabilito con il RPD.
- Aggiornare con regolarità immagini e dipendenze (`pip-audit`, `npm audit`) e rigenerare il feed GTFS quando
  cambia l'orario.

### 6. Prima dell'avvio

- [ ] HTTPS attivo, MCP e inferenza non esposti
- [ ] `DEMO_ORA` vuoto e feed GTFS aggiornato e valido per le date di esercizio
- [ ] Coordinate delle fermate confermate dal sopralluogo (`fonte=manuale`)
- [ ] Fornitore delle tile e del geocoder scelti
- [ ] Biglietti: `PAGAMENTI` reale o vendita disattivata (`BIGLIETTI_ATTIVI=false`), segreto e credenziali robusti, backup del volume `biglietti`
- [ ] Registro dei trattamenti e informativa approvati dal RPD
- [ ] Dichiarazione di accessibilità pubblicata
- [ ] Valutazione d'impatto IA (se si attiva un LLM)
- [ ] `publiccode.yml` aggiornato
