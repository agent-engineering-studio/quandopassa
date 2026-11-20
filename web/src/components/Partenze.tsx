import type { Partenza } from "../api";
import { giornoRelativo, hhmm, traMinuti } from "../api";

interface Props {
  partenze: Partenza[];
  oggi: string;
  aPiediMin?: number;
  onCorsa?: (id: string) => void;
}

/** Elenco dei prossimi passaggi, con l'indicazione "fai in tempo" se si conosce il tempo a piedi. */
export default function Partenze({ partenze, oggi, aPiediMin, onCorsa }: Props) {
  if (!partenze.length) return <p className="small text-muted mb-0">Nessun passaggio nei prossimi giorni.</p>;
  return (
    <ul className="list-unstyled mb-0">
      {partenze.map((p) => {
        const margine = aPiediMin !== undefined ? p.tra_minuti - aPiediMin : null;
        return (
          <li key={p.corsa_id + p.orario} className={p.suspended ? "partenza-sospesa" : undefined}>
            <button
              type="button"
              className="riga-partenza d-flex w-100 justify-content-between align-items-center gap-2 bg-transparent border-0 text-start"
              onClick={(e) => {
                e.stopPropagation();
                onCorsa?.(p.corsa_id);
              }}
              aria-label={
                p.suspended
                  ? `Linea ${p.linea} alle ${hhmm(p.orario)}: fermata sospesa, il bus non ferma qui`
                  : `Linea ${p.linea} alle ${hhmm(p.orario)}, tra ${traMinuti(p.tra_minuti)}: evidenzia il bus sulla mappa`
              }
            >
              <span className="d-flex align-items-center gap-2">
                <span className="badge badge-linea" style={{ background: p.colore }}>
                  {p.linea}
                </span>
                <span>
                  <span className="d-block fw-semibold tabular">
                    {giornoRelativo(p.orario, oggi)}
                    {hhmm(p.orario)}
                  </span>
                  <span className="d-block small text-muted">
                    {p.destinazione}
                    {p.in_corsa ? " · bus già in viaggio" : ""}
                  </span>
                </span>
              </span>
              <span className="text-end">
                {p.suspended ? (
                  <span className="esito esito-no">fermata sospesa</span>
                ) : (
                  <span className={`d-block fw-bold tabular ${p.tra_minuti <= 5 ? "imminente" : ""}`}>
                    {p.tra_minuti <= 0 ? "in partenza" : `tra ${traMinuti(p.tra_minuti)}`}
                  </span>
                )}
                {!p.suspended && margine !== null && p.tra_minuti < 120 && (
                  <span className={`esito ${margine >= 2 ? "esito-ok" : margine >= 0 ? "esito-attenzione" : "esito-no"}`}>
                    {margine >= 2 ? `fai in tempo (+${margine} min)` : margine >= 0 ? "affrettati" : "non fai in tempo"}
                  </span>
                )}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
