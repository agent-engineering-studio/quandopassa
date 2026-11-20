// Avvisi di servizio nell'app pubblica: in vigore adesso, fermate sospese, avvisi di una fermata.
import type { ServiceAlert } from "./api";

export const isActive = (a: ServiceAlert, now: Date) =>
  new Date(a.starts_at) <= now && (!a.ends_at || now < new Date(a.ends_at));

/** Fermate dove adesso non si sale né si scende (sospese o saltate da una deviazione). */
export function closedStopIds(alerts: ServiceAlert[], now: Date): Set<string> {
  const out = new Set<string>();
  for (const a of alerts) {
    if ((a.kind === "stop_closed" || a.kind === "detour") && isActive(a, now)) a.stop_ids.forEach((id) => out.add(id));
  }
  return out;
}

/** Avvisi che riguardano una fermata: la fermata stessa o una delle sue linee. */
export function alertsForStop(alerts: ServiceAlert[], stopId: string, lines: string[]): ServiceAlert[] {
  return alerts.filter((a) => a.stop_ids.includes(stopId) || a.route_ids.some((r) => lines.includes(r)));
}

export function alertPeriod(a: ServiceAlert): string {
  const fmt = (iso: string) =>
    new Date(iso).toLocaleString("it-IT", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  if (a.kind === "service_suspended" && a.ends_at) {
    const day = (d: Date) => d.toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long" });
    const first = new Date(a.starts_at);
    const last = new Date(new Date(a.ends_at).getTime() - 1000);
    return first.toDateString() === last.toDateString() ? day(first) : `da ${day(first)} a ${day(last)}`;
  }
  return a.ends_at ? `dal ${fmt(a.starts_at)} al ${fmt(a.ends_at)}` : `dal ${fmt(a.starts_at)}, fino a nuovo avviso`;
}
