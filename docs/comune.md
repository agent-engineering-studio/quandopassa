---
title: Benefici per il Comune
description: Perché QuandoPassa conviene a un piccolo Comune senza sistema AVM/GPS sui bus.
---

# Benefici per il Comune

I sistemi di localizzazione dei bus (AVM) richiedono apparati a bordo, connettività, una centrale e contratti di
manutenzione: costi fuori portata per un servizio urbano di due linee. QuandoPassa parte da quello che il Comune
e l'azienda hanno già, **l'orario**, e lo trasforma in un servizio informativo moderno.

| Beneficio | Come |
|---|---|
| **Nessun hardware** | Niente GPS, SIM o centrale: le posizioni sono stimate dall'orario GTFS lungo il percorso stradale. |
| **Informazione al cittadino** | Mappa, fermata più vicina, bus in arrivo, "fai in tempo" e assistente in italiano, dal telefono. |
| **Nessun dato personale** | Nessun account e nessun database: la posizione resta sul telefono, l'assistente non riceve dati personali. |
| **Design della PA** | Interfaccia [Bootstrap Italia](https://italia.github.io/bootstrap-italia/) (Designers Italia), accessibile, con font e icone in locale: nessuna CDN di terzi. |
| **Dati aperti** | Il feed GTFS è uno standard: lo stesso file alimenta QuandoPassa, Google Maps, Moovit e i portali open data. |
| **Pensiline** | Le fermate sono le 20 aree della proposta di localizzazione delle pensiline: la mappa aiuta a discuterle e verificarle. |
| **IA sotto controllo** | Uso informativo a basso rischio, dichiarato (AI Act art. 50); motore predefinito offline, nessun dato a terzi. |
| **Integrazione** | API JSON aperte e un server MCP: lo stesso servizio può rispondere dentro altri assistenti e portali. |
| **Riuso** | Codice EUPL-1.2 con `publiccode.yml`: un altro Comune cambia il feed GTFS e il file `.env`. |

## Cosa serve per partire

1. **L'orario in GTFS.** Per il pilota il feed è già nel repository (Circolari A e B, generato dalla proposta
   delle 20 aree e dai tempi del template Sabato Viaggi). Un Comune che ha già un feed lo copia nella cartella
   indicata da `GTFS_DIR`. Vedi [Il feed GTFS e le fermate](gtfs.md).
2. **Le coordinate delle fermate.** Il geocoding da OpenStreetMap dà posizioni indicative; dopo il sopralluogo
   si scrivono quelle rilevate e restano fisse.
3. **Un server.** Tre container Docker, nessun database: una piccola macchina virtuale basta. Vedi
   [Installazione](installazione.md).

## Limiti dichiarati

- **Stime, non rilevazioni.** Se il bus è in ritardo o devia, la mappa non lo sa. L'app lo dice sempre e indica
  il ritardo come "non rilevabile".
- **Posizioni delle fermate indicative** finché non c'è il sopralluogo.
- **Solo viaggi diretti** nel calcolo "come arrivo": senza cambi di linea.

## Evoluzioni possibili

- **Ritardi reali con GTFS-Realtime.** Se l'azienda di trasporto pubblica un feed GTFS-Realtime (anche da un
  semplice tracker sul bus), QuandoPassa può mostrare posizioni e ritardi veri al posto delle stime.
- **Avvisi di servizio** (deviazioni, mercato del martedì, scioperi) gestiti dall'ufficio.
- **Pubblicazione del feed** sul portale open data del Comune e sul catalogo nazionale.
