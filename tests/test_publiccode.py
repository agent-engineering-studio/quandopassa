"""La scheda publiccode.yml deve restare valida per il Catalogo di Developers Italia."""
from pathlib import Path

import yaml

RADICE = Path(__file__).resolve().parents[1]

# Sottoinsieme dei valori ammessi dallo standard publiccode.yml (campo categories)
CATEGORIE_AMMESSE = {
    "geographic-information-systems", "digital-citizenship", "data-visualization", "other",
}


def test_publiccode_yml_valido():
    pc = yaml.safe_load((RADICE / "publiccode.yml").read_text())
    for chiave in ("publiccodeYmlVersion", "name", "url", "platforms", "developmentStatus",
                   "softwareType", "description", "legal", "maintenance", "localisation"):
        assert chiave in pc, chiave
    assert set(pc["categories"]) <= CATEGORIE_AMMESSE
    it = pc["description"]["it"]
    assert it["shortDescription"] and it["longDescription"] and it["features"]
    assert len(it["shortDescription"]) <= 150
    assert all(len(f) <= 100 for f in it["features"])
    assert pc["legal"]["license"] == "EUPL-1.2"
    assert pc["maintenance"]["type"] in ("internal", "contract", "community", "none")
    if pc["maintenance"]["type"] in ("internal", "community"):
        assert pc["maintenance"]["contacts"]
    assert "it" not in pc, "la sezione nazionale va scritta IT (maiuscolo)"
    # software open source di terze parti: codiceIPA vuoto (guida Developers Italia, passo 8)
    assert pc["IT"]["riuso"]["codiceIPA"] == ""
    if (RADICE / "docs").exists():  # nel container dei test docs/ è escluso: si controlla in CI sul repository
        for s in it.get("screenshots", []):
            assert (RADICE / s).exists(), s


def test_licenza_e_file_di_progetto():
    assert "EUPL" in (RADICE / "LICENSE").read_text()
    for f in ("README.md", "CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md", ".env.example"):
        assert (RADICE / f).exists(), f
