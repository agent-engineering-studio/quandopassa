from datetime import datetime, timedelta

from conftest import MERCOLEDI_9, ROMA


def test_feed_resta(orario):
    assert set(orario.linee) == {"A", "B"}
    assert len(orario.fermate) == 21
    assert len(orario.corse) == 16
    # Seven è condivisa da A e B
    assert orario.linee_della_fermata("R05") == ["A", "B"]


def test_calendario_circolare_a_non_il_martedi(orario):
    martedi = datetime(2026, 11, 10, tzinfo=ROMA).date()
    linee = {c.linea_id for c in orario.corse_del_giorno(martedi)}
    assert linee == {"B"}
    assert {c.linea_id for c in orario.corse_del_giorno(MERCOLEDI_9.date())} == {"A", "B"}
    assert orario.corse_del_giorno(datetime(2026, 11, 15).date()) == []  # domenica


def test_veicoli_interpolati(orario):
    v = {x["corsa_id"]: x for x in orario.veicoli(MERCOLEDI_9)}
    # A_0900 alle 9:05 è appena partita da Piazza Plebiscito (9:05) -> in fermata
    assert "A_0900" in v and v["A_0900"]["stato"] == "in_fermata"
    assert v["A_0900"]["prossima_fermata_id"] in ("R02", "R03")
    # B_0848: 17 minuti dopo la partenza, tra Grippa (+14) e Federico II (+20)
    b = v["B_0848"]
    assert b["stato"] == "in_viaggio" and b["prossima_fermata_id"] == "R20A"
    r19, r20 = orario.fermate["R19"], orario.fermate["R20A"]
    assert min(r19.lat, r20.lat) - 1e-6 <= b["lat"] <= max(r19.lat, r20.lat) + 1e-6
    assert 0 < b["avanzamento"] < 1


def test_nessun_bus_di_sera(orario):
    sera = MERCOLEDI_9.replace(hour=21)
    assert orario.veicoli(sera) == []
    nxt = orario.prossima_corsa(sera)
    assert nxt["partenza"].startswith("2026-11-12T08:15")


def test_partenze_ordinate_e_future(orario):
    p = orario.partenze("R05", MERCOLEDI_9, n=4)
    assert [x["linea"] for x in p[:2]] == ["A", "B"]  # A 9:10, B 9:13
    assert p[0]["orario"].startswith("2026-11-11T09:10") and p[0]["tra_minuti"] == 5
    assert all(a["orario"] <= b["orario"] for a, b in zip(p, p[1:]))


def test_partenze_saltano_la_domenica(orario):
    sabato_sera = datetime(2026, 11, 14, 20, 0, tzinfo=ROMA)
    p = orario.partenze("R11", sabato_sera, n=1)
    assert p[0]["orario"].startswith("2026-11-16T08:15")


def test_ricerca_fermate(orario):
    assert orario.cerca("plebiscito")[0]["id"] == "R02"
    assert orario.cerca("p.za dei martiri")[0]["id"] == "R03"
    assert orario.cerca("seven")[0]["id"] == "R05"
    assert {f["id"] for f in orario.cerca("cimitero", n=3)} >= {"R09", "R10"}
    assert orario.cerca("villaggio azzurro")[0]["id"] == "R11"
    assert orario.cerca("xyzxyz") == []


def test_percorso_diretto(orario):
    r11 = orario.fermate["R11"]
    opzioni = orario.percorso(r11.lat + 0.0005, r11.lon, ["R15"], MERCOLEDI_9)
    assert opzioni and opzioni[0]["linea"] == "B"
    o = opzioni[0]
    assert o["fermata_discesa_id"] == "R15"
    assert o["partenza"] < o["arrivo"]
    uscita = datetime.fromisoformat(o["esci_entro"])
    assert uscita >= MERCOLEDI_9 - timedelta(minutes=1)


def test_orario_del_giorno_per_interfaccia(orario):
    o = orario.orario_del_giorno(MERCOLEDI_9.date())
    assert len(o["corse"]) == 16
    tracciati = {t["id"]: t for t in o["tracciati"]}
    for c in o["corse"]:
        t = tracciati[c["tracciato_id"]]
        assert len(t["distanze_fermate"]) == len(c["fermate"]) == len(c["arrivi"])
        assert t["distanze_fermate"] == sorted(t["distanze_fermate"])


def test_build_gtfs_rigenera_identico(tmp_path):
    import shutil

    import build_gtfs
    from conftest import GTFS
    for f in ("fermate.csv", "percorsi.json"):
        shutil.copy(GTFS / f, tmp_path / f)
    if (GTFS / "forme.json").exists():
        shutil.copy(GTFS / "forme.json", tmp_path / "forme.json")
    stat = build_gtfs.costruisci(tmp_path)
    assert stat["corse"] == 16 and stat["orari"] == 192
    for f in ("stops.txt", "trips.txt", "stop_times.txt", "routes.txt", "calendar.txt"):
        assert (tmp_path / f).read_text() == (GTFS / f).read_text(), f
