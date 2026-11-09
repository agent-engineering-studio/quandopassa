---
title: Intelligenza artificiale
description: Come funziona l'assistente di QuandoPassa, quali backend usa e quali garanzie offre.
---

# Intelligenza artificiale

L'assistente risponde in italiano a domande come *"Quando passa il prossimo bus da Piazza Plebiscito?"*,
*"Come arrivo al cimitero?"*, *"Dov'è adesso la linea B?"* o *"Quanto costa il biglietto?"*.

## Chi fa cosa

Come in [Spazio Comune](https://github.com/agent-engineering-studio/spazio-comune), i compiti sono divisi:

1. il **server di inferenza capisce** la frase: intento, luogo, linea, ora;
2. l'**app calcola** la risposta dai dati (orario GTFS, posizione se condivisa) e scrive una bozza;
3. un **LLM, se configurato, può solo riformulare** la bozza con i dati forniti.

Una riformulazione che cambia orari, minuti, distanze o nomi viene **scartata** a favore della bozza: gli orari
non possono essere inventati dal modello.

| Intento | Esempio | Risposta calcolata da |
|---|---|---|
| `prossimo` | "quando passa la B a Seven?" | prossimi passaggi dalla fermata |
| `percorso` | "come arrivo alla stazione?" | lo stesso calcolo della scheda "Come arrivo": a piedi, bus, eventuale cambio |
| `dove_bus` | "dov'è adesso la linea B?" | posizione stimata e prossima fermata |
| `vicina` | "fermata più vicina" | fermate vicine alla posizione condivisa |
| `orari_linea` | "orari della circolare A" | partenze dal capolinea della giornata |
| FAQ | "quanto costa il biglietto?" | base di conoscenza del servizio (`INFO_BIGLIETTI`, contatti, giorni, privacy) |

## Backend

`rules` (predefinito)
:   motore deterministico in italiano: nessun modello, nessuna GPU, **nessun dato esce dal server**, risposte
    riproducibili. È quello usato nei test.

`openai`
:   qualsiasi endpoint OpenAI-compatibile: l'LLM locale del profilo `llm` (Ollama, `make up-llm`), vLLM,
    llama.cpp o un servizio cloud. Capisce frasi più libere e rende le risposte più naturali.

Se il server di inferenza non risponde, l'assistente si spegne e la scheda **Chiedi** sparisce: mappa, fermate e
orari continuano a funzionare (degrado controllato).

## Garanzie

- **Trasparenza (AI Act, art. 50).** L'interfaccia dichiara che l'assistente è un sistema di IA; ogni risposta
  riporta se è stata generata con IA e con quale backend.
- **Decisione umana (L. 132/2025).** Uso informativo a basso rischio: l'assistente non decide nulla per conto
  della persona.
- **Dati personali.** Email e numeri di telefono vengono rimossi prima di ogni invio a un LLM; la posizione, se
  condivisa, serve solo alla domanda in corso e non viene salvata.
- **Fondatezza.** Orari e minuti vengono sempre dall'orario ufficiale; le FAQ rispondono solo con la base di
  conoscenza del servizio, altrimenti l'assistente dice di non sapere.

!!! warning "Prima di usare un LLM in esercizio"
    Prima di passare a `INFERENCE_BACKEND=openai` in produzione serve la valutazione prevista dalle Linee guida
    AgID sull'IA nella PA, con un LLM interno all'ente o un fornitore qualificato ACN.
