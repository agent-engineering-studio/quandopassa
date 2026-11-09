---
title: Server MCP
description: Il bus urbano come strumento per Claude, Copilot e altri assistenti e agenti, via Model Context Protocol.
---

# Server MCP

Il server MCP (Model Context Protocol) espone le stesse informazioni dell'app come **strumenti** per assistenti e
sistemi agentici: Claude Desktop, Claude Code, Copilot, IDE e orchestratori. Passa solo dalle API HTTP pubbliche
dell'app: **non conosce segreti e non scrive nulla**.

## Strumenti

| Strumento | Cosa restituisce |
|---|---|
| `info_servizio` | azienda, linee, validità dell'orario, ora attuale, prossima corsa, avvisi |
| `cerca_fermata` | fermate il cui nome somiglia al testo (es. "plebiscito", "seven") |
| `fermate_vicine` | fermate più vicine a un punto, con minuti a piedi e prossimi passaggi |
| `prossime_partenze` | prossimi passaggi da una fermata, anche per un'ora indicata |
| `bus_in_servizio` | bus in servizio con posizione **stimata** dall'orario e prossima fermata |
| `come_arrivare` | da un punto a una destinazione (fermata, indirizzo o luogo): soluzioni con tratti a piedi, linee, cambi, orari |
| `orari_linea` | fermate e tracciato di una linea |
| `tariffe_biglietti` | titoli in vendita con prezzi e regole (solo informazione: nessun agente compra o paga) |
| `chiedi_assistente` | domanda in italiano all'assistente del servizio |

Le istruzioni del server chiedono agli agenti di dichiarare che le posizioni sono stimate e di non chiedere né
inviare dati personali.

## Collegamento

=== "HTTP (Docker)"

    Con `make up` il server è su `http://localhost:8090/mcp` (trasporto streamable HTTP), raggiungibile solo da
    localhost. Gli host ammessi si cambiano con `MCP_ALLOWED_HOSTS`.

=== "stdio (Claude Desktop, Claude Code)"

    ```json
    { "mcpServers": { "quandopassa": { "command": "python", "args": ["mcp_server/server.py"],
      "env": { "QUANDOPASSA_URL": "http://localhost:8000" } } } }
    ```

    Richiede `pip install -r mcp_server/requirements.txt`.
