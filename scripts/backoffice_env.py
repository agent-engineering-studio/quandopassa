"""Completa il file .env con le credenziali del backoffice e del database (lo usano `make env` e `make up`).

    python scripts/backoffice_env.py [.env]              aggiunge solo quello che manca
    python scripts/backoffice_env.py [.env] --password   cambia la password del backoffice

Il backoffice è sempre attivo: servono ADMIN_USER e ADMIN_PASSWORD (in chiaro nel .env, almeno 12 caratteri),
ADMIN_SECRET (chiave delle sessioni) e POSTGRES_PASSWORD. Se manca la password la chiede; senza terminale
(automazioni, CI) la genera e la stampa una volta. Non tocca gli altri valori del file.
"""
from __future__ import annotations

import getpass
import secrets
import sys
from pathlib import Path

MIN_LENGTH = 12


def current_value(lines: list[str], key: str) -> str:
    for line in lines:
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


def set_value(lines: list[str], key: str, value: str) -> list[str]:
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            return lines
    return [*lines, f"{key}={value}"]


def ask_password(user: str) -> str:
    while True:
        password = getpass.getpass(f"Password del backoffice per «{user}» (almeno {MIN_LENGTH} caratteri): ")
        if len(password) < MIN_LENGTH:
            print("Troppo corta, riprova.")
        elif getpass.getpass("Ripeti la password: ") != password:
            print("Le password non coincidono, riprova.")
        elif any(c in password for c in "$\"'#\\`") or any(c.isspace() for c in password):
            print("Evita spazi e i caratteri $ \" ' # \\ ` (il .env li interpreta), riprova.")
        else:
            return password


def main(argv: list[str]) -> None:
    change = "--password" in argv
    args = [a for a in argv if not a.startswith("--")]
    path = Path(args[0] if args else ".env")
    if not path.exists():
        sys.exit(f"{path} non trovato: crearlo con  make env")
    lines = path.read_text(encoding="utf-8").splitlines()
    interactive = sys.stdin.isatty()
    changed: list[str] = []

    user = current_value(lines, "ADMIN_USER")
    if not user:
        user = "admin"
        if interactive:
            user = input("Utente del backoffice [admin]: ").strip() or "admin"
        lines = set_value(lines, "ADMIN_USER", user)
        changed.append("ADMIN_USER")

    generated = ""
    if change or (not current_value(lines, "ADMIN_PASSWORD") and not current_value(lines, "ADMIN_PASSWORD_HASH")):
        if interactive:
            password = ask_password(user)
        else:
            password = generated = secrets.token_urlsafe(15)
        lines = set_value(lines, "ADMIN_PASSWORD", password)
        if current_value(lines, "ADMIN_PASSWORD_HASH"):
            lines = set_value(lines, "ADMIN_PASSWORD_HASH", "")  # l'hash avrebbe la precedenza
        changed.append("ADMIN_PASSWORD")

    if len(current_value(lines, "ADMIN_SECRET")) < 32:
        lines = set_value(lines, "ADMIN_SECRET", secrets.token_urlsafe(48))
        changed.append("ADMIN_SECRET")
    if not current_value(lines, "POSTGRES_PASSWORD"):
        lines = set_value(lines, "POSTGRES_PASSWORD", secrets.token_urlsafe(24))
        changed.append("POSTGRES_PASSWORD")

    if changed:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        path.chmod(0o600)
        print(f"{path}: impostati {', '.join(changed)}")
    if generated:
        print(f"Password del backoffice generata per «{user}»: {generated}  (è nel .env, ADMIN_PASSWORD)")


if __name__ == "__main__":
    main(sys.argv[1:])
