"""Hash delle password del backoffice (scrypt della libreria standard, senza caratteri «$» che il .env altererebbe).

    python -m quandopassa.password              chiede la password e stampa la riga per il .env

Formato: scrypt:N:r:p:sale_base64:hash_base64
"""
from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import secrets
import sys

N, R, P = 2**15, 8, 1
MAX_MEMORY = 64 * 1024 * 1024
MIN_LENGTH = 12


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, maxmem=MAX_MEMORY, dklen=32)
    return f"scrypt:{N}:{R}:{P}:{_b64encode(salt)}:{_b64encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        name, n, r, p, salt, expected = encoded.split(":")
        if name != "scrypt":
            return False
        expected_bytes = _b64decode(expected)
        digest = hashlib.scrypt(password.encode(), salt=_b64decode(salt), n=int(n), r=int(r), p=int(p),
                                maxmem=MAX_MEMORY, dklen=len(expected_bytes))
        return hmac.compare_digest(digest, expected_bytes)
    except (ValueError, TypeError):
        return False


def main() -> None:
    if not sys.stdin.isatty():
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = getpass.getpass("Password del backoffice: ")
        if getpass.getpass("Ripeti la password: ") != password:
            sys.exit("Le password non coincidono")
    if len(password) < MIN_LENGTH:
        sys.exit(f"Password troppo corta: almeno {MIN_LENGTH} caratteri")
    print(f"ADMIN_PASSWORD_HASH={hash_password(password)}")


if __name__ == "__main__":
    main()
