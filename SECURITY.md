# Sicurezza

Se trovi una vulnerabilità non aprire una issue pubblica: usa la segnalazione privata del repository ("Report a
vulnerability"), indicando versione, passi per riprodurre e impatto. Riceverai una risposta entro 7 giorni.

Controlli da eseguire a ogni rilascio:

- `pip-audit -r api/requirements.txt -r inference/requirements.txt -r mcp_server/requirements.txt`
  (vulnerabilità note nelle dipendenze Python): nessuna al 9/11/2026.
- `npm audit --omit=dev` in `web/` (dipendenze dell'interfaccia): nessuna al 9/11/2026.
- `bandit -r api/quandopassa inference mcp_server scripts` (analisi statica): restano tre segnalazioni LOW
  (B404, B603, B607) su `scripts/registra_demo.py`, che chiama `ffmpeg` con argomenti fissi. È uno strumento di
  sviluppo per i video, non gira in esercizio: falsi positivi.
- Audit di accessibilità axe-core (WCAG 2 A/AA, 2.1 A/AA) su mappa, fermate vicine, fermata, assistente,
  servizio e ricerca, da desktop e da telefono: 0 violazioni al 9/11/2026.
- Suite `pytest`, che copre anche l'oscuramento di posizione e domande nei log di accesso.

Scelte di progetto rilevanti per la sicurezza:

- nessun database, nessun account, nessun segreto applicativo: non ci sono credenziali da proteggere nell'app;
- container non-root; il server di inferenza non è esposto fuori dalla rete di Compose; il server MCP ascolta
  solo su `127.0.0.1` con protezione da DNS rebinding ed è in sola lettura;
- i log di accesso non contengono coordinate né il testo delle domande all'assistente;
- l'interfaccia non carica risorse da CDN di terzi (le tile della mappa sì: vedi `docs/normativa-it.md`).

Gli enti che installano QuandoPassa restano responsabili di HTTPS, aggiornamenti, conservazione dei log, scelta
del fornitore delle tile e conformità al Regolamento ACN per il cloud della PA.
