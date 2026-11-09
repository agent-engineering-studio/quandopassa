"""Audit di accessibilità con axe-core (WCAG 2 A/AA, 2.1 A/AA) su tutte le schede dell'interfaccia.

    make demo && make accessibilita        # oppure: python scripts/audit_accessibilita.py [BASE_URL]

Percorre da solo mappa, fermate vicine, fermata, assistente, servizio, ricerca e "come arrivo", da desktop e da
telefono, e stampa le violazioni. Esce con codice 1 se ne trova. Richiede playwright e `npm install` in web/.
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

RADICE = Path(__file__).resolve().parents[1]
AXE = (RADICE / "web" / "node_modules" / "axe-core" / "axe.min.js").read_text()
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001"
TOTALE = 0


def audit(page, nome):
    global TOTALE
    page.wait_for_timeout(600)  # fine delle transizioni CSS di Bootstrap Italia
    page.add_script_tag(content=AXE)
    r = page.evaluate("""async () => (await axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa']}})).violations
        .map(v => ({id: v.id, impact: v.impact, n: v.nodes.length, esempio: v.nodes[0].target.join(' '), msg: v.help}))""")
    TOTALE += len(r)
    print(f"{nome}: {len(r)} violazioni")
    for v in r:
        print("   ", json.dumps(v, ensure_ascii=False))


with sync_playwright() as p:
    b = p.chromium.launch()
    for vp, suff in (({"width": 1280, "height": 800}, "desktop"), ({"width": 390, "height": 844}, "mobile")):
        c = b.new_context(viewport=vp, geolocation={"latitude": 40.8099, "longitude": 16.922}, permissions=["geolocation"], locale="it-IT")
        pg = c.new_page(); pg.goto(BASE); pg.wait_for_selector(".bus-icona"); pg.wait_for_timeout(500)
        audit(pg, f"{suff} mappa")
        pg.locator(".pannello button:has-text('Usa la mia posizione')").click(); pg.wait_for_selector(".card-fermata"); audit(pg, f"{suff} vicino")
        pg.locator(".card-fermata h3").first.click(); pg.wait_for_selector(".in-arrivo-card"); audit(pg, f"{suff} fermata")
        pg.locator("#scheda-assistente").click(); pg.locator("#domanda").fill("prossimo bus"); pg.locator("#contenuto-assistente button[type=submit]").click()
        pg.wait_for_function("document.querySelectorAll('.fumetto-assistente').length > 1"); audit(pg, f"{suff} assistente")
        pg.locator("#scheda-servizio").click(); audit(pg, f"{suff} servizio")
        pg.locator("#cerca-fermata").fill("pia"); audit(pg, f"{suff} ricerca aperta")
        pg.locator("#scheda-percorso").click(); pg.wait_for_timeout(500); audit(pg, f"{suff} come arrivo vuoto")
        pg.locator(".campo-luogo input").first.click(); pg.wait_for_timeout(300); audit(pg, f"{suff} come arrivo suggerimenti")
        pg.locator(".campo-luogo .cerca-elenco li").first.dispatch_event("mousedown"); pg.wait_for_timeout(800)
        cam = pg.locator(".campo-luogo input").nth(1); cam.click(); cam.press_sequentially("cimitero", delay=30); pg.wait_for_timeout(1200)
        pg.keyboard.press("Enter"); pg.wait_for_selector(".soluzione"); pg.locator(".soluzione-testa").nth(1).click(); pg.wait_for_timeout(500)
        audit(pg, f"{suff} come arrivo soluzioni")
        c.close()
    b.close()

print(f"totale: {TOTALE} violazioni")
sys.exit(1 if TOTALE else 0)
