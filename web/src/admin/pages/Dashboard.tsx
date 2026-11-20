// Cruscotto: stato del feed pubblicato, avvisi in corso e problemi da sistemare.
import { admin, formatDate, formatDateTime } from "../api";
import { PageTitle, useAdmin } from "../ui";

const yyyymmdd = (s: string) => (s ? `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}` : null);

export default function Dashboard() {
  const { status, info } = useAdmin();
  if (!status) return <p>Caricamento…</p>;
  const f = status.feed;
  const tiles = [
    { label: "Fermate", value: f.stops, note: f.provisional_stops ? `${f.provisional_stops} senza posizione` : "tutte sulla mappa", href: "#/fermate" },
    { label: "Linee", value: f.routes, note: `${f.trips} corse programmate`, href: "#/linee" },
    { label: "Avvisi in corso o in arrivo", value: status.alerts_active, note: "visibili ai cittadini", href: "#/avvisi" },
  ];
  return (
    <>
      <PageTitle title="Cruscotto">
        <a className="btn btn-outline-primary btn-sm" href={admin.exportUrl(false)}>
          Scarica il GTFS (zip)
        </a>
      </PageTitle>
      {!status.database && (
        <div className="alert alert-warning">Il database non risponde: la mappa pubblica funziona, le modifiche no.</div>
      )}
      <div className="row g-3 mb-4">
        {tiles.map((t) => (
          <div className="col-12 col-md-4" key={t.label}>
            <a className="card card-bg shadow-sm h-100 text-decoration-none" href={t.href}>
              <div className="card-body">
                <p className="small text-muted mb-1">{t.label}</p>
                <p className="display-6 fw-bold mb-1 tabular">{t.value}</p>
                <p className="small mb-0">{t.note}</p>
              </div>
            </a>
          </div>
        ))}
      </div>
      <div className="row g-4">
        <div className="col-12 col-lg-6">
          <h2 className="h5">Feed pubblicato</h2>
          <dl className="row small mb-0">
            <dt className="col-5">Azienda</dt>
            <dd className="col-7">{f.agency}</dd>
            <dt className="col-5">Valido</dt>
            <dd className="col-7">
              dal {formatDate(yyyymmdd(f.validity[0]))} al {formatDate(yyyymmdd(f.validity[1]))}
            </dd>
            <dt className="col-5">Versione</dt>
            <dd className="col-7 font-monospace">{f.version}</dd>
            <dt className="col-5">Ultima generazione</dt>
            <dd className="col-7">{formatDateTime(status.generated_at)}</dd>
            <dt className="col-5">Intestazione dell'app</dt>
            <dd className="col-7">
              {info.header.title} · {info.header.entity_name}
            </dd>
          </dl>
        </div>
        <div className="col-12 col-lg-6">
          <h2 className="h5">Da controllare</h2>
          {status.warnings.length ? (
            <ul className="small">
              {status.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          ) : (
            <p className="small">Nessun avviso sul feed.</p>
          )}
        </div>
      </div>
    </>
  );
}
