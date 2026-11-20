// Componenti condivisi del backoffice: contesto, messaggi, campi, conferme, mappa.
import L from "leaflet";
import { createContext, useContext, useEffect, useId, useState, type ReactNode } from "react";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import type { Info } from "../api";
import { ApiError, type MutationResult, type Snapshot, type Status } from "./api";

// ------------------------------------------------------------------ contesto
export interface Message {
  kind: "success" | "danger" | "warning";
  text: string;
  errors: string[];
  warnings: string[];
}

export interface AdminContextValue {
  username: string;
  info: Info;
  data: Snapshot | null;
  status: Status | null;
  reload: () => Promise<void>;
  notify: (message: Message | null) => void;
}

export const AdminContext = createContext<AdminContextValue | null>(null);

export function useAdmin(): AdminContextValue {
  const value = useContext(AdminContext);
  if (!value) throw new Error("useAdmin fuori dal backoffice");
  return value;
}

/**
 * Esegue una modifica: messaggio di esito con gli avvisi del feed, poi ricarica i dati.
 * Restituisce il risultato, oppure null se la modifica non è andata a buon fine.
 */
export function useSave() {
  const { notify, reload } = useAdmin();
  const [busy, setBusy] = useState(false);
  async function save<T>(action: () => Promise<MutationResult<T>>, success: string): Promise<MutationResult<T> | null> {
    setBusy(true);
    try {
      const result = await action();
      await reload();
      notify({
        kind: "success",
        text: `${success} La mappa pubblica è già aggiornata.`,
        errors: [],
        warnings: result.warnings,
      });
      return result;
    } catch (e) {
      notify(errorMessage(e));
      return null;
    } finally {
      setBusy(false);
    }
  }
  return { save, busy };
}

export function errorMessage(e: unknown): Message {
  if (e instanceof ApiError) return { kind: "danger", text: e.message, errors: e.errors, warnings: e.warnings };
  return { kind: "danger", text: (e as Error).message || "Errore imprevisto", errors: [], warnings: [] };
}

// ------------------------------------------------------------------ messaggi
export function Notice({ message, onClose }: { message: Message | null; onClose: () => void }) {
  return (
    <div aria-live="polite" aria-atomic="true">
      {message && (
        <div className={`alert alert-${message.kind} alert-dismissible mb-4`} role={message.kind === "danger" ? "alert" : "status"}>
          <p className="mb-1 fw-semibold">{message.text}</p>
          {message.errors.length > 0 && (
            <ul className="mb-1">
              {message.errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          )}
          {message.warnings.length > 0 && (
            <details className="small mt-1">
              <summary>Avvisi sul feed ({message.warnings.length})</summary>
              <ul className="mb-0 mt-1">
                {message.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </details>
          )}
          <button type="button" className="btn-close" aria-label="Chiudi il messaggio" onClick={onClose} />
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ campi
interface FieldProps {
  label: string;
  value: string | number | null;
  onChange: (value: string) => void;
  type?: string;
  help?: string;
  required?: boolean;
  disabled?: boolean;
  placeholder?: string;
  pattern?: string;
  min?: string | number;
  max?: string | number;
  step?: string | number;
  textarea?: boolean;
  rows?: number;
  className?: string;
}

export function Field(p: FieldProps) {
  const uid = useId();
  const helpId = p.help ? `${uid}-aiuto` : undefined;
  const common = {
    id: uid,
    className: "form-control",
    value: p.value ?? "",
    required: p.required,
    disabled: p.disabled,
    placeholder: p.placeholder,
    "aria-describedby": helpId,
  };
  return (
    <div className={`mb-3 ${p.className ?? ""}`}>
      <label htmlFor={uid} className="small fw-semibold mb-1 d-block">
        {p.label}
        {p.required && <span aria-hidden="true"> *</span>}
      </label>
      {p.textarea ? (
        <textarea {...common} rows={p.rows ?? 3} onChange={(e) => p.onChange(e.target.value)} />
      ) : (
        <input
          {...common}
          type={p.type ?? "text"}
          pattern={p.pattern}
          min={p.min}
          max={p.max}
          step={p.step}
          onChange={(e) => p.onChange(e.target.value)}
        />
      )}
      {p.help && (
        <small id={helpId} className="form-text d-block text-muted">
          {p.help}
        </small>
      )}
    </div>
  );
}

export function Select({
  label,
  value,
  onChange,
  options,
  help,
  required,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  help?: string;
  required?: boolean;
}) {
  const uid = useId();
  return (
    <div className="mb-3">
      <label htmlFor={uid} className="small fw-semibold mb-1 d-block">
        {label}
        {required && <span aria-hidden="true"> *</span>}
      </label>
      <select id={uid} className="form-select" value={value} required={required} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {help && <small className="form-text d-block text-muted">{help}</small>}
    </div>
  );
}

/** Pulsante in due passi: il primo clic chiede conferma, il secondo esegue. */
export function ConfirmButton({
  label,
  confirmLabel,
  onConfirm,
  disabled,
}: {
  label: string;
  confirmLabel: string;
  onConfirm: () => void;
  disabled?: boolean;
}) {
  const [asking, setAsking] = useState(false);
  useEffect(() => {
    if (!asking) return;
    const t = setTimeout(() => setAsking(false), 6000);
    return () => clearTimeout(t);
  }, [asking]);
  return asking ? (
    <span className="d-inline-flex gap-2">
      <button type="button" className="btn btn-danger btn-sm" disabled={disabled} onClick={() => { setAsking(false); onConfirm(); }}>
        {confirmLabel}
      </button>
      <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setAsking(false)}>
        Annulla
      </button>
    </span>
  ) : (
    <button type="button" className="btn btn-outline-danger btn-sm" disabled={disabled} onClick={() => setAsking(true)}>
      {label}
    </button>
  );
}

export function PageTitle({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-3">
      <h1 className="h3 mb-0">{title}</h1>
      <div className="d-flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

// ------------------------------------------------------------------ mappa
function FitTo({ points }: { points: [number, number][] }) {
  const map = useMap();
  const key = points.map((p) => p.join(",")).join(";");
  useEffect(() => {
    // senza animazione: se si cambia pagina durante lo zoom Leaflet non trova più la mappa
    if (points.length > 1) map.fitBounds(L.latLngBounds(points), { padding: [30, 30], maxZoom: 17, animate: false });
    else if (points.length === 1) map.setView(points[0], 17, { animate: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, map]);
  return null;
}

/** Mappa con le tile e il centro configurati per l'app pubblica. */
export function BaseMap({
  children,
  fit = [],
  height = 460,
  label,
}: {
  children?: ReactNode;
  fit?: [number, number][];
  height?: number;
  label: string;
}) {
  const { info } = useAdmin();
  return (
    <div className="mappa-admin" style={{ height }} role="region" aria-label={label}>
      <MapContainer center={info.centro} zoom={15} className="h-100 w-100" scrollWheelZoom>
        <TileLayer url={info.mappa.tiles} attribution={info.mappa.attribuzione} />
        <FitTo points={fit} />
        {children}
      </MapContainer>
    </div>
  );
}

/** Indicatore di una fermata sulla mappa del backoffice. */
export function stopIcon(text: string, kind: "normal" | "selected" | "closed" | "provisional" = "normal") {
  return L.divIcon({
    className: `pin-fermata pin-${kind}`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    html: `<span>${text.replace(/[<>&"]/g, "")}</span>`,
  });
}
