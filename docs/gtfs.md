---
title: Il feed GTFS e le fermate
description: Da dove vengono orari, fermate e percorsi, come si rigenerano e come si usa un altro feed.
---

# Il feed GTFS e le fermate

QuandoPassa legge un feed **GTFS statico** (General Transit Feed Specification): file di testo con fermate,
linee, corse, orari, calendari e, se c'è, il tracciato stradale (`shapes.txt`). La cartella è indicata da
`GTFS_DIR` nel `.env` (predefinita: `./data`).

## Il feed del pilota

La cartella `data/` contiene il feed generato dalla proposta preliminare di localizzazione delle pensiline
(Circolari A e B, 20 aree, documento del 9/11/2026). Le sorgenti modificabili a mano sono due:

`fermate.csv`
:   le fermate: area, nome, linee, tipologia (pensilina o fermata leggera), nota, strategia di ricerca per il
    geocoding, coordinate e loro fonte.

`percorsi.json`
:   agenzia, calendari, sequenza delle fermate per linea con i minuti di percorrenza e le partenze dal
    capolinea. Tempi e partenze vengono dal template GTFS Sabato Viaggi, tenendo solo le fermate della proposta.

L'area 20 (Via Federico II di Svevia) ha due punti di fermata, lato zona produttiva e lato Villaggio Azzurro,
perché la Circolare B la percorre prima e dopo Seven. La Circolare A ordinaria non circola il martedì (giorno di
mercato, con un percorso diverso che la proposta non copre).

```bash
make gtfs       # rigenera i file .txt da fermate.csv e percorsi.json
make geocode    # geocoding delle fermate + tracciati stradali, poi rigenera il feed
```

## Geocoding e tracciati stradali

Per ogni fermata `scripts/geocode_stops.py` prova in ordine le strategie della colonna `ricerca`:

- `incrocio:Via A|Via B` cerca su OpenStreetMap (Overpass) il nodo in comune tra due strade;
- il testo libero usa Nominatim, limitato al territorio comunale.

Poi chiede a OSRM il percorso stradale di ogni linea attraverso le sue fermate e lo scrive in `forme.json`,
da cui nasce `shapes.txt`: così le linee sulla mappa **seguono le strade** invece di unire le fermate in linea
retta, e i bus si muovono lungo il percorso vero.

Il workflow GitHub **geocoding** lo fa da solo a ogni modifica di `fermate.csv` o `percorsi.json` e fa il
commit dei file aggiornati. Rispetta le policy d'uso dei servizi OpenStreetMap (una richiesta al secondo,
User-Agent identificativo).

!!! tip "Dopo il sopralluogo"
    Le posizioni da OpenStreetMap sono **indicative**: i corridoi con più strade vanno fissati sul posto.
    Basta scrivere `lat`, `lon` e `fonte=manuale` in `fermate.csv`: il geocoding non tocca più quella riga.
    Finché una fermata non ha coordinate, l'app la mostra in posizione provvisoria, con il bordo tratteggiato
    e un avviso.

## Usare un altro feed

Un altro Comune può usare qualsiasi feed GTFS esistente:

1. copiare i file in una cartella, per esempio `data/altro`;
2. scrivere `GTFS_DIR=./data/altro` nel `.env`;
3. aggiornare `COMUNE_NOME`, `SERVIZIO_NOME` e `MAPPA_CENTRO`;
4. riavviare: `make up`.

Le colonne extra di questo repository (`posizione` in `stops.txt`) sono facoltative. Se il feed non ha
`shapes.txt`, i bus si muovono lungo la spezzata tra le fermate.
