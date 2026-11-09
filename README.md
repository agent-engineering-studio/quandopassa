# QuandoPassa

**Il bus urbano sulla mappa, senza mettere un GPS sui bus.** QuandoPassa legge l'orario ufficiale in formato GTFS
e mostra dove si trova ogni bus *secondo l'orario*, qual è la fermata più vicina, tra quanti minuti arriva il
prossimo bus e se fai in tempo a prenderlo. Con un assistente IA in italiano e un server MCP per altri agenti.
Open source (EUPL-1.2), riusabile da qualsiasi Comune con un feed GTFS.
Pilota proposto: servizio urbano di **Gioia del Colle**, Circolari A e B.

📖 **Documentazione completa:** https://gzileni.github.io/quandopassa/

![Demo](docs/demo/quandopassa-demo.gif)

> Proposta indipendente, non un servizio ufficiale del Comune. Le posizioni dei bus sono **stime dall'orario
> programmato** (non c'è un GPS a bordo) e l'app lo dichiara sempre. La demo usa un orologio fisso su un mercoledì
> mattina.

Il README è diviso in tre parti: **[Cittadini](#1-per-i-cittadini)** ·
**[Comune](#2-per-il-comune)** · **[Sviluppatori e ufficio IT](#3-per-sviluppatori-e-ufficio-it)**.

---

## 1. Per i cittadini

Una pagina web, dal telefono o dal computer: niente app da installare, niente registrazione.

| Cosa fai | Cosa ottieni |
|---|---|
| Apri la mappa | I bus in servizio che si muovono lungo le strade, con linea e direzione |
| Tocchi **Usa la mia posizione** | Le fermate più vicine, i minuti a piedi e per ogni bus "fai in tempo", "affrettati" o "non fai in tempo" |
| Apri una fermata | Il **bus in arrivo**: tra quanti minuti, a quante fermate e quanti metri, dov'è adesso |
| Apri **Come arrivo** e scegli partenza e arrivo | Come su un navigatore: quanto camminare, quale bus, **dove cambiare**, a che ora arrivi; il viaggio sulla mappa |
| Chiedi all'**assistente** *"come arrivo al cimitero?"* | La stessa risposta, in italiano |
| Compri un **biglietto** (prototipo) | Corsa, carnet o abbonamento senza registrazione; lo attivi alla salita e mostri codice e QR |

**Onestà sui dati.** Senza GPS a bordo il ritardo non è misurabile: l'app scrive "Ritardo: non rilevabile"
invece di un "in orario" che non può verificare. La posizione resta sul telefono e non viene salvata.

**Come arrivo** — da una fermata, un indirizzo, un luogo o un punto sulla mappa:

![Come arrivo](docs/demo/quandopassa-come-arrivo.gif)

→ [Guida per i cittadini](https://gzileni.github.io/quandopassa/cittadini/) ·
[video verticale](docs/demo/quandopassa-demo-verticale.mp4) ·
[video "come arrivo" verticale](docs/demo/quandopassa-come-arrivo-verticale.mp4)

---

## 2. Per il Comune

| Beneficio | Come |
|---|---|
| **Nessun hardware** | Niente apparati AVM/GPS, SIM o centrale: basta l'orario in GTFS. |
| **Nessun dato personale** | Nessun account; posizione e ricerche non salvate; i biglietti sono anonimi; l'assistente non riceve dati personali. |
| **Design della PA** | Interfaccia [Bootstrap Italia](https://italia.github.io/bootstrap-italia/) responsive e accessibile, font e icone in locale, nessuna CDN di terzi. |
| **Pensiline** | Le fermate sono le 20 aree della proposta di localizzazione delle pensiline, geocodificate su OpenStreetMap. |
| **IA sotto controllo** | Uso informativo a basso rischio (AI Act art. 50), motore predefinito offline, orari mai inventati dal modello. |
| **Dati aperti e integrazione** | Feed GTFS standard, API JSON aperte e server MCP. |
| **Biglietti digitali** | Prototipo con tariffe nel `.env`, acquisto anonimo, QR firmato e verifica a bordo; il venditore (Comune con pagoPA o gestore) si sceglie con un adattatore. |
| **Riuso** | Un altro Comune cambia il feed GTFS e il file `.env`; codice EUPL-1.2 con `publiccode.yml`. |

Evoluzione naturale: con un feed **GTFS-Realtime** dell'azienda di trasporto, posizioni e ritardi veri al posto
delle stime.

**Pronto per il riuso nella PA.** Licenza EUPL-1.2, `publiccode.yml` verificato dai test, `CONTRIBUTING.md`,
`SECURITY.md`, `CHANGELOG.md`; dipendenze senza vulnerabilità note (`pip-audit`, `npm audit`); audit di
accessibilità axe-core senza violazioni WCAG 2.1 AA (`make accessibilita`); posizione e ricerche mai salvate né
scritte nei log.

→ [Benefici per il Comune](https://gzileni.github.io/quandopassa/comune/) ·
[Il feed GTFS e le fermate](https://gzileni.github.io/quandopassa/gtfs/) ·
[Biglietti digitali](https://gzileni.github.io/quandopassa/biglietti/) ·
[Conformità normativa](https://gzileni.github.io/quandopassa/conformita/) ·
[Riuso e Catalogo Developers Italia](https://gzileni.github.io/quandopassa/riuso/)

---

## 3. Per sviluppatori e ufficio IT

```bash
make up          # crea .env da .env.example, costruisce e avvia
# app       http://localhost:8000      (API: /api/docs)
# MCP       http://localhost:8090/mcp
make demo        # istanza demo su :8001 con orologio fisso (mercoledì 09:00)
make test        # suite pytest nel container
```

Tre container; l'unico archivio è quello anonimo dei biglietti (SQLite su volume):

- **app** (`api/` + `web/`): FastAPI con il motore GTFS (posizioni stimate, partenze, fermate vicine, ricerca),
  il calcolo degli itinerari con cambi (`itinerari.py`), la ricerca dei luoghi su OpenStreetMap e l'assistente; interfaccia React con Vite, Bootstrap Italia e Leaflet su OpenStreetMap.
  L'interfaccia scarica una volta l'orario del giorno e anima i bus da sola, allineata all'ora del server.
- **inference** (`inference/`): server OpenAI-compatibile, backend `rules` (offline, predefinito) o `openai`
  (Ollama del profilo `llm`, vLLM, Azure OpenAI…). L'IA capisce la domanda, l'app calcola la risposta, l'LLM può
  solo riformularla: una riformulazione con numeri diversi viene scartata.
- **mcp** (`mcp_server/`): server MCP in sola lettura con `cerca_fermata`, `fermate_vicine`,
  `prossime_partenze`, `bus_in_servizio`, `come_arrivare`, `orari_linea`, `tariffe_biglietti`, `chiedi_assistente`.

Il feed è nella cartella `GTFS_DIR` (predefinita `data/`): `fermate.csv` e `percorsi.json` sono le sorgenti,
`make gtfs` rigenera i file GTFS e `make geocode` cerca le fermate su OpenStreetMap e i tracciati stradali con
OSRM (lo fa anche il workflow **geocoding** a ogni modifica).

→ [Installazione](https://gzileni.github.io/quandopassa/installazione/) ·
[Configurazione](https://gzileni.github.io/quandopassa/configurazione/) ·
[Architettura e API](https://gzileni.github.io/quandopassa/architettura/) ·
[Intelligenza artificiale](https://gzileni.github.io/quandopassa/intelligenza-artificiale/) ·
[Server MCP](https://gzileni.github.io/quandopassa/mcp/) ·
[Installazione conforme PA](https://gzileni.github.io/quandopassa/normativa-it/) ·
[Video e demo](https://gzileni.github.io/quandopassa/video/)

---

## Licenza

EUPL-1.2 · Agent Engineering Studio e contributori.
