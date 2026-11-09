# Contribuire a QuandoPassa

Il progetto accoglie contributi da cittadini, enti, aziende di trasporto e fornitori.

## Come proporre una modifica

1. Apri una issue che descriva il problema o la funzione, con il caso d'uso del tuo ente.
2. Crea un branch dal ramo `main` e mantieni le modifiche piccole e mirate.
3. Aggiungi o aggiorna i test: `make test` deve passare.
4. Se tocchi l'interfaccia, usa i componenti di Bootstrap Italia e verifica l'accessibilità (WCAG 2.1 AA):
   `npm run build` in `web/` deve passare e l'audit axe-core non deve trovare violazioni (vedi `SECURITY.md`).
5. Aggiorna `CHANGELOG.md` e, se cambia qualcosa per il riuso, `publiccode.yml` e la documentazione in `docs/`.
6. Apri una pull request descrivendo cosa cambia e come l'hai verificato.

## Regole del progetto

- Nessun dato specifico di un Comune nel codice: va nel file `.env` o nel feed GTFS (vedi `docs/configurazione.md`).
- Nessun dato personale salvato: la posizione resta sul dispositivo o serve solo alla richiesta in corso, e non
  finisce nei log.
- Onestà sui dati: le posizioni dei bus sono stime dall'orario. L'interfaccia non deve mai presentarle come
  rilevate né mostrare un ritardo che non è misurato.
- L'IA capisce e riformula, il codice calcola: orari, minuti e distanze vengono sempre dall'orario GTFS.
- Nessuna risorsa da CDN di terzi nell'interfaccia: font, icone e librerie vengono impacchettati con l'app.
- Dipendenze nuove solo se necessarie, con versione fissata e senza vulnerabilità note (`pip-audit`, `npm audit`).

## Licenza dei contributi

Inviando un contributo accetti che sia distribuito con licenza EUPL-1.2, la stessa del progetto.
