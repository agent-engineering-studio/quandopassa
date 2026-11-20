"""Avvia un servizio QuandoPassa leggendo il file .env come fa docker compose.

    avvia.py /etc/quandopassa/quandopassa.env -- comando argomenti...

Formato: KEY=VALORE, commenti su righe proprie, valori presi alla lettera (anche con &, <, ", spazi);
le virgolette che racchiudono tutto il valore vengono tolte. Le variabili già impostate nell'ambiente
(Environment= dell'unità systemd) hanno la precedenza sul file: servono a fissare porte e indirizzi interni.
Usato dalle unità systemd create da deploy/install.sh (installazione senza Docker).
"""
from __future__ import annotations

import os
import sys


def leggi_env(percorso: str) -> dict[str, str]:
    valori: dict[str, str] = {}
    try:
        with open(percorso, encoding="utf-8") as f:
            righe = f.read().splitlines()
    except FileNotFoundError:
        print(f"avvia.py: {percorso} non trovato, uso solo l'ambiente", file=sys.stderr)
        return valori
    for riga in righe:
        riga = riga.strip()
        if not riga or riga.startswith("#") or "=" not in riga:
            continue
        chiave, valore = riga.split("=", 1)
        chiave = chiave.strip().removeprefix("export ").strip()
        valore = valore.strip()
        if len(valore) >= 2 and valore[0] == valore[-1] and valore[0] in "\"'":
            valore = valore[1:-1]
        if chiave:
            valori[chiave] = valore
    return valori


def main(argv: list[str]) -> None:
    if len(argv) < 3 or argv[1] != "--":
        sys.exit("uso: avvia.py FILE_ENV -- comando [argomenti...]")
    for chiave, valore in leggi_env(argv[0]).items():
        os.environ.setdefault(chiave, valore)
    comando = argv[2:]
    os.execvp(comando[0], comando)


if __name__ == "__main__":
    main(sys.argv[1:])
