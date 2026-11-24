import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { BikeStation, Fermata, FermataVicina, Info, Itinerario, LineaDettaglio, Luogo, OrarioGiorno, Partenza } from "./api";
import { api, hhmm } from "./api";
import { alertsForStop, closedStopIds } from "./alerts";
import { NEARBY_STOP_METERS, nearbyBikeStations } from "./bikes";
import BikeStations from "./components/BikeStations";
import Assistente from "./components/Assistente";
import BarraAvvisi, { AvvisoServizio } from "./components/Avvisi";
import ComeArrivo, { type Campo } from "./components/ComeArrivo";
import InArrivo from "./components/InArrivo";
import Mappa from "./components/Mappa";
import Partenze from "./components/Partenze";
import Icona, { IconaBus } from "./Icona";
import { busInArrivo, hhmmDaSecondi, secondiDelGiorno, veicoliAl } from "./motore";
import { notifica } from "./notifiche";
import { giornoLocale, isoLocale, oraLocale, useOrologio } from "./orologio";

type Pannello = "vicino" | "percorso" | "fermata" | "assistente" | "servizio";
interface Posizione {
  lat: number;
  lon: number;
  accuratezza: number;
}

const MOBILE = "(max-width: 991.98px)";

export default function App() {
  const adesso = useOrologio(1000);
  const oggi = giornoLocale(adesso);

  const [info, setInfo] = useState<Info | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [fermate, setFermate] = useState<Fermata[]>([]);
  const [linee, setLinee] = useState<LineaDettaglio[]>([]);
  const [orario, setOrario] = useState<OrarioGiorno | null>(null);
  const [lineeVisibili, setLineeVisibili] = useState<string[]>([]);
  const [pannello, setPannello] = useState<Pannello>("vicino");
  const [selezionata, setSelezionata] = useState<string | null>(null);
  const [partenze, setPartenze] = useState<Partenza[]>([]);
  const [posizione, setPosizione] = useState<Posizione | null>(null);
  const [vicine, setVicine] = useState<FermataVicina[] | null>(null);
  const [cercoPosizione, setCercoPosizione] = useState(false);
  const [centraSu, setCentraSu] = useState<[number, number] | null>(null);
  const [corsaEvidenziata, setCorsaEvidenziata] = useState<string | null>(null);
  const [itinerario, setItinerario] = useState<Itinerario | null>(null);
  const [sceltaCampo, setSceltaCampo] = useState<Campo | null>(null);
  const [luogoScelto, setLuogoScelto] = useState<{ campo: Campo; luogo: Luogo } | null>(null);
  const watchId = useRef<number | null>(null);
  const ultimaPosVicine = useRef<string>("");
  const testata = useRef<HTMLElement>(null);
  const [bikeStations, setBikeStations] = useState<BikeStation[]>([]);
  const [showBikes, setShowBikes] = useState(true);
  const [feedChanges, setFeedChanges] = useState(0); // cresce quando il backoffice pubblica un nuovo feed
  const knownLines = useRef<string[]>([]);
  const riquadro = useRef<HTMLElement>(null);

  // ------------------------------------------------------------ dati statici
  useEffect(() => {
    Promise.all([api.info(), api.fermate(), api.linee()])
      .then(([i, f, l]) => {
        setInfo(i);
        setFermate(f);
        setLinee(l);
        // dopo un aggiornamento restano nascoste solo le linee che la persona aveva nascosto
        const ids = l.map((x) => x.id);
        const known = knownLines.current; // letto ora: l'updater sotto viene eseguito più tardi
        knownLines.current = ids;
        setLineeVisibili((prev) => (known.length ? ids.filter((id) => prev.includes(id) || !known.includes(id)) : ids));
      })
      .catch((e) => setErrore((e as Error).message));
  }, [feedChanges]);

  // il backoffice può cambiare fermate, orari e avvisi in qualsiasi momento: ogni 2 minuti si controlla la versione
  useEffect(() => {
    if (!info) return;
    const t = setInterval(() => {
      api
        .health()
        .then((h) => h.feed !== info.versione_feed && setFeedChanges((n) => n + 1))
        .catch(() => undefined);
    }, 120_000);
    return () => clearInterval(t);
  }, [info]);

  // bike sharing: stazioni pubblicate dal backoffice; se il gestore dà la disponibilità si aggiorna ogni minuto
  const bikeSystems = info?.bike_sharing ?? [];
  const bikesLive = bikeSystems.some((b) => b.live);
  useEffect(() => {
    if (!bikeSystems.length) {
      setBikeStations([]);
      return;
    }
    const load = () =>
      api
        .bikeStations()
        .then((r) => setBikeStations(r.stations))
        .catch(() => undefined); // restano le ultime stazioni ricevute
    load();
    if (!bikesLive) return;
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [info, bikeSystems.length, bikesLive]);

  // orario del giorno (cambia a mezzanotte)
  useEffect(() => {
    let valido = true; // ignora risposte arrivate dopo un cambio di giorno (es. sincronizzazione dell'orologio)
    api
      .orario(oggi)
      .then((o) => valido && setOrario(o))
      .catch(() => valido && setOrario(null));
    return () => {
      valido = false;
    };
  }, [oggi, feedChanges]);

  const veicoli = useMemo(() => (orario ? veicoliAl(orario, secondiDelGiorno(adesso, orario)) : []), [orario, adesso]);

  // altezza dell'header PA: da desktop mappa e pannello occupano il resto dello schermo
  useLayoutEffect(() => {
    const el = testata.current;
    if (!el) return;
    const ro = new ResizeObserver(() =>
      document.documentElement.style.setProperty("--altezza-testata", `${el.offsetHeight}px`),
    );
    ro.observe(el);
    return () => ro.disconnect();
  }, [info]);

  // da mobile il pannello sta sotto la mappa: portarlo in vista quando cambia contenuto
  const mostraPannello = () => {
    if (window.matchMedia(MOBILE).matches) riquadro.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  // ------------------------------------------------------------ fermata selezionata
  const minutoCorrente = isoLocale(adesso).slice(0, 16);
  useEffect(() => {
    if (!selezionata) return;
    api.partenze(selezionata, minutoCorrente).then(setPartenze).catch(() => setPartenze([]));
  }, [selezionata, minutoCorrente]);

  const apriFermata = useCallback(
    (id: string) => {
      setSelezionata(id);
      setPannello("fermata");
      const f = fermate.find((x) => x.id === id);
      if (f) setCentraSu([f.lat, f.lon]);
    },
    [fermate],
  );

  // ------------------------------------------------------------ geolocalizzazione
  const localizza = () => {
    if (!("geolocation" in navigator)) {
      notifica("danger", "Il browser non supporta la geolocalizzazione.");
      return;
    }
    setCercoPosizione(true);
    if (watchId.current !== null) navigator.geolocation.clearWatch(watchId.current);
    watchId.current = navigator.geolocation.watchPosition(
      (p) => {
        const nuova = { lat: p.coords.latitude, lon: p.coords.longitude, accuratezza: p.coords.accuracy };
        setPosizione((prima) => {
          if (!prima) setCentraSu([nuova.lat, nuova.lon]);
          return nuova;
        });
        setCercoPosizione(false);
        setPannello((x) => (x === "fermata" || x === "percorso" ? x : "vicino"));
      },
      (e) => {
        setCercoPosizione(false);
        notifica(
          "danger",
          e.code === 1 ? "Permesso negato: abilitalo nelle impostazioni del browser." : e.message,
          "Posizione non disponibile",
        );
      },
      { enableHighAccuracy: true, maximumAge: 10000, timeout: 20000 },
    );
  };
  useEffect(() => () => {
    if (watchId.current !== null) navigator.geolocation.clearWatch(watchId.current);
  }, []);

  // fermate vicine: aggiornate quando ci si sposta di ~25 m o cambia il minuto
  useEffect(() => {
    if (!posizione) return;
    const chiave = `${posizione.lat.toFixed(4)},${posizione.lon.toFixed(4)},${minutoCorrente}`;
    if (chiave === ultimaPosVicine.current) return;
    ultimaPosVicine.current = chiave;
    api.vicine(posizione.lat, posizione.lon, minutoCorrente).then(setVicine).catch(() => setVicine(null));
  }, [posizione, minutoCorrente]);

  const fermataSel = fermate.find((f) => f.id === selezionata) ?? null;
  const fermateById = useMemo(() => new Map(fermate.map((f) => [f.id, f])), [fermate]);
  const closedStops = useMemo(
    () => closedStopIds(info?.alerts ?? [], adesso),
    // ricalcolo al minuto: gli avvisi iniziano e finiscono a orari precisi
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [info, Math.floor(adesso.getTime() / 60000)],
  );
  const arrivi = useMemo(() => (selezionata ? busInArrivo(veicoli, selezionata) : []), [veicoli, selezionata]);
  const vicinaSel = vicine?.find((v) => v.id === selezionata);
  const bikesNearStop = useMemo(
    () => (fermataSel ? nearbyBikeStations(bikeStations, fermataSel.lat, fermataSel.lon, 3, NEARBY_STOP_METERS) : []),
    [bikeStations, fermataSel],
  );
  const bikesNearMe = useMemo(
    () => (posizione ? nearbyBikeStations(bikeStations, posizione.lat, posizione.lon, 2, 800) : []),
    [bikeStations, posizione],
  );
  const showBikeStation = (b: BikeStation) => {
    setShowBikes(true);
    setCentraSu([b.lat, b.lon]);
  };

  // ------------------------------------------------------------ render
  if (errore)
    return (
      <main className="container my-5">
        <div className="alert alert-danger" role="alert">
          <strong className="d-block">Servizio non raggiungibile</strong>
          {errore}
        </div>
      </main>
    );
  if (!info)
    return (
      <main className="container my-5" aria-busy="true">
        <p className="text-muted">Caricamento del servizio…</p>
        <div className="progress progress-indeterminate" role="progressbar" aria-label="Caricamento">
          <div className="progress-bar" />
        </div>
      </main>
    );

  const nessunBus = veicoli.length === 0;
  const prossimaCorsa = orario?.corse
    .map((c) => c.partenze[0])
    .filter((s) => s > secondiDelGiorno(adesso, orario))
    .sort((a, b) => a - b)[0];

  const schede: { id: Pannello; etichetta: string; icona: string; disabilitata?: boolean }[] = [
    { id: "vicino", etichetta: "Vicino a te", icona: "it-map-marker-circle" },
    { id: "percorso", etichetta: "Come arrivo", icona: "it-flag" },
    { id: "fermata", etichetta: "Fermata", icona: "it-map-marker", disabilitata: !selezionata },
    ...(info.assistente ? [{ id: "assistente" as const, etichetta: "Chiedi", icona: "it-comment" }] : []),
    { id: "servizio", etichetta: "Servizio", icona: "it-info-circle" },
  ];

  return (
    <>
      <div className="skiplinks">
        <a className="visually-hidden-focusable" href="#pannello">
          Vai ai contenuti
        </a>
        <a className="visually-hidden-focusable" href="#piede">
          Vai al piè di pagina
        </a>
      </div>

      <header ref={testata} className="it-header-wrapper">
        <div className="it-header-slim-wrapper">
          <div className="container-fluid px-3 px-lg-4">
            <div className="it-header-slim-wrapper-content">
              <a className="navbar-brand" href={info.header.entity_url || info.sito}>
                {info.header.entity_name}
              </a>
              <div className="it-header-slim-right-zone gap-3">
                {info.biglietti.url && (
                  <a className="text-white small" href={info.biglietti.url} target="_blank" rel="noopener noreferrer">
                    Biglietti
                    <span className="visually-hidden"> (sito esterno, si apre in una nuova scheda)</span>
                  </a>
                )}
                <a className="text-white small d-none d-md-inline" href="/api/docs">
                  API aperte
                </a>
              </div>
            </div>
          </div>
        </div>
        <div className="it-nav-wrapper">
          <div className="it-header-center-wrapper it-small-header">
            <div className="container-fluid px-3 px-lg-4">
              <div className="it-header-center-content-wrapper">
                <div className="it-brand-wrapper ps-0">
                  <a href="/">
                    {info.header.logo_url ? (
                      <img src={info.header.logo_url} alt={info.header.logo_alt} className="logo-ente me-2" />
                    ) : (
                      <span className="me-2 text-white d-inline-flex">
                        <IconaBus dim={40} />
                      </span>
                    )}
                    <div className="it-brand-text">
                      <div className="it-brand-title">{info.header.title}</div>
                      <div className="it-brand-tagline">{info.header.subtitle}</div>
                    </div>
                  </a>
                </div>
                <div className="it-right-zone d-none d-sm-flex">
                  <span className="text-white small text-end">
                    <strong className="d-block tabular">
                      {veicoli.length} {veicoli.length === 1 ? "bus" : "bus"} in servizio
                    </strong>
                    posizione stimata dall'orario
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
        <BarraAvvisi alerts={info.alerts} now={adesso} />
      </header>

      <div className="area">
        <div className="colonna-mappa">
          <div className="barra px-3 py-2 d-flex flex-wrap align-items-center gap-2">
            <ul className="list-unstyled d-flex flex-wrap gap-2 mb-0" aria-label="Linee mostrate sulla mappa">
              {linee.map((l) => {
                const attiva = lineeVisibili.includes(l.id);
                return (
                  <li key={l.id}>
                    <button
                      type="button"
                      className="chip chip-lg chip-linea"
                      style={{ ["--c" as string]: l.colore }}
                      aria-pressed={attiva}
                      onClick={() =>
                        setLineeVisibili((v) => (attiva ? v.filter((x) => x !== l.id) : [...v, l.id]))
                      }
                    >
                      <span className="chip-label">{l.nome_esteso}</span>
                    </button>
                  </li>
                );
              })}
              {bikeStations.length > 0 && (
                <li>
                  <button
                    type="button"
                    className="chip chip-lg chip-linea chip-bici"
                    aria-pressed={showBikes}
                    onClick={() => setShowBikes((v) => !v)}
                    title="Stazioni di bike sharing"
                  >
                    <span className="chip-label">Bici</span>
                  </button>
                </li>
              )}
            </ul>
            <CercaFermata
              fermate={fermate}
              onScelta={(id) => {
                apriFermata(id);
                mostraPannello();
              }}
            />
            <Orologio adesso={adesso} />
          </div>

          <div className="mappa-box">
            <Mappa
              info={info}
              closedStops={closedStops}
              linee={linee}
              fermate={fermate}
              veicoli={veicoli}
              lineeVisibili={lineeVisibili}
              posizione={posizione}
              selezionata={selezionata}
              corsaEvidenziata={corsaEvidenziata}
              onFermata={(id) => {
                apriFermata(id);
                mostraPannello();
              }}
              centraSu={centraSu}
              itinerario={pannello === "percorso" ? itinerario : null}
              bikeStations={showBikes ? bikeStations : []}
              sceltaPunto={sceltaCampo !== null}
              onPunto={(lat, lon) => {
                if (!sceltaCampo) return;
                setLuogoScelto({ campo: sceltaCampo, luogo: { tipo: "mappa", nome: "Punto sulla mappa", lat, lon } });
                setSceltaCampo(null);
                setPannello("percorso");
                mostraPannello();
              }}
            />

            {sceltaCampo && (
              <div className="avviso-mappa alert alert-info bg-white shadow-sm py-2 mb-0 d-flex align-items-center gap-2" role="status">
                <span className="flex-grow-1 small">
                  <strong>Tocca la mappa</strong> per scegliere {sceltaCampo === "da" ? "la partenza" : "l'arrivo"}.
                </span>
                <button type="button" className="btn btn-outline-primary btn-xs" onClick={() => setSceltaCampo(null)}>
                  Annulla
                </button>
              </div>
            )}

            {nessunBus && !sceltaCampo && pannello !== "percorso" && (
              <div className="avviso-mappa alert alert-warning bg-white shadow-sm py-2 mb-0 d-flex align-items-center gap-2 flex-wrap">
                <span className="flex-grow-1 small">
                  <strong>Nessun bus in servizio ora.</strong>
                  {prossimaCorsa !== undefined
                    ? ` Prima corsa alle ${hhmmDaSecondi(prossimaCorsa)}.`
                    : info.prossima_corsa
                      ? ` Prossima: ${info.prossima_corsa.partenza.slice(0, 10) === oggi ? "" : "il " + info.prossima_corsa.partenza.slice(8, 10) + "/" + info.prossima_corsa.partenza.slice(5, 7) + " "}alle ${hhmm(info.prossima_corsa.partenza)}.`
                      : ""}
                </span>
              </div>
            )}

            <div className="pulsanti-mappa">
              <button
                type="button"
                className={`btn-mappa ${posizione ? "attivo" : ""}`}
                onClick={() => {
                  localizza();
                  setPannello("vicino");
                }}
                disabled={cercoPosizione}
                aria-label="Usa la mia posizione"
                title="La mia posizione"
              >
                <Icona nome="it-map-marker-circle" />
              </button>
            </div>
          </div>
        </div>

        <section ref={riquadro} id="pannello" className="pannello" aria-label="Informazioni sul servizio" tabIndex={-1}>
          <ul className="nav nav-tabs" role="tablist">
            {schede.map((s) => (
              <li key={s.id} className="nav-item" role="presentation">
                <button
                  type="button"
                  role="tab"
                  id={`scheda-${s.id}`}
                  aria-controls={`contenuto-${s.id}`}
                  aria-selected={pannello === s.id}
                  className={`nav-link ${pannello === s.id ? "active" : ""} ${s.disabilitata ? "disabled" : ""}`}
                  disabled={s.disabilitata}
                  onClick={() => setPannello(s.id)}
                >
                  <Icona nome={s.icona} classe="icon-sm" />
                  {s.etichetta}
                </button>
              </li>
            ))}
          </ul>

          <div className="p-3" role="tabpanel" id={`contenuto-${pannello}`} aria-labelledby={`scheda-${pannello}`}>
            {pannello === "vicino" &&
              (!posizione ? (
                <div>
                  <h2 className="h5">Qual è la fermata più vicina?</h2>
                  <p>
                    Attiva la posizione: troviamo la fermata più vicina e ti diciamo se fai in tempo a prendere il
                    prossimo bus, confrontando l'ora attuale con l'orario ufficiale.
                  </p>
                  <button type="button" className="btn btn-primary btn-icon w-100 justify-content-center gap-2" onClick={localizza} disabled={cercoPosizione}>
                    <Icona nome="it-map-marker-circle" classe="icon-white" />
                    <span>{cercoPosizione ? "Cerco la posizione…" : "Usa la mia posizione"}</span>
                  </button>
                  <p className="small text-muted mt-2 mb-0">
                    <Icona nome="it-info-circle" classe="icon-xs" /> La posizione resta sul tuo dispositivo e serve
                    solo a questo calcolo. In alternativa scegli una fermata sulla mappa o con la ricerca.
                  </p>
                </div>
              ) : !vicine ? (
                <div className="progress progress-indeterminate" role="progressbar" aria-label="Cerco le fermate vicine">
                  <div className="progress-bar" />
                </div>
              ) : (
                <div className="d-flex flex-column gap-3">
                  <h2 className="h5 mb-0">Fermate vicino a te</h2>
                  {vicine.map((v, i) => (
                    <article
                      key={v.id}
                      className="card-fermata p-3"
                      tabIndex={0}
                      onClick={() => apriFermata(v.id)}
                      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), apriFermata(v.id))}
                      aria-label={`${v.nome}, ${v.distanza_m} metri: apri la fermata`}
                    >
                      <div className="d-flex justify-content-between gap-2 mb-2">
                        <div>
                          <span className="small text-muted text-uppercase">
                            {i === 0 ? "Fermata più vicina" : "Alternativa"}
                          </span>
                          <h3 className="h6 mb-0">{v.nome}</h3>
                        </div>
                        <div className="text-end text-nowrap">
                          <strong className="d-block tabular">
                            {v.distanza_m < 1000 ? `${v.distanza_m} m` : `${(v.distanza_m / 1000).toFixed(1).replace(".", ",")} km`}
                          </strong>
                          <span className="small text-muted">{v.a_piedi_min} min a piedi</span>
                        </div>
                      </div>
                      <Partenze partenze={v.partenze} oggi={oggi} aPiediMin={v.a_piedi_min} onCorsa={setCorsaEvidenziata} />
                    </article>
                  ))}
                  <BikeStations stations={bikesNearMe} title="Bici condivise vicino a te" onStation={showBikeStation} />
                </div>
              ))}

            {pannello === "fermata" && fermataSel && (
              <div>
                <div className="d-flex align-items-center gap-2 mb-1">
                  {(fermataSel.linee ?? []).map((l) => {
                    const linea = linee.find((x) => x.id === l);
                    return (
                      <span key={l} className="badge badge-linea" style={{ background: linea?.colore }}>
                        {l}
                      </span>
                    );
                  })}
                  <span className="small text-muted">Area n. {fermataSel.codice}</span>
                </div>
                <h2 className="h4 mb-1">{fermataSel.nome}</h2>
                <p className="small text-muted">{fermataSel.descrizione}</p>
                {alertsForStop(info.alerts, fermataSel.id, fermataSel.linee ?? []).length > 0 && (
                  <div className="avvisi-fermata mb-2" role="status">
                    {alertsForStop(info.alerts, fermataSel.id, fermataSel.linee ?? []).map((a) => (
                      <AvvisoServizio key={a.id} alert={a} now={adesso} />
                    ))}
                  </div>
                )}
                {fermataSel.provvisoria && (
                  <div className="alert alert-warning py-2 small">
                    Posizione sulla mappa provvisoria, in attesa di geocoding o sopralluogo.
                  </div>
                )}
                {vicinaSel && (
                  <p>
                    Sei a <strong>{vicinaSel.distanza_m} m</strong>, circa <strong>{vicinaSel.a_piedi_min} min</strong>{" "}
                    a piedi.
                  </p>
                )}
                {closedStops.has(fermataSel.id) ? (
                  <div className="alert alert-danger py-2 small" role="status">
                    <strong>Fermata sospesa:</strong> i bus non fermano qui. Leggi l'avviso qui sopra per la fermata
                    alternativa.
                  </div>
                ) : (
                  <InArrivo
                    arrivi={arrivi}
                    linee={linee}
                    fermate={fermateById}
                    prossimaPartenza={partenze[0]}
                    onBus={(corsa, pos) => {
                      setCorsaEvidenziata(corsa);
                      setCentraSu(pos);
                    }}
                  />
                )}
                <button
                  type="button"
                  className="btn btn-outline-primary btn-sm btn-icon mb-2"
                  onClick={() => {
                    setLuogoScelto({
                      campo: "a",
                      luogo: { tipo: "fermata", id: fermataSel.id, nome: fermataSel.nome, lat: fermataSel.lat, lon: fermataSel.lon },
                    });
                    setPannello("percorso");
                  }}
                >
                  <Icona nome="it-flag" classe="icon-sm icon-primary" />
                  <span>Portami qui</span>
                </button>
                <h3 className="h5 mt-3">Prossimi passaggi</h3>
                <Partenze partenze={partenze} oggi={oggi} aPiediMin={vicinaSel?.a_piedi_min} onCorsa={setCorsaEvidenziata} />
                {bikesNearStop.length > 0 && (
                  <div className="mt-3">
                    <BikeStations stations={bikesNearStop} title="Bici condivise vicino alla fermata" onStation={showBikeStation} />
                  </div>
                )}
              </div>
            )}

            {pannello === "percorso" && (
              <ComeArrivo
                posizione={posizione}
                chiediPosizione={localizza}
                dallaMappa={luogoScelto}
                onScegliSullaMappa={(campo) => {
                  setSceltaCampo(campo);
                  if (campo && window.matchMedia(MOBILE).matches)
                    document.querySelector(".mappa-box")?.scrollIntoView({ behavior: "smooth", block: "center" });
                }}
                sceltaInCorso={sceltaCampo}
                selezionato={itinerario}
                onItinerario={setItinerario}
              />
            )}

            {pannello === "assistente" && info.assistente && (
              <Assistente
                esempi={info.esempi_assistente}
                posizione={posizione}
                onFermata={(id) => setSelezionata(id)}
              />
            )}

            {pannello === "servizio" && (
              <div className="d-flex flex-column gap-3">
                <section className="card-biglietti p-3" aria-labelledby="titolo-biglietti">
                  <h2 id="titolo-biglietti" className="h5">
                    Biglietti
                  </h2>
                  <p className="small mb-3">{info.biglietti.info}</p>
                  {info.biglietti.url && (
                    <>
                      <a
                        className="btn btn-primary btn-icon w-100 justify-content-center gap-2"
                        href={info.biglietti.url}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        <span>Acquista il biglietto</span>
                        <Icona nome="it-external-link" classe="icon-white icon-sm" />
                        <span className="visually-hidden"> (sito esterno, si apre in una nuova scheda)</span>
                      </a>
                      <p className="small text-muted mt-2 mb-0">
                        Acquisto e pagamento avvengono sul sito {info.biglietti.nome ? `di ${info.biglietti.nome}` : "dell'azienda di trasporto"}:
                        QuandoPassa non vende biglietti e non riceve dati di pagamento.
                      </p>
                    </>
                  )}
                </section>
                <div className="card card-bg no-after">
                  <div className="card-body p-3">
                    <h2 className="h5 card-title mb-1">{info.agenzia}</h2>
                    <p className="small mb-0">
                      <Icona nome="it-telephone" classe="icon-xs" />{" "}
                      <a href={`tel:${info.telefono.replace(/\s/g, "")}`}>{info.telefono}</a>
                    </p>
                    <p className="small text-muted mb-0">Versione orario {info.versione_feed}</p>
                  </div>
                </div>
                <section aria-labelledby="titolo-linee">
                  <h2 id="titolo-linee" className="h5">Linee</h2>
                  <ul className="list-unstyled d-flex flex-column gap-2 mb-0">
                    {linee.map((l) => (
                      <li key={l.id} className="d-flex align-items-center gap-2">
                        <span className="badge badge-linea" style={{ background: l.colore }}>
                          {l.nome}
                        </span>
                        <span>
                          <strong className="d-block">{l.nome_esteso}</strong>
                          <span className="small text-muted">{l.fermate.length} fermate · percorso circolare</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
                <section aria-labelledby="titolo-dati">
                  <h2 id="titolo-dati" className="h5">Come leggere i dati</h2>
                  <ul className="small mb-0 ps-3">
                    {info.avvisi.map((a) => (
                      <li key={a}>{a}</li>
                    ))}
                  </ul>
                </section>
              </div>
            )}
          </div>
        </section>
      </div>

      <footer id="piede" className="it-footer">
        <div className="it-footer-main">
          <div className="container py-4">
            <div className="row g-4">
              <div className="col-md-6">
                <h2 className="h5 text-white">{info.comune}</h2>
                <p className="small text-white mb-1">{info.servizio}</p>
                <p className="small text-white mb-0">
                  Gestore: {info.agenzia} · tel. {info.telefono}
                </p>
              </div>
              <div className="col-md-6">
                <h2 className="h6 text-white">Come leggere i dati</h2>
                <ul className="list-unstyled small text-white mb-3">
                  {info.avvisi.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
                <ul className="list-unstyled small mb-0">
                  <li>
                    <a className="text-white" href="https://form.agid.gov.it/">
                      Dichiarazione di accessibilità
                    </a>
                  </li>
                  <li>
                    <a className="text-white" href="/api/docs">
                      API aperte del servizio
                    </a>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
        <div className="it-footer-small-prints py-2">
          <div className="container small text-white">
            La posizione resta sul tuo dispositivo. Orari stimati dall'orario programmato (feed GTFS{" "}
            {info.versione_feed}): verifica sempre alla fermata.
          </div>
        </div>
      </footer>
    </>
  );
}

/** Ora reale del servizio (Europe/Rome): le posizioni dei bus si aggiornano ogni secondo. */
function Orologio({ adesso }: { adesso: Date }) {
  return (
    <div className="ms-auto d-flex align-items-center gap-1 text-primary" aria-live="off">
      <Icona nome="it-clock" classe="icon-sm icon-primary" />
      <span className="visually-hidden">Ora attuale</span>
      <time className="tabular fw-semibold" dateTime={isoLocale(adesso)}>
        {oraLocale(adesso)}
      </time>
    </div>
  );
}

function CercaFermata({ fermate, onScelta }: { fermate: Fermata[]; onScelta: (id: string) => void }) {
  const [testo, setTesto] = useState("");
  const [aperto, setAperto] = useState(false);
  const [attiva, setAttiva] = useState(0);
  const norm = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const risultati = useMemo(() => {
    const q = norm(testo.trim());
    return fermate.filter((f) => !q || norm(`${f.codice} ${f.nome}`).includes(q)).slice(0, 12);
  }, [fermate, testo]);

  const scegli = (f: Fermata) => {
    onScelta(f.id);
    setTesto("");
    setAperto(false);
  };

  return (
    <div className="cerca">
      <Icona nome="it-search" classe="icon-sm" />
      <label htmlFor="cerca-fermata" className="visually-hidden">
        Cerca una fermata
      </label>
      <input
        id="cerca-fermata"
        type="search"
        className="form-control"
        placeholder="Cerca fermata"
        role="combobox"
        aria-expanded={aperto && risultati.length > 0}
        aria-controls="cerca-elenco"
        aria-autocomplete="list"
        aria-activedescendant={aperto && risultati[attiva] ? `cerca-${risultati[attiva].id}` : undefined}
        autoComplete="off"
        value={testo}
        onChange={(e) => {
          setTesto(e.currentTarget.value);
          setAperto(true);
          setAttiva(0);
        }}
        onFocus={() => setAperto(true)}
        onBlur={() => setTimeout(() => setAperto(false), 150)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") (e.preventDefault(), setAttiva((a) => Math.min(a + 1, risultati.length - 1)));
          else if (e.key === "ArrowUp") (e.preventDefault(), setAttiva((a) => Math.max(a - 1, 0)));
          else if (e.key === "Enter" && risultati[attiva]) (e.preventDefault(), scegli(risultati[attiva]));
          else if (e.key === "Escape") setAperto(false);
        }}
      />
      {aperto && (
        <ul id="cerca-elenco" className="cerca-elenco" role="listbox" aria-label="Fermate">
          {risultati.length === 0 ? (
            <li className="text-muted" aria-disabled="true">
              Nessuna fermata
            </li>
          ) : (
            risultati.map((f, i) => (
              <li
                key={f.id}
                id={`cerca-${f.id}`}
                role="option"
                aria-selected={i === attiva}
                onMouseDown={(e) => (e.preventDefault(), scegli(f))}
              >
                <span className="text-muted tabular me-2">{f.codice}</span>
                {f.nome}
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
