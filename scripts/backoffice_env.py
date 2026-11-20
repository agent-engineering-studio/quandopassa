"""Attiva il backoffice nel file .env per docker compose: utente, password, chiavi e database.

    python scripts/backoffice_env.py [.env]          (lo usa `make backoffice`)

Chiede utente e password (la password non viene salvata: nel .env va solo il suo hash), genera la chiave delle
sessioni e la password di Postgres se mancano, e imposta DATA_DIR e DATABASE_URL per il profilo "backoffice".
"""
from __future__ import annotations

import getpass
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from quandopassa.password import MIN_LENGTH, hash_password  # noqa: E402


def read_env(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


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


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else ".env")
    lines = read_env(path)
    if not lines:
        sys.exit(f"{path} non trovato: creare prima il file con  make env")

    user = input(f"Utente del backoffice [{current_value(lines, 'ADMIN_USER') or 'editor'}]: ").strip()
    user = user or current_value(lines, "ADMIN_USER") or "editor"
    password = getpass.getpass(f"Password (almeno {MIN_LENGTH} caratteri; invio = non cambiarla): ")
    if password:
        if len(password) < MIN_LENGTH:
            sys.exit("Password troppo corta")
        if getpass.getpass("Ripeti la password: ") != password:
            sys.exit("Le password non coincidono")
        lines = set_value(lines, "ADMIN_PASSWORD_HASH", hash_password(password))
    elif not current_value(lines, "ADMIN_PASSWORD_HASH"):
        sys.exit("Serve una password")

    lines = set_value(lines, "ADMIN_USER", user)
    if len(current_value(lines, "ADMIN_SECRET")) < 32:
        lines = set_value(lines, "ADMIN_SECRET", secrets.token_urlsafe(48))
    db_password = current_value(lines, "POSTGRES_PASSWORD") or secrets.token_urlsafe(24)
    lines = set_value(lines, "POSTGRES_PASSWORD", db_password)
    lines = set_value(lines, "DATA_DIR", current_value(lines, "DATA_DIR") or "/srv/dati")
    if not current_value(lines, "DATABASE_URL"):
        lines = set_value(lines, "DATABASE_URL", f"postgresql://quandopassa:{db_password}@db:5432/quandopassa")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)
    print(f"Backoffice configurato in {path} per l'utente «{user}».")


if __name__ == "__main__":
    main()
