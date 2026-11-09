"""Fixture condivise: feed GTFS di test, app e server di inferenza reale (rules)."""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

RADICE = Path(__file__).resolve().parents[1]
for p in (RADICE / "api", RADICE / "inference", RADICE / "scripts"):
    sys.path.insert(0, str(p))

os.environ.setdefault("INFERENCE_BACKEND", "rules")

import importlib.util  # noqa: E402


def carica(nome: str, percorso: Path):
    """Importa un modulo per percorso (inference/server.py e mcp_server/server.py hanno lo stesso nome)."""
    spec = importlib.util.spec_from_file_location(nome, percorso)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nome] = mod
    spec.loader.exec_module(mod)
    return mod


inference = carica("inference_server", RADICE / "inference" / "server.py")
mcp_quandopassa = carica("mcp_quandopassa", RADICE / "mcp_server" / "server.py")

from quandopassa.ai import ClientIA  # noqa: E402
from quandopassa.config import Config  # noqa: E402
from quandopassa.gtfs import Orario  # noqa: E402
from quandopassa.main import create_app  # noqa: E402

ROMA = ZoneInfo("Europe/Rome")
GTFS = RADICE / "data"
# mercoledì 11/11/2026: circolano A e B
MERCOLEDI_9 = datetime(2026, 11, 11, 9, 5, tzinfo=ROMA)


@pytest.fixture(scope="session")
def orario() -> Orario:
    return Orario(GTFS)


@pytest.fixture
def ia():
    return ClientIA("http://inference", client=TestClient(inference.app))


@pytest.fixture
def cfg(tmp_path):
    return Config(gtfs_dir=GTFS, web_dist=tmp_path, demo_ora="2026-11-11T09:05:00", geocoder="")


@pytest.fixture
def client(cfg, ia):
    return TestClient(create_app(cfg, ia))
