---
title: Riuso e Catalogo Developers Italia
description: Come pubblicare QuandoPassa nel Catalogo del software della PA e come un altro Comune può adottarlo.
---

# Riuso e Catalogo Developers Italia

Come pubblicare QuandoPassa nel Catalogo del software della PA e come un altro Comune può adottarlo. Le
indicazioni seguono le stesse fonti istituzionali usate per [Spazio Comune](https://github.com/agent-engineering-studio/spazio-comune),
elencate in fondo.

## Due percorsi di pubblicazione

**Oggi: software open source di terze parti.** Il codice non è di proprietà di una PA, quindi entra nel Catalogo
come software di interesse pubblico sviluppato da terzi. La guida "Pubblicare software per la PA" di Developers
Italia chiede il file `publiccode.yml` nel repository, con il campo `codiceIPA` vuoto, e una segnalazione sul
repository GitHub del Catalogo con il modello "add new software".

**Domani: software a riuso.** Se un Comune adotta QuandoPassa e ne diventa titolare (art. 69 CAD), lo dichiara con
l'onboarding di Developers Italia registrando il proprio spazio di code hosting. A quel punto `codiceIPA` riporta
il codice IPA dell'ente (per Gioia del Colle `c_e038`) e gli enti che lo usano compaiono in `usedBy`.

## Checklist di pubblicazione

- [x] Repository pubblico: `github.com/gzileni/quandopassa`
- [x] Licenza EUPL-1.2, raccomandata dalla guida per la PA
- [x] README, documentazione tecnica e istruzioni di installazione (questo sito)
- [x] `CONTRIBUTING.md`, `CHANGELOG.md`, `SECURITY.md`
- [x] Dipendenze senza vulnerabilità note (`pip-audit`, `npm audit`); analisi statica `bandit` con soli falsi
      positivi documentati in `SECURITY.md`
- [x] Audit di accessibilità axe-core senza violazioni (WCAG 2.1 AA)
- [x] `publiccode.yml` con categorie ammesse, `codiceIPA` vuoto e schermate esistenti, verificato dal test
      `tests/test_publiccode.py`
- [ ] Verifica finale con l'[editor/validatore ufficiale](https://publiccode-editor.developers.italia.it/)
- [ ] Segnalazione sul repository `italia/catalogo-software` con il modello "add new software"
- [ ] Licenza dei metadati e del feed GTFS di esempio: la guida consiglia CC0 o CC BY 4.0 per descrizioni,
      documentazione e dati

## Come un Comune adotta QuandoPassa

**Valutazione comparativa (art. 68 CAD).** Prima di acquisire software l'ente confronta le soluzioni disponibili,
privilegiando quelle open source e già a catalogo. La relazione dovrebbe considerare anche i servizi generalisti
(app di mobilità che leggono il GTFS pubblicato dall'azienda) e spiegare perché serve un servizio del Comune:
fermate e pensiline proprie, interfaccia della PA, nessun dato personale, assistente e API sotto il controllo
dell'ente.

**Configurazione.** Il feed GTFS va nella cartella `GTFS_DIR`; nome del Comune, servizio, centro della mappa e
testo sui biglietti nel file `.env` (vedi [Configurazione](configurazione.md) e [Il feed GTFS](gtfs.md)).

**Dati aperti.** Lo stesso feed GTFS alimenta QuandoPassa e può essere pubblicato sul portale open data del
Comune e sul punto di accesso nazionale ai dati del trasporto, così le app di mobilità lo riprendono.

**Ospitalità.** QuandoPassa non conserva dati personali e non ha database, ma resta un servizio della PA: va
ospitato su infrastrutture o servizi cloud **qualificati ACN**. Se un fornitore lo offre come servizio SaaS, quel
servizio deve essere qualificato.

**Prima dell'avvio.** Aggiornare il registro dei trattamenti con il RPD (posizione usata al momento, log di
accesso), scegliere il fornitore delle tile della mappa, pubblicare la dichiarazione di accessibilità e, se si
attiva un modello linguistico, fare la valutazione prevista dalle Linee guida AgID per l'IA nella PA. Dettagli in
[Installazione conforme PA](normativa-it.md).

## Fonti istituzionali

- [Developers Italia – Pubblicare software per la PA](https://developers.italia.it/it/guide/pubblicare-software-per-la-pa)
- [Developers Italia – Regolamento del Catalogo software](https://docs.italia.it/italia/developers-italia/policy-inserimento-catalogo-docs/it/stabile/catalogo-di-developers-italia.html)
- [Developers Italia – Catalogo del software](https://catalogo-software.developers.italia.it/)
- [Developers Italia – Onboarding delle amministrazioni](https://onboarding.developers.italia.it/)
- [Editor e validatore publiccode.yml](https://publiccode-editor.developers.italia.it/)
- [AgID – Linee guida su acquisizione e riuso di software per la PA](https://www.agid.gov.it/it/design-servizi/riuso-open-source/linee-guida-acquisizione-riuso-software-pa)
