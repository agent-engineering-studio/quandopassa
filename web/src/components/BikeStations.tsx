import type { NearbyBikeStation } from "../bikes";
import { availabilityText } from "../bikes";

interface Props {
  stations: NearbyBikeStation[];
  title: string;
  onStation?: (s: NearbyBikeStation) => void;
}

/** Elenco di stazioni di bike sharing con distanza, bici libere e link all'app del gestore. */
export default function BikeStations({ stations, title, onStation }: Props) {
  if (!stations.length) return null;
  return (
    <section className="bici-vicine" aria-label={title}>
      <h3 className="h6 mb-2">{title}</h3>
      <ul className="list-unstyled mb-0 d-flex flex-column gap-2">
        {stations.map((s) => (
          <li key={`${s.system_id}/${s.id}`} className="bici-riga">
            <button
              type="button"
              className="btn btn-link p-0 text-start text-decoration-none flex-grow-1"
              onClick={() => onStation?.(s)}
              aria-label={`${s.name}, ${s.distance_m} metri, ${availabilityText(s)}: mostra sulla mappa`}
            >
              <span className="bici-segno" aria-hidden="true">
                {s.live && s.bikes !== null ? s.bikes : "B"}
              </span>
              <span>
                <strong className="d-block small">{s.name}</strong>
                <span className="small text-muted">
                  {s.distance_m} m · {s.walk_min} min a piedi · {availabilityText(s)}
                </span>
              </span>
            </button>
            {s.app_url && (
              <a className="btn btn-outline-success btn-xs text-nowrap" href={s.app_url} target="_blank" rel="noopener noreferrer">
                Noleggia
              </a>
            )}
          </li>
        ))}
      </ul>
      <p className="small text-muted mt-2 mb-0">
        Bici di {[...new Set(stations.map((s) => s.system))].join(", ")}: noleggio e pagamento nell'app del gestore.
      </p>
    </section>
  );
}
