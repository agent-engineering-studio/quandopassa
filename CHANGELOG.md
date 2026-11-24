# Changelog

Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/) e il versionamento [SemVer](https://semver.org/lang/it/).

## [Non rilasciato]

### Aggiunto
- **Bike sharing** nel backoffice: sistemi (gestore, link all'app per il noleggio, feed), stazioni sulla mappa
  con le fermate del bus vicine, import da feed **GBFS** v2.x/v3.0 (URL o file JSON/zip) con anteprima delle
  modifiche; le stazioni modificate a mano non vengono sovrascritte. Disponibilità di bici e stalli letta lato
  server da `station_status` con cache sul `ttl`. API pubbliche `/api/v1/bikes/stations` e `/api/v1/bikes/nearby`,
  `bikes_nearby` nella scheda della fermata, `bike_sharing` in `/info`.
- **Backoffice** `/admin` per l'ufficio trasporti (React + Vite, Bootstrap Italia): fermate sulla mappa,
  linee con percorso, minuti e partenze, calendari ed eccezioni, agenzia e validità del feed, intestazione
  dell'app (logo, ente, titolo), impostazioni di mappa, ricerca e biglietti, registro delle modifiche.
  Dati in **Postgres**; a ogni salvataggio il feed GTFS viene rigenerato, verificato e ricaricato senza
  riavvio (una modifica che renderebbe il feed non valido non viene salvata); export GTFS in zip.
  Sempre attivo: utente e password nel `.env` (`ADMIN_USER`, `ADMIN_PASSWORD`, completati da `make env`),
  cookie di sessione firmato, CSRF, blocco dopo 5 tentativi; `make password`; Postgres nel docker compose.
- **Avvisi di servizio**: fermate sospese, deviazioni temporanee con percorso provvisorio, giorni di servizio
  sospeso (diventano `calendar_dates` nel GTFS), informazioni. Nell'app: barra degli avvisi, fermata sospesa
  in rosso, partenze segnate, itinerari che evitano le fermate sospese; API `GET /api/v1/alerts`.
- L'app pubblica si accorge di un nuovo feed entro due minuti e si aggiorna da sola.
- Video del backoffice (16:9 e GIF) e screenshot di backoffice e avvisi (`registra_demo.py --backoffice`);
  video e screenshot dell'app rigenerati. Alla fermata sospesa il riquadro "Bus in arrivo" lascia il posto
  all'avviso che i bus non fermano.
- Installazione **senza Docker** su VM Linux (`deploy/install.sh`): Debian, Ubuntu, RHEL/Rocky/Alma, Fedora;
  servizi systemd non-root con hardening, nginx con rate limiting e log senza coordinate, HTTPS Let's Encrypt,
  firewall, backoffice con Postgres locale e backup notturno (`--admin-da`), LLM locale
  opzionale, istanza demo, aggiornamento e disinstallazione; comando `quandopassa`. Requisiti minimi nel README.
- Pulsante **Acquista il biglietto** verso la biglietteria online dell'azienda di trasporto (`LINK_BIGLIETTI`,
  `BIGLIETTERIA_NOME`): QuandoPassa non vende biglietti né gestisce pagamenti.
- **Come arrivo**: itinerari porta a porta da fermate, indirizzi, luoghi (OpenStreetMap) o punti sulla mappa,
  con tratti a piedi, bus e un cambio, disegnati sulla mappa; "solo a piedi" quando conviene; "Portami qui" dalla
  scheda della fermata. API `/itinerari` e `/luoghi`; assistente e strumento MCP `come_arrivare` usano lo stesso
  calcolo. Video dedicato (16:9, 9:16, GIF).
- Audit di accessibilità ripetibile (`make accessibilita`, axe-core).
- Riquadro "Bus in arrivo" nella scheda della fermata: minuti stimati, fermate e metri mancanti, posizione
  attuale; il ritardo è dichiarato non rilevabile.
- Istanza demo con orologio fisso, video dimostrativi (16:9, 9:16, GIF) e screenshot generati con Playwright.
- Sito di documentazione su GitHub Pages (Zensical) e README in tre parti.
- Guida al riuso e alla pubblicazione nel Catalogo Developers Italia, matrice di conformità e checklist di
  installazione conforme per la PA.
- `CONTRIBUTING.md`, `SECURITY.md`, questo changelog e il test di validità di `publiccode.yml`.

### Modificato
- La generazione del GTFS (`scripts/build_gtfs.py`) è nel pacchetto dell'app (`quandopassa/sources.py`) e
  supporta varianti delle linee (`id`), direzione ed eccezioni dei calendari.
- Interfaccia rifatta con Bootstrap Italia 2.18.3, responsive, senza CDN di terzi.
- L'interfaccia segue sempre l'ora reale; la simulazione resta solo nell'istanza demo.
- Linee sulla mappa lungo i tracciati stradali (OSRM) e fermate geocodificate su OpenStreetMap.
- Colore della Circolare A scurito (`#1864AB`) per il contrasto WCAG AA con il testo bianco.

### Rimosso
- Recensioni di fermate, linee e servizio, area di moderazione dell'ufficio e database PostgreSQL.

### Sicurezza
- I log di accesso non registrano più coordinate (`lat`, `lon`, `da_lat`…), il testo delle domande né le ricerche di luoghi.
- `bandit`: identificativo dei tracciati con SHA1 dichiarato non crittografico; geocoding limitato a URL https.

## [0.1.0] – 2026-11-09

Prima versione: posizioni dei bus stimate dall'orario GTFS, fermate vicine con "fai in tempo", assistente IA,
server di inferenza, server MCP, Docker Compose.
