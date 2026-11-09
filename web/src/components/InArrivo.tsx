import type { Fermata, LineaDettaglio, Partenza } from "../api";
import { hhmm, traMinuti } from "../api";
import Icona, { IconaBus } from "../Icona";
import type { BusInArrivo } from "../motore";
import { hhmmDaSecondi } from "../motore";

interface Props {
  arrivi: BusInArrivo[];
  linee: LineaDettaglio[];
  fermate: Map<string, Fermata>;
  prossimaPartenza?: Partenza;
  onBus: (corsaId: string, posizione: [number, number]) => void;
}

const distanza = (m: number) => (m < 1000 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toFixed(1).replace(".", ",")} km`);

/** Il bus più vicino alla fermata: tra quanto arriva (stima dall'orario), quanto è lontano e dove si trova. */
export default function InArrivo({ arrivi, linee, fermate, prossimaPartenza, onBus }: Props) {
  const primo = arrivi[0];

  if (!primo)
    return (
      <div className="callout note my-3">
        <div className="callout-title">
          <Icona nome="it-info-circle" />
          Bus in arrivo
        </div>
        <p className="mb-0">
          Nessun bus è in viaggio verso questa fermata adesso.
          {prossimaPartenza && (
            <>
              {" "}
              Il prossimo passa alle <strong>{hhmm(prossimaPartenza.orario)}</strong> (linea {prossimaPartenza.linea},{" "}
              tra {traMinuti(prossimaPartenza.tra_minuti)}).
            </>
          )}
        </p>
      </div>
    );

  const v = primo.veicolo;
  const linea = linee.find((l) => l.id === v.corsa.linea_id);
  const dove =
    v.stato === "in_fermata"
      ? `fermo a ${fermate.get(v.corsa.fermate[Math.max(0, v.prossima - 1)])?.nome ?? "una fermata"}`
      : `diretto a ${fermate.get(v.corsa.fermate[v.prossima])?.nome ?? "la prossima fermata"}`;

  return (
    <section className="in-arrivo my-3" aria-labelledby="titolo-in-arrivo" aria-live="polite">
      <h3 id="titolo-in-arrivo" className="h6 text-uppercase text-muted mb-2">
        Bus in arrivo
      </h3>
      <button
        type="button"
        className="in-arrivo-card w-100 text-start"
        onClick={() => onBus(v.corsa.id, [v.lat, v.lon])}
        aria-label={`Mostra sulla mappa il bus della linea ${linea?.nome ?? ""}`}
      >
        <span className="d-flex align-items-center gap-3">
          <span className="in-arrivo-icona" style={{ background: linea?.colore }}>
            <IconaBus dim={22} />
            <b>{linea?.nome}</b>
          </span>
          <span className="flex-grow-1">
            <span className="in-arrivo-minuti tabular">
              {primo.giaInFermata ? "È in fermata" : primo.minuti <= 0 ? "In arrivo" : `~${primo.minuti} min`}
            </span>
            <span className="d-block small">
              {primo.giaInFermata
                ? "sta per ripartire"
                : `${primo.fermateIntermedie === 0 ? "prossima fermata" : `tra ${primo.fermateIntermedie} ${primo.fermateIntermedie === 1 ? "fermata" : "fermate"}`} · circa ${distanza(primo.metriMancanti)}`}
            </span>
          </span>
        </span>
        <span className="d-block small text-muted mt-2">
          {linea?.nome_esteso} · {dove} · arrivo previsto {hhmmDaSecondi(primo.arrivo)}
        </span>
        <span className="d-block small mt-1">
          <Icona nome="it-clock" classe="icon-xs" /> <strong>Ritardo: non rilevabile.</strong> Non c'è un GPS a bordo:
          tempo e posizione sono stimati dall'orario programmato.
        </span>
      </button>
      {arrivi.length > 1 && (
        <p className="small text-muted mt-2 mb-0">
          Poi: linea {arrivi[1].veicolo.corsa.linea_id}{" "}
          {arrivi[1].minuti <= 0 ? "in arrivo" : `tra ~${arrivi[1].minuti} min`}.
        </p>
      )}
    </section>
  );
}
