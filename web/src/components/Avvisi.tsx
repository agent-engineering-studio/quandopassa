import { useState } from "react";
import type { ServiceAlert } from "../api";
import { alertPeriod, isActive } from "../alerts";
import Icona from "../Icona";

/** Riquadro di un avviso di servizio. */
export function AvvisoServizio({ alert, now }: { alert: ServiceAlert; now: Date }) {
  const active = isActive(alert, now);
  return (
    <div className={`avviso-servizio avviso-${alert.kind} ${active ? "" : "avviso-futuro"}`}>
      <p className="mb-0 fw-semibold">
        <span className="badge-avviso">{active ? alert.kind_label : `Dal ${new Date(alert.starts_at).toLocaleDateString("it-IT")}`}</span>{" "}
        {alert.title}
      </p>
      {alert.description && <p className="mb-0 small">{alert.description}</p>}
      <p className="mb-0 small text-muted">
        {alertPeriod(alert)}
        {alert.route_ids.length ? ` · linee ${alert.route_ids.join(", ")}` : ""}
      </p>
    </div>
  );
}

/** Barra degli avvisi sotto l'intestazione: il primo sempre visibile, gli altri a richiesta. */
export default function BarraAvvisi({ alerts, now }: { alerts: ServiceAlert[]; now: Date }) {
  const [open, setOpen] = useState(false);
  if (!alerts.length) return null;
  const sorted = [...alerts].sort((a, b) => Number(isActive(b, now)) - Number(isActive(a, now)));
  return (
    <section className="barra-avvisi px-3 py-2" aria-label="Avvisi di servizio">
      <div className="d-flex align-items-start gap-2">
        <Icona nome="it-warning-circle" classe="icon-sm flex-shrink-0 mt-1" />
        <div className="flex-grow-1 min-w-0">
          <AvvisoServizio alert={sorted[0]} now={now} />
          {open && sorted.slice(1).map((a) => <AvvisoServizio key={a.id} alert={a} now={now} />)}
        </div>
        {sorted.length > 1 && (
          <button type="button" className="btn btn-sm btn-outline-dark py-0 flex-shrink-0" aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? "Meno" : `Altri ${sorted.length - 1}`}
          </button>
        )}
      </div>
    </section>
  );
}
