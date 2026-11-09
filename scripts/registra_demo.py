"""Registra i video dimostrativi e gli screenshot sull'istanza demo già avviata.

    make demo                                       # istanza demo su :8001 (mercoledì 11/11/2026, 09:00)
    python scripts/registra_demo.py                 # 16:9 -> docs/demo/quandopassa-demo.{mp4,gif}
    python scripts/registra_demo.py --verticale     # 9:16 -> docs/demo/quandopassa-demo-verticale.mp4
    python scripts/registra_demo.py --percorso      # 16:9 -> docs/demo/quandopassa-come-arrivo.{mp4,gif}
    python scripts/registra_demo.py --percorso --verticale   # 9:16 -> docs/demo/quandopassa-come-arrivo-verticale.mp4
    python scripts/registra_demo.py --screenshot    # docs/screenshot/*.png

L'orologio della demo parte dall'avvio del container: riavviarla prima di ogni registrazione
(docker compose restart demo) perché le scene trovino i bus dove il copione se li aspetta.

Richiede playwright (chromium) e ffmpeg.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE = os.getenv("BASE_URL", "http://localhost:8001")
RADICE = Path(__file__).resolve().parents[1]
USCITA = RADICE / "docs" / "demo"
GREZZI = USCITA / "grezzi"
DESKTOP = {"width": 1280, "height": 720}
VERTICALE = {"width": 405, "height": 720}  # 9:16, portato a 1080x1920 da ffmpeg
# a circa 120 m dalla fermata Seven (R05), dove passano sia la A sia la B
POSIZIONE = {"latitude": 40.8099, "longitude": 16.9220}
# Villaggio Azzurro (solo linea B): per arrivare al cimitero (solo linea A) serve un cambio a Seven
VILLAGGIO = {"latitude": 40.7836, "longitude": 16.9330}

STILE = """
#demo-cap{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:99999;
  background:rgba(0,38,77,.93);color:#fff;font:600 22px/1.3 'Titillium Web',sans-serif;
  padding:14px 26px;border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,.25);max-width:88vw;text-align:center;
  animation:demoIn .35s ease-out;pointer-events:none}
#demo-cap small{display:block;font-weight:400;font-size:16px;opacity:.85;margin-top:2px}
@keyframes demoIn{from{opacity:0;transform:translate(-50%,12px)}to{opacity:1;transform:translate(-50%,0)}}
.demo-focus{outline:4px solid #ffb400 !important;outline-offset:3px;transition:outline .2s}
#demo-cartello{position:fixed;inset:0;z-index:100000;display:flex;align-items:center;justify-content:center;
  background:linear-gradient(135deg,#0066cc,#00264d);color:#fff;font-family:'Titillium Web',sans-serif;text-align:center}
#demo-cartello h1{color:#fff;font-weight:700}
"""
CAP_MOBILE = "#demo-cap{font-size:17px;bottom:14px;padding:10px 14px;width:92vw}#demo-cap small{font-size:13px}"


def _stile(page: Page) -> None:
    page.evaluate("""css => {
        if (!document.getElementById('demo-style')) {
          const st = document.createElement('style'); st.id = 'demo-style'; st.textContent = css;
          document.head.appendChild(st);
        }
    }""", STILE)


def didascalia(page: Page, titolo: str, sotto: str = "") -> None:
    _stile(page)
    page.evaluate("""([t, s]) => {
        document.getElementById('demo-cap')?.remove();
        const d = document.createElement('div'); d.id = 'demo-cap';
        d.innerHTML = t + (s ? '<small>' + s + '</small>' : '');
        document.body.appendChild(d);
    }""", [titolo, sotto])


def senza_didascalia(page: Page) -> None:
    page.evaluate("document.getElementById('demo-cap')?.remove()")


def cartello(page: Page, html: str, durata: int, w: int = 1000) -> None:
    """Schermata a tutto campo sopra l'app (usa i font dell'app, nessuna risorsa esterna)."""
    _stile(page)
    page.evaluate("""([h, w]) => {
        document.getElementById('demo-cartello')?.remove();
        const d = document.createElement('div'); d.id = 'demo-cartello';
        d.innerHTML = '<div style="max-width:' + w + 'px;padding:24px">' + h + '</div>';
        document.body.appendChild(d);
    }""", [html, w])
    page.wait_for_timeout(durata)
    page.evaluate("document.getElementById('demo-cartello')?.remove()")


def evidenzia(page: Page, selettore: str, pausa: int = 700):
    el = page.locator(selettore).first
    el.scroll_into_view_if_needed()
    el.evaluate("e => e.classList.add('demo-focus')")
    page.wait_for_timeout(pausa)
    el.evaluate("e => e.classList.remove('demo-focus')")
    return el


def scorri(page: Page, y: int, passi: int = 20) -> None:
    for _ in range(passi):
        page.mouse.wheel(0, y / passi)
        page.wait_for_timeout(35)


def apri(page: Page) -> None:
    page.goto(BASE + "/")
    page.wait_for_selector(".leaflet-marker-icon.bus-icona", timeout=20000)
    page.wait_for_timeout(600)


def contesto(browser, viewport: dict, cartella: str, posizione: dict = POSIZIONE, **extra):
    return browser.new_context(viewport=viewport, record_video_dir=GREZZI / cartella, record_video_size=viewport,
                               geolocation=posizione, permissions=["geolocation"], locale="it-IT",
                               timezone_id="Europe/Rome", **extra)


# ---------------------------------------------------------------------------------------------- 16:9
def scena_desktop(browser) -> Path:
    ctx = contesto(browser, DESKTOP, "1")
    page = ctx.new_page()
    apri(page)
    cartello(page, """<p style="font-size:22px;letter-spacing:.08em;text-transform:uppercase;opacity:.8">Comune di Gioia del Colle</p>
      <h1 style="font-size:56px">Quando passa il bus?</h1>
      <p style="font-size:28px;margin-top:24px">Oggi: un orario da consultare e <b>nessun GPS</b> a bordo.</p>
      <p style="font-size:28px">Con <b>QuandoPassa</b>: il bus sulla mappa, la fermata più vicina<br>e se fai in tempo a prenderlo.</p>""", 4200)

    didascalia(page, "I bus sulla mappa, secondo dopo secondo", "Posizione stimata dall'orario ufficiale GTFS, lungo il percorso stradale")
    page.wait_for_timeout(3600)
    didascalia(page, "Mostra solo la linea che ti interessa", "Circolare A e Circolare B")
    evidenzia(page, ".chip-linea >> nth=1", 600).click()
    page.wait_for_timeout(1600)
    page.locator(".chip-linea").nth(1).click()
    page.wait_for_timeout(1000)

    didascalia(page, "Dov'è la fermata più vicina?", "La posizione resta sul telefono")
    evidenzia(page, ".pannello button:has-text('Usa la mia posizione')", 600).click()
    page.wait_for_selector(".card-fermata", timeout=15000)
    page.wait_for_timeout(800)
    didascalia(page, "Minuti a piedi e prossimi passaggi", "\"Fai in tempo\", \"affrettati\" o \"non fai in tempo\"")
    page.wait_for_timeout(3400)

    didascalia(page, "Alla fermata: il bus più vicino", "Tra quanti minuti arriva, quante fermate mancano, dov'è adesso")
    evidenzia(page, ".card-fermata", 600)
    page.locator(".card-fermata h3").first.click()
    page.wait_for_selector(".in-arrivo-card", timeout=10000)
    page.wait_for_timeout(3200)
    didascalia(page, "Un tocco e lo vedi sulla mappa", "Il ritardo non si inventa: senza GPS l'app lo dichiara")
    evidenzia(page, ".in-arrivo-card", 600).click()
    page.wait_for_timeout(3600)

    didascalia(page, "Cerca una fermata per nome", "")
    campo = evidenzia(page, "#cerca-fermata", 400)
    campo.click()
    campo.press_sequentially("cimitero", delay=90)
    page.wait_for_timeout(700)
    page.keyboard.press("Enter")
    page.wait_for_timeout(2800)

    didascalia(page, "Oppure chiedi all'assistente, in italiano", "L'IA capisce la domanda, l'orario lo calcola l'app")
    evidenzia(page, "#scheda-assistente", 500).click()
    campo = evidenzia(page, "#domanda", 400)
    campo.click()
    campo.press_sequentially("come arrivo alla stazione?", delay=65)
    evidenzia(page, "#contenuto-assistente button[type=submit]", 400).click()
    page.wait_for_function("document.querySelectorAll('.fumetto-assistente').length > 1", timeout=15000)
    page.wait_for_timeout(4200)

    senza_didascalia(page)
    cartello(page, """<h1 style="font-size:60px">QuandoPassa</h1>
      <p style="font-size:28px;margin-top:20px">Bus sulla mappa · fermata più vicina · bus in arrivo · assistente IA</p>
      <p style="font-size:22px;opacity:.85;margin-top:28px">Orario GTFS · OpenStreetMap · Bootstrap Italia · server MCP<br>
      open source EUPL-1.2, riusabile da ogni Comune con un feed GTFS</p>
      <p style="font-size:18px;opacity:.7;margin-top:36px">Demo: posizioni stimate dall'orario programmato, orologio fisso</p>""", 4400)
    ctx.close()
    return Path(page.video.path())


# ---------------------------------------------------------------------------------------------- 9:16
def mobile(page: Page, titolo: str, sotto: str = "") -> None:
    page.add_style_tag(content=CAP_MOBILE)
    didascalia(page, titolo, sotto)


def scena_verticale(browser) -> Path:
    ctx = contesto(browser, VERTICALE, "v", device_scale_factor=2, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    apri(page)
    page.add_style_tag(content=CAP_MOBILE)
    cartello(page, """<p style="font-size:15px;letter-spacing:.08em;text-transform:uppercase;opacity:.8">Comune di Gioia del Colle</p>
      <h1 style="font-size:40px;line-height:1.15">Quando passa il bus?</h1>
      <p style="font-size:20px;margin-top:22px">Nessun GPS a bordo,<br>solo un orario da consultare.</p>
      <p style="font-size:20px;margin-top:14px">Con <b>QuandoPassa</b> il bus<br>è sulla mappa del telefono.</p>""", 3800, w=380)

    mobile(page, "I bus sulla mappa", "stimati dall'orario ufficiale")
    page.wait_for_timeout(3200)

    page.locator(".pannello").scroll_into_view_if_needed()
    mobile(page, "La fermata più vicina", "la posizione resta sul telefono")
    evidenzia(page, ".pannello button:has-text('Usa la mia posizione')", 600).click()
    page.wait_for_selector(".card-fermata", timeout=15000)
    page.locator(".pannello").scroll_into_view_if_needed()
    page.wait_for_timeout(1000)
    mobile(page, "Fai in tempo?", "minuti a piedi e prossimi passaggi")
    scorri(page, 160, 10)
    page.wait_for_timeout(2400)

    evidenzia(page, ".card-fermata", 500)
    page.locator(".card-fermata h3").first.click()
    page.wait_for_selector(".in-arrivo-card", timeout=10000)
    page.locator(".in-arrivo-card").scroll_into_view_if_needed()
    scorri(page, -140, 6)
    mobile(page, "Il bus in arrivo", "tra quanti minuti e a quante fermate")
    page.wait_for_timeout(3200)
    evidenzia(page, ".in-arrivo-card", 500).click()
    page.evaluate("window.scrollTo({top: document.querySelector('.mappa-box').offsetTop - 60, behavior: 'smooth'})")
    mobile(page, "Eccolo sulla mappa", "")
    page.wait_for_timeout(3200)

    evidenzia(page, "#scheda-assistente", 400).click()
    page.locator("#domanda").scroll_into_view_if_needed()
    mobile(page, "Chiedilo all'assistente", "orari calcolati dall'app, mai inventati")
    campo = evidenzia(page, "#domanda", 400)
    campo.click()
    campo.press_sequentially("quando passa la B a Seven?", delay=65)
    evidenzia(page, "#contenuto-assistente button[type=submit]", 400).click()
    page.wait_for_function("document.querySelectorAll('.fumetto-assistente').length > 1", timeout=15000)
    page.locator(".fumetto-assistente").last.scroll_into_view_if_needed()
    page.wait_for_timeout(3600)

    senza_didascalia(page)
    cartello(page, """<h1 style="font-size:44px">QuandoPassa</h1>
      <p style="font-size:20px;margin-top:18px">bus sulla mappa · fermata vicina<br>bus in arrivo · assistente IA</p>
      <p style="font-size:16px;opacity:.85;margin-top:22px">Open source EUPL-1.2<br>riusabile da ogni Comune</p>
      <p style="font-size:14px;opacity:.7;margin-top:28px">Demo con orologio fisso</p>""", 3800, w=380)
    ctx.close()
    return Path(page.video.path())


# ---------------------------------------------------------------------------------------------- come arrivo
def _campo(page: Page, n: int):
    return page.locator(".campo-luogo input").nth(n)


def _suggerimento(page: Page, testo: str, riserva: str | None = None) -> None:
    voce = page.locator(".campo-luogo .cerca-elenco li", has_text=testo).first
    try:
        voce.wait_for(timeout=15000)
    except Exception:  # noqa: BLE001 - geocoder pubblico lento o saturo: si ripiega su una fermata
        if not riserva:
            raise
        voce = page.locator(".campo-luogo .cerca-elenco li", has_text=riserva).first
        voce.wait_for(timeout=5000)
    voce.evaluate("e => e.classList.add('demo-focus')")
    page.wait_for_timeout(700)
    voce.dispatch_event("mousedown")


def _scrivi_arrivo(page: Page, testo: str, scelta: str, pausa: int = 1400, riserva: str | None = None) -> None:
    campo = _campo(page, 1)
    campo.click()
    campo.press_sequentially(testo, delay=80)
    page.wait_for_timeout(pausa)
    _suggerimento(page, scelta, riserva)
    page.wait_for_selector(".soluzione", timeout=15000)


def scena_percorso(browser, verticale: bool) -> Path:
    vp = VERTICALE if verticale else DESKTOP
    extra = {"device_scale_factor": 2, "is_mobile": True, "has_touch": True} if verticale else {}
    ctx = contesto(browser, vp, "p", posizione=VILLAGGIO, **extra)
    page = ctx.new_page()
    cap = (lambda t, s="": mobile(page, t, s)) if verticale else (lambda t, s="": didascalia(page, t, s))
    apri(page)
    if verticale:
        page.add_style_tag(content=CAP_MOBILE)
        cartello(page, """<p style="font-size:15px;letter-spacing:.08em;text-transform:uppercase;opacity:.8">QuandoPassa</p>
          <h1 style="font-size:40px;line-height:1.15">Come arrivo?</h1>
          <p style="font-size:20px;margin-top:22px">Quali bus prendere,<br>dove cambiare, quanto camminare.</p>""", 3400, w=380)
    else:
        cartello(page, """<p style="font-size:22px;letter-spacing:.08em;text-transform:uppercase;opacity:.8">QuandoPassa · Gioia del Colle</p>
          <h1 style="font-size:56px">Come arrivo?</h1>
          <p style="font-size:28px;margin-top:24px">Da un punto a un altro, come su un navigatore:<br>
          <b>quali bus prendere</b>, <b>dove cambiare</b> e <b>quanto camminare</b>.</p>""", 4000)

    evidenzia(page, "#scheda-percorso", 500).click()
    if verticale:
        page.locator(".pannello").scroll_into_view_if_needed()
    cap("Da dove parti?", "la tua posizione, un indirizzo o un punto sulla mappa")
    _campo(page, 0).click()
    page.wait_for_timeout(900)
    _suggerimento(page, "La mia posizione")
    page.wait_for_timeout(900)

    cap("Dove vuoi andare?", "dal Villaggio Azzurro al cimitero")
    _scrivi_arrivo(page, "cimitero", "rotatoria cimitero")
    page.wait_for_timeout(600)
    if verticale:
        page.locator(".soluzione").first.scroll_into_view_if_needed()
        scorri(page, -120, 6)
    cap("Le soluzioni, in ordine di arrivo", "a piedi o in bus: l'app non nasconde che a volte si fa prima a piedi")
    page.wait_for_timeout(3400)

    evidenzia(page, ".soluzione-testa >> nth=1", 600).click()
    cap("Bus B, cambio a Seven, bus A", "fermate, orari e attesa al cambio, tutto calcolato dall'orario")
    page.wait_for_timeout(1200)
    if verticale:
        page.locator(".passi").scroll_into_view_if_needed()
        page.wait_for_timeout(2600)
        page.evaluate("window.scrollTo({top: document.querySelector('.mappa-box').offsetTop - 60, behavior: 'smooth'})")
        cap("Il viaggio sulla mappa", "a piedi tratteggiato, in bus con il colore della linea")
        page.wait_for_timeout(3400)
    else:
        scorri(page, 0, 1)
        page.locator(".pannello").evaluate("e => e.scrollBy({top: 260, behavior: 'smooth'})")
        page.wait_for_timeout(2600)
        cap("Il viaggio sulla mappa", "a piedi tratteggiato, in bus con il colore della linea")
        page.wait_for_timeout(3000)

    if verticale:
        page.locator(".pannello").scroll_into_view_if_needed()
    else:
        page.locator(".pannello").evaluate("e => e.scrollTo({top: 0, behavior: 'smooth'})")
    page.wait_for_timeout(500)
    cap("Anche luoghi e indirizzi: il castello in 12 minuti", "cercati su OpenStreetMap dal server, senza la tua posizione")
    _scrivi_arrivo(page, "castello", "Castello Normanno Svevo", pausa=2200, riserva="Vittorio Emanuele")
    page.wait_for_timeout(600)
    evidenzia(page, ".soluzione-testa >> nth=0", 500).click()
    page.wait_for_timeout(3600)

    senza_didascalia(page)
    if verticale:
        cartello(page, """<h1 style="font-size:44px">QuandoPassa</h1>
          <p style="font-size:20px;margin-top:18px">come arrivo, con i bus<br>del servizio urbano</p>
          <p style="font-size:16px;opacity:.85;margin-top:22px">orari dall'orario ufficiale GTFS<br>open source EUPL-1.2</p>
          <p style="font-size:14px;opacity:.7;margin-top:28px">Demo con orologio fisso</p>""", 3600, w=380)
    else:
        cartello(page, """<h1 style="font-size:60px">QuandoPassa</h1>
          <p style="font-size:28px;margin-top:20px">Come arrivo: a piedi, bus, cambi · tutto dall'orario ufficiale GTFS</p>
          <p style="font-size:22px;opacity:.85;margin-top:28px">Anche dall'assistente IA e dal server MCP (strumento come_arrivare)<br>
          Bootstrap Italia · open source EUPL-1.2</p>
          <p style="font-size:18px;opacity:.7;margin-top:36px">Demo: orari stimati dall'orario programmato, orologio fisso</p>""", 4200)
    ctx.close()
    return Path(page.video.path())


# ---------------------------------------------------------------------------------------------- screenshot
def screenshot() -> None:
    cartella = RADICE / "docs" / "screenshot"
    cartella.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1.5, locale="it-IT",
                                  geolocation=POSIZIONE, permissions=["geolocation"], timezone_id="Europe/Rome")
        page = ctx.new_page()
        apri(page)
        page.screenshot(path=cartella / "01_mappa.png")
        page.locator(".pannello button:has-text('Usa la mia posizione')").click()
        page.wait_for_selector(".card-fermata")
        page.wait_for_timeout(800)
        page.screenshot(path=cartella / "02_vicino.png")
        page.locator(".card-fermata h3").first.click()
        page.wait_for_selector(".in-arrivo-card")
        page.wait_for_timeout(1200)
        page.screenshot(path=cartella / "03_fermata.png")
        page.locator("#scheda-assistente").click()
        page.locator("#domanda").fill("come arrivo al cimitero?")
        page.locator("#contenuto-assistente button[type=submit]").click()
        page.wait_for_function("document.querySelectorAll('.fumetto-assistente').length > 1")
        page.wait_for_timeout(600)
        page.screenshot(path=cartella / "04_assistente.png")
        page.locator("#scheda-servizio").click()
        page.wait_for_timeout(400)
        page.screenshot(path=cartella / "05_servizio.png")
        ctx.close()

        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1.5, locale="it-IT",
                                  geolocation=VILLAGGIO, permissions=["geolocation"], timezone_id="Europe/Rome")
        page = ctx.new_page()
        apri(page)
        page.locator("#scheda-percorso").click()
        _campo(page, 0).click()
        _suggerimento(page, "La mia posizione")
        page.wait_for_timeout(800)
        _scrivi_arrivo(page, "cimitero", "rotatoria cimitero")
        page.locator(".soluzione-testa").nth(1).click()
        page.wait_for_timeout(1500)
        page.evaluate("document.querySelectorAll('.demo-focus').forEach(e => e.classList.remove('demo-focus'))")
        page.screenshot(path=cartella / "08_come_arrivo.png")
        ctx.close()

        ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True,
                                  has_touch=True, locale="it-IT", geolocation=POSIZIONE, permissions=["geolocation"],
                                  timezone_id="Europe/Rome")
        page = ctx.new_page()
        apri(page)
        page.screenshot(path=cartella / "06_mobile.png")
        page.locator(".pannello button:has-text('Usa la mia posizione')").click()
        page.wait_for_selector(".card-fermata")
        page.locator(".card-fermata h3").first.click()
        page.wait_for_selector(".in-arrivo-card")
        page.locator(".pannello").scroll_into_view_if_needed()
        page.wait_for_timeout(800)
        page.screenshot(path=cartella / "07_mobile_fermata.png")
        ctx.close()
        browser.close()
    print(f"screenshot in {cartella}")


# ---------------------------------------------------------------------------------------------- montaggio
def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def main(argv: list[str]) -> None:
    if not shutil.which("ffmpeg"):
        sys.exit("serve ffmpeg")
    if "--screenshot" in argv:
        screenshot()
        return
    USCITA.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(GREZZI, ignore_errors=True)
    verticale, percorso = "--verticale" in argv, "--percorso" in argv
    with sync_playwright() as p:
        browser = p.chromium.launch()
        if percorso:
            grezzo = scena_percorso(browser, verticale)
        else:
            grezzo = scena_verticale(browser) if verticale else scena_desktop(browser)
        browser.close()

    nome = "quandopassa-come-arrivo" if percorso else "quandopassa-demo"
    if verticale:
        mp4 = USCITA / f"{nome}-verticale.mp4"
        ffmpeg("-i", str(grezzo), "-vf", "scale=1080:1920:flags=lanczos,fps=30", "-c:v", "libx264", "-preset", "slow",
               "-crf", "22", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(mp4))
        poster = "come-arrivo-verticale-poster.jpg" if percorso else "verticale-poster.jpg"
        ffmpeg("-ss", "6", "-i", str(mp4), "-frames:v", "1", "-q:v", "3", str(USCITA / poster))
    else:
        mp4 = USCITA / f"{nome}.mp4"
        ffmpeg("-i", str(grezzo), "-vf", "fps=30", "-c:v", "libx264", "-preset", "slow", "-crf", "22",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(mp4))
        tavolozza = GREZZI / "tavolozza.png"
        ffmpeg("-i", str(mp4), "-vf", "fps=10,scale=800:-1:flags=lanczos,palettegen=stats_mode=diff", str(tavolozza))
        ffmpeg("-i", str(mp4), "-i", str(tavolozza), "-lavfi",
               "fps=10,scale=800:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4",
               str(USCITA / f"{nome}.gif"))
    shutil.rmtree(GREZZI, ignore_errors=True)
    for f in sorted(USCITA.iterdir()):
        print(f"{f.relative_to(RADICE)}  {f.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main(sys.argv[1:])
