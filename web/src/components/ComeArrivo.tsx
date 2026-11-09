import { useEffect, useId, useRef, useState } from "react";
import type { Itinerario, Luogo, RispostaItinerari, TrattoBus } from "../api";
import { api, hhmm } from "../api";
import Icona, { IconaPiedi } from "../Icona";

export type Campo = "da" | "a";

interface Props {
  posizione: { lat: number; lon: number } | null;
  chiediPosizione: () => void;
  /** punto appena scelto toccando la mappa, per il campo indicato */
  dallaMappa: { campo: Campo; luogo: Luogo } | null;
  onScegliSullaMappa: (campo: Campo | null) => void;
  sceltaInCorso: Campo | null;
  selezionato: Itinerario | null;
  onItinerario: (it: Itinerario | null) => void;
}

const distanza = (m: number) => (m < 1000 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toFixed(1).replace(".", ",")} km`);
const durata = (min: number) => (min < 60 ? `${min} min` : `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, "0")}`);

/** "Come arrivo": da un luogo a un altro con a piedi, bus e cambi, come su un navigatore. */
export default function ComeArrivo(p: Props) {
  const [da, setDa] = useState<Luogo | null>(null);
  const [a, setA] = useState<Luogo | null>(null);
  const [risposta, setRisposta] = useState<RispostaItinerari | null>(null);
  const [attesa, setAttesa] = useState(false);
  const [errore, setErrore] = useState<string | null>(null);

  // la mia posizione come partenza predefinita, appena disponibile
  useEffect(() => {
    if (p.posizione && (!da || da.tipo === "posizione"))
      setDa({ tipo: "posizione", nome: "La mia posizione", lat: p.posizione.lat, lon: p.posizione.lon });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.posizione]);

  useEffect(() => {
    if (!p.dallaMappa) return;
    (p.dallaMappa.campo === "da" ? setDa : setA)(p.dallaMappa.luogo);
  }, [p.dallaMappa]);

  useEffect(() => {
    if (!da || !a) {
      setRisposta(null);
      p.onItinerario(null);
      return;
    }
    let valido = true;
    setAttesa(true);
    setErrore(null);
    api
      .itinerari(da, a)
      .then((r) => {
        if (!valido) return;
        setRisposta(r);
        p.onItinerario(r.opzioni[0] ?? null);
      })
      .catch((e) => valido && setErrore((e as Error).message))
      .finally(() => valido && setAttesa(false));
    return () => {
      valido = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [da?.lat, da?.lon, a?.lat, a?.lon]);

  return (
    <section aria-labelledby="titolo-come-arrivo">
      <h2 id="titolo-come-arrivo" className="h5">
        Come arrivo
      </h2>
      <div className="come-arrivo-campi">
        <CampoLuogo
          etichetta="Partenza"
          icona="it-map-marker-circle"
          valore={da}
          onValore={setDa}
          posizione={p.posizione}
          chiediPosizione={p.chiediPosizione}
          onMappa={() => p.onScegliSullaMappa("da")}
          inScelta={p.sceltaInCorso === "da"}
        />
        <button
          type="button"
          className="btn btn-icon btn-sm btn-outline-primary scambia"
          onClick={() => {
            setDa(a);
            setA(da);
          }}
          disabled={!da && !a}
          aria-label="Scambia partenza e arrivo"
          title="Scambia partenza e arrivo"
        >
          <Icona nome="it-exchange-circle" classe="icon-sm icon-primary" />
        </button>
        <CampoLuogo
          etichetta="Arrivo"
          icona="it-flag"
          valore={a}
          onValore={setA}
          posizione={p.posizione}
          chiediPosizione={p.chiediPosizione}
          onMappa={() => p.onScegliSullaMappa("a")}
          inScelta={p.sceltaInCorso === "a"}
        />
      </div>

      <div aria-live="polite" className="mt-3">
        {!da || !a ? (
          <p className="small text-muted mb-0">
            <Icona nome="it-info-circle" classe="icon-xs" /> Scegli partenza e arrivo: una fermata, un indirizzo, un luogo
            o un punto sulla mappa. Ti diciamo quali bus prendere, dove cambiare e quanto si cammina.
          </p>
        ) : attesa ? (
          <div className="progress progress-indeterminate" role="progressbar" aria-label="Calcolo del percorso">
            <div className="progress-bar" />
          </div>
        ) : errore ? (
          <div className="alert alert-danger py-2">{errore}</div>
        ) : risposta && risposta.opzioni.length === 0 ? (
          <div className="alert alert-info py-2">Nessun percorso trovato nei prossimi giorni.</div>
        ) : (
          risposta && (
            <>
              <ol className="list-unstyled d-flex flex-column gap-2 mb-2" aria-label="Soluzioni di viaggio">
                {risposta.opzioni.map((o, i) => (
                  <li key={i}>
                    <Soluzione
                      it={o}
                      aperta={p.selezionato === o}
                      onApri={() => p.onItinerario(o)}
                    />
                  </li>
                ))}
              </ol>
              <p className="small text-muted mb-0">
                <Icona nome="it-clock" classe="icon-xs" /> {risposta.avviso} I tratti a piedi sono stimati in linea d'aria.
              </p>
            </>
          )
        )}
      </div>
    </section>
  );
}

function Soluzione({ it, aperta, onApri }: { it: Itinerario; aperta: boolean; onApri: () => void }) {
  const soloPiedi = it.linee.length === 0;
  return (
    <div className={`soluzione ${aperta ? "aperta" : ""}`}>
      <button type="button" className="soluzione-testa w-100 text-start" aria-expanded={aperta} onClick={onApri}>
        <span className="d-flex justify-content-between align-items-baseline gap-2">
          <strong className="tabular fs-5">
            {hhmm(it.partenza)} – {hhmm(it.arrivo)}
          </strong>
          <strong className="tabular">{durata(it.durata_min)}</strong>
        </span>
        <span className="d-flex flex-wrap align-items-center gap-1 my-1" aria-hidden="true">
          {it.tratti.map((t, i) => (
            <span key={i} className="d-inline-flex align-items-center gap-1">
              {i > 0 && <Icona nome="it-chevron-right" classe="icon-xs" />}
              {t.tipo === "piedi" ? (
                <span className="d-inline-flex align-items-center text-muted small">
                  <IconaPiedi dim={16} />
                  {t.minuti}′
                </span>
              ) : (
                <span className="badge badge-linea" style={{ background: t.colore }}>
                  {t.linea}
                </span>
              )}
            </span>
          ))}
        </span>
        <span className="d-block small text-muted">
          {soloPiedi
            ? `Solo a piedi · ${distanza(it.a_piedi_m)}`
            : `${it.cambi === 0 ? "Diretto" : `${it.cambi} cambio`} · ${distanza(it.a_piedi_m)} a piedi · ${
                it.attesa_iniziale_min <= 0 ? "esci adesso" : `esci tra ${durata(it.attesa_iniziale_min)}`
              }`}
        </span>
      </button>
      {aperta && <Passi it={it} />}
    </div>
  );
}

function Passi({ it }: { it: Itinerario }) {
  return (
    <ol className="passi list-unstyled mb-0">
      {it.tratti.map((t, i) =>
        t.tipo === "piedi" ? (
          <li key={i} className="passo passo-piedi">
            <span className="passo-icona">
              <IconaPiedi />
            </span>
            <span>
              <span className="d-block">
                Cammina <strong>{distanza(t.metri)}</strong> fino a <strong>{t.a.nome}</strong>
              </span>
              <span className="small text-muted tabular">
                {hhmm(t.partenza)} · circa {t.minuti} min
              </span>
            </span>
          </li>
        ) : (
          <PassoBus key={i} t={t} />
        ),
      )}
      <li className="passo">
        <span className="passo-icona">
          <Icona nome="it-flag" classe="icon-sm" />
        </span>
        <span>
          Arrivo alle <strong className="tabular">{hhmm(it.arrivo)}</strong>
        </span>
      </li>
    </ol>
  );
}

function PassoBus({ t }: { t: TrattoBus }) {
  return (
    <li className="passo passo-bus" style={{ ["--c" as string]: t.colore }}>
      <span className="passo-icona">
        <span className="badge badge-linea" style={{ background: t.colore }}>
          {t.linea}
        </span>
      </span>
      <span>
        {t.attesa_min > 0 && (
          <span className="d-block small cambio">
            <Icona nome="it-exchange-circle" classe="icon-xs" /> Cambio: attesa di {durata(t.attesa_min)}
          </span>
        )}
        <span className="d-block">
          Sali sulla <strong>{t.nome_linea}</strong> a <strong>{t.salita.nome}</strong> alle{" "}
          <strong className="tabular">{hhmm(t.salita.orario!)}</strong>
        </span>
        <span className="d-block">
          Scendi a <strong>{t.discesa.nome}</strong> alle <strong className="tabular">{hhmm(t.discesa.orario!)}</strong>
        </span>
        <span className="small text-muted">
          {t.fermate_intermedie === 0 ? "fermata successiva" : `${t.fermate_intermedie + 1} fermate`} · {t.minuti} min
        </span>
      </span>
    </li>
  );
}

// ------------------------------------------------------------------ campo con suggerimenti
interface CampoProps {
  etichetta: string;
  icona: string;
  valore: Luogo | null;
  onValore: (l: Luogo | null) => void;
  posizione: { lat: number; lon: number } | null;
  chiediPosizione: () => void;
  onMappa: () => void;
  inScelta: boolean;
}

function CampoLuogo(p: CampoProps) {
  const uid = useId();
  const [testo, setTesto] = useState("");
  const [aperto, setAperto] = useState(false);
  const [voci, setVoci] = useState<Luogo[]>([]);
  const [attiva, setAttiva] = useState(0);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    window.clearTimeout(timer.current);
    if (testo.trim().length < 2) {
      setVoci([]);
      return;
    }
    timer.current = window.setTimeout(() => {
      api.luoghi(testo.trim()).then(setVoci).catch(() => setVoci([]));
    }, 350);
    return () => window.clearTimeout(timer.current);
  }, [testo]);

  const speciali: Luogo[] = [
    { tipo: "posizione", nome: "La mia posizione", lat: p.posizione?.lat ?? 0, lon: p.posizione?.lon ?? 0 },
    { tipo: "mappa", nome: "Scegli sulla mappa", lat: 0, lon: 0 },
  ];
  const elenco = [...(testo.trim() ? [] : speciali), ...voci];

  const scegli = (l: Luogo) => {
    setAperto(false);
    setTesto("");
    if (l.tipo === "mappa") return p.onMappa();
    if (l.tipo === "posizione" && !p.posizione) return p.chiediPosizione();
    p.onValore(l);
  };

  return (
    <div className="campo-luogo">
      <label htmlFor={`${uid}-campo`} className="small fw-semibold mb-1 d-block">
        {p.etichetta}
      </label>
      <div className="cerca">
        <Icona nome={p.icona} classe="icon-sm" />
        <input
          id={`${uid}-campo`}
          type="search"
          className="form-control"
          role="combobox"
          aria-expanded={aperto && elenco.length > 0}
          aria-controls={`${uid}-elenco`}
          aria-autocomplete="list"
          aria-activedescendant={aperto && elenco[attiva] ? `${uid}-v${attiva}` : undefined}
          autoComplete="off"
          placeholder={p.inScelta ? "Tocca un punto sulla mappa…" : p.valore ? p.valore.nome : "Fermata, indirizzo o luogo"}
          value={testo || (p.valore && !aperto ? p.valore.nome : "")}
          onChange={(e) => {
            setTesto(e.currentTarget.value);
            setAperto(true);
            setAttiva(0);
          }}
          onFocus={() => setAperto(true)}
          onBlur={() => setTimeout(() => setAperto(false), 150)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") (e.preventDefault(), setAttiva((x) => Math.min(x + 1, elenco.length - 1)));
            else if (e.key === "ArrowUp") (e.preventDefault(), setAttiva((x) => Math.max(x - 1, 0)));
            else if (e.key === "Enter" && elenco[attiva]) (e.preventDefault(), scegli(elenco[attiva]));
            else if (e.key === "Escape") setAperto(false);
          }}
        />
        {aperto && elenco.length > 0 && (
          <ul id={`${uid}-elenco`} className="cerca-elenco" role="listbox" aria-label={`Suggerimenti per ${p.etichetta}`}>
            {elenco.map((l, i) => (
              <li
                key={`${l.tipo}-${l.id ?? l.nome}-${i}`}
                id={`${uid}-v${i}`}
                role="option"
                aria-selected={i === attiva}
                onMouseDown={(e) => (e.preventDefault(), scegli(l))}
              >
                <span className="d-flex align-items-center gap-2">
                  <Icona
                    nome={
                      l.tipo === "fermata"
                        ? "it-map-marker"
                        : l.tipo === "posizione"
                          ? "it-map-marker-circle"
                          : l.tipo === "mappa"
                            ? "it-flag"
                            : "it-search"
                    }
                    classe="icon-xs"
                  />
                  <span>
                    <span className="d-block">{l.nome}</span>
                    {l.dettaglio && <span className="small text-muted">{l.dettaglio}</span>}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
