# Changelog

Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/) e il versionamento [SemVer](https://semver.org/lang/it/).

## [Non rilasciato]

### Aggiunto
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
