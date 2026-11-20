// Client delle API del backoffice (/api/admin): sessione con cookie HttpOnly e token CSRF per le modifiche.
import type { AlertKind } from "../api";

export interface Session {
  username: string;
  csrf: string;
  expires: number;
}

export interface Stop {
  stop_id: string;
  stop_code: string;
  stop_name: string;
  category: string;
  note: string;
  search_hint: string;
  lat: number | null;
  lon: number | null;
  source: string;
  updated_at?: string;
}

export interface CalendarException {
  day: string; // AAAA-MM-GG
  type: 1 | 2;
}

export interface Calendar {
  service_id: string;
  days: string; // sette cifre 0/1 da lunedì a domenica
  start_date: string | null;
  end_date: string | null;
  note: string;
  exceptions: CalendarException[];
}

export interface VariantStop {
  stop_id: string;
  minutes: number;
}

export interface Variant {
  variant_id: string;
  route_id: string;
  short_name: string;
  long_name: string;
  color: string;
  text_color: string;
  service_id: string;
  headsign: string;
  direction_id: 0 | 1;
  sort_order: number;
  shape?: [number, number][] | null;
  stops: VariantStop[];
  departures: string[];
}

export interface Agency {
  agency_id: string;
  agency_name: string;
  agency_url: string;
  agency_timezone: string;
  agency_lang: string;
  agency_phone: string;
}

export interface FeedInfo {
  feed_publisher_name: string;
  feed_publisher_url: string;
  feed_lang: string;
  feed_start_date: string; // AAAA-MM-GG
  feed_end_date: string;
  feed_version?: string;
}

export interface Snapshot {
  agency: Agency;
  feed_info: FeedInfo;
  stops: Stop[];
  calendars: Calendar[];
  variants: Variant[];
}

export interface AdminAlert {
  id?: number;
  kind: AlertKind;
  title: string;
  description: string;
  starts_at: string;
  ends_at: string | null;
  route_ids: string[];
  stop_ids: string[];
  shape: [number, number][] | null;
  created_by?: string;
  updated_at?: string;
}

export interface SettingField {
  key: string;
  variable: string;
  label: string;
  help: string;
  value: string;
  env_value: string;
  custom: boolean;
}

export interface SettingsResponse {
  fields: SettingField[];
  read_only: { variable: string; value: string }[];
  logo: string | null;
}

export interface AuditEntry {
  id: number;
  at: string;
  username: string;
  action: string;
  target: string;
  details: Record<string, unknown> | null;
}

export interface Status {
  feed: {
    version: string;
    validity: [string, string];
    stops: number;
    provisional_stops: number;
    routes: number;
    trips: number;
    agency: string;
  };
  generated_at: string | null;
  warnings: string[];
  alerts_active: number;
  osrm: boolean;
  database: boolean;
}

export interface MutationResult<T = unknown> {
  ok: boolean;
  result: T;
  summary: Record<string, number>;
  warnings: string[];
  feed_version: string;
}

/** Errore delle API con i messaggi di verifica del feed, se ci sono. */
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public errors: string[] = [],
    public warnings: string[] = [],
  ) {
    super(message);
  }
}

let csrfToken = "";
export const setCsrf = (token: string) => {
  csrfToken = token;
};

function describeValidation(detail: { loc?: (string | number)[]; msg?: string }[]): string[] {
  return detail.map((d) => {
    const field = (d.loc ?? []).filter((x) => x !== "body").join(" › ");
    const msg = (d.msg ?? "").replace(/^Value error, /, "");
    return field ? `${field}: ${msg}` : msg;
  });
}

async function request<T>(method: string, path: string, body?: unknown, raw?: Blob): Promise<T> {
  const headers: Record<string, string> = {};
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (raw) headers["Content-Type"] = raw.type || "application/octet-stream";
  const response = await fetch(`/api/admin${path}`, {
    method,
    headers,
    credentials: "same-origin",
    body: raw ?? (body !== undefined ? JSON.stringify(body) : undefined),
  });
  if (!response.ok) {
    let message = `Errore ${response.status}`;
    let errors: string[] = [];
    let warnings: string[] = [];
    try {
      const data = await response.json();
      const detail = data.detail;
      if (typeof detail === "string") message = detail;
      else if (Array.isArray(detail)) {
        errors = describeValidation(detail);
        message = "Dati non validi";
      } else if (detail && typeof detail === "object") {
        message = detail.message ?? message;
        errors = detail.errors ?? [];
        warnings = detail.warnings ?? [];
      }
    } catch {
      /* risposta non JSON */
    }
    throw new ApiError(message, response.status, errors, warnings);
  }
  return response.json() as Promise<T>;
}

const id = (value: string) => encodeURIComponent(value);

export const admin = {
  session: () => request<Session>("GET", "/session"),
  login: (username: string, password: string) => request<Session>("POST", "/login", { username, password }),
  logout: () => request<{ ok: boolean }>("POST", "/logout"),
  status: () => request<Status>("GET", "/status"),
  data: () => request<Snapshot>("GET", "/data"),

  saveStop: (originalId: string | null, stop: Stop) =>
    originalId ? request<MutationResult>("PUT", `/stops/${id(originalId)}`, stop) : request<MutationResult>("POST", "/stops", stop),
  deleteStop: (stopId: string) => request<MutationResult>("DELETE", `/stops/${id(stopId)}`),

  saveCalendar: (originalId: string | null, calendar: Calendar) =>
    originalId
      ? request<MutationResult>("PUT", `/calendars/${id(originalId)}`, calendar)
      : request<MutationResult>("POST", "/calendars", calendar),
  deleteCalendar: (serviceId: string) => request<MutationResult>("DELETE", `/calendars/${id(serviceId)}`),

  saveVariant: (originalId: string | null, variant: Variant) =>
    originalId
      ? request<MutationResult>("PUT", `/variants/${id(originalId)}`, variant)
      : request<MutationResult>("POST", "/variants", variant),
  deleteVariant: (variantId: string) => request<MutationResult>("DELETE", `/variants/${id(variantId)}`),
  setShape: (variantId: string, points: [number, number][] | null) =>
    request<MutationResult>("PUT", `/variants/${id(variantId)}/shape`, { points }),
  computeShape: (variantId: string) => request<MutationResult>("POST", `/variants/${id(variantId)}/shape/osrm`),

  saveFeed: (agency: Agency, feedInfo: FeedInfo) =>
    request<MutationResult>("PUT", "/feed", { agency, feed_info: feedInfo }),

  alerts: (includePast: boolean) => request<AdminAlert[]>("GET", `/alerts?include_past=${includePast}`),
  saveAlert: (alertId: number | null, alert: AdminAlert) =>
    alertId
      ? request<MutationResult<number>>("PUT", `/alerts/${alertId}`, alert)
      : request<MutationResult<number>>("POST", "/alerts", alert),
  deleteAlert: (alertId: number) => request<MutationResult>("DELETE", `/alerts/${alertId}`),

  settings: () => request<SettingsResponse>("GET", "/settings"),
  saveSettings: (values: Record<string, string | null>) => request<MutationResult>("PUT", "/settings", values),
  uploadLogo: (file: File) => request<MutationResult>("PUT", "/logo", undefined, file),
  deleteLogo: () => request<MutationResult>("DELETE", "/logo"),

  audit: (limit = 200) => request<AuditEntry[]>("GET", `/audit?limit=${limit}`),
  exportUrl: (withSources: boolean) => `/api/admin/export.zip${withSources ? "?sources=true" : ""}`,
};

// ------------------------------------------------------------------ date e ore
const pad = (n: number) => String(n).padStart(2, "0");

/** ISO → valore per <input type="datetime-local"> nell'ora del browser. */
export function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Valore di <input type="datetime-local"> → ISO con fuso. */
export function fromLocalInput(value: string): string {
  return new Date(value).toISOString();
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("it-IT", { dateStyle: "medium", timeStyle: "short" });
}

export function formatDate(isoDate: string | null): string {
  if (!isoDate) return "—";
  const [y, m, d] = isoDate.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

/** Testo libero di orari ("8:30 9:00, 9.30") → ["08:30", "09:00", "09:30"], ordinati e senza doppioni. */
export function parseTimes(text: string): { times: string[]; invalid: string[] } {
  const times = new Set<string>();
  const invalid: string[] = [];
  for (const token of text.split(/[\s,;]+/).filter(Boolean)) {
    const m = token.match(/^(\d{1,2})[:.](\d{2})$/);
    if (!m || Number(m[1]) > 47 || Number(m[2]) > 59) invalid.push(token);
    else times.add(`${pad(Number(m[1]))}:${m[2]}`);
  }
  return { times: [...times].sort(), invalid };
}

/** Partenze da "inizio" a "fine" ogni "ogni" minuti. */
export function seriesOfTimes(start: string, end: string, every: number): string[] {
  const toMin = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));
  const out: string[] = [];
  if (!start || !end || every <= 0) return out;
  for (let t = toMin(start); t <= toMin(end); t += every) out.push(`${pad(Math.floor(t / 60))}:${pad(t % 60)}`);
  return out;
}
