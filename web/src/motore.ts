// Posizione dei bus calcolata nel browser dall'orario del giorno (stessa logica di api/quandopassa/gtfs.py).
// Nessun GPS: ogni bus si muove lungo il suo tracciato in proporzione al tempo tra due fermate.

import type { Corsa, OrarioGiorno, Tracciato } from "./api";

export interface Veicolo {
  corsa: Corsa;
  lat: number;
  lon: number;
  direzione: number;
  stato: "in_fermata" | "in_viaggio";
  prossima: number; // indice della prossima fermata nella corsa
  arrivoProssima: number; // secondi dalla mezzanotte
  avanzamento: number;
}

const rad = (g: number) => (g * Math.PI) / 180;

export function rotta(a: [number, number], b: [number, number]): number {
  const y = Math.sin(rad(b[1] - a[1])) * Math.cos(rad(b[0]));
  const x =
    Math.cos(rad(a[0])) * Math.sin(rad(b[0])) - Math.sin(rad(a[0])) * Math.cos(rad(b[0])) * Math.cos(rad(b[1] - a[1]));
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

function bisectRight(arr: number[], x: number): number {
  let lo = 0;
  let hi = arr.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (x < arr[mid]) hi = mid;
    else lo = mid + 1;
  }
  return lo;
}

export function puntoA(t: Tracciato, d: number): { p: [number, number]; dir: number } {
  const tot = t.progressive[t.progressive.length - 1];
  const dd = Math.max(0, Math.min(d, tot));
  const i = Math.max(0, Math.min(bisectRight(t.progressive, dd) - 1, t.punti.length - 2));
  const a = t.punti[i];
  const b = t.punti[i + 1];
  const seg = t.progressive[i + 1] - t.progressive[i];
  const f = seg <= 0 ? 0 : (dd - t.progressive[i]) / seg;
  return { p: [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f], dir: rotta(a, b) };
}

/** Secondi trascorsi dalla mezzanotte del giorno di servizio (fuso del server). */
export function secondiDelGiorno(ora: Date, orario: OrarioGiorno): number {
  return (ora.getTime() - new Date(orario.mezzanotte).getTime()) / 1000;
}

export function veicoliAl(orario: OrarioGiorno, t: number): Veicolo[] {
  const tracciati = new Map(orario.tracciati.map((x) => [x.id, x]));
  const out: Veicolo[] = [];
  for (const c of orario.corse) {
    // le corse del giorno prima che sforano la mezzanotte hanno orari > 86400
    const tt = c.arrivi[c.arrivi.length - 1] > 86400 && t < c.partenze[0] ? t + 86400 : t;
    if (tt < c.partenze[0] || tt > c.arrivi[c.arrivi.length - 1]) continue;
    const tr = tracciati.get(c.tracciato_id);
    if (!tr) continue;
    const i = Math.max(0, bisectRight(c.partenze, tt) - 1);
    let d: number;
    let stato: Veicolo["stato"];
    if (tt <= c.partenze[i] || (c.arrivi[i] <= tt && tt <= c.partenze[i])) {
      stato = "in_fermata";
      d = tr.distanze_fermate[i];
    } else {
      const j = Math.min(i + 1, c.fermate.length - 1);
      const dur = Math.max(1, c.arrivi[j] - c.partenze[i]);
      const f = Math.max(0, Math.min(1, (tt - c.partenze[i]) / dur));
      stato = "in_viaggio";
      d = tr.distanze_fermate[i] + f * (tr.distanze_fermate[j] - tr.distanze_fermate[i]);
    }
    const { p, dir } = puntoA(tr, stato === "in_fermata" ? d + 5 : d);
    const pos = stato === "in_fermata" ? puntoA(tr, d).p : p;
    let prossima = c.arrivi.findIndex((a) => a > tt);
    if (prossima < 0) prossima = c.fermate.length - 1;
    out.push({
      corsa: c,
      lat: pos[0],
      lon: pos[1],
      direzione: dir,
      stato,
      prossima,
      arrivoProssima: c.arrivi[prossima],
      avanzamento: (tt - c.partenze[0]) / Math.max(1, c.arrivi[c.arrivi.length - 1] - c.partenze[0]),
    });
  }
  return out;
}

export const hhmmDaSecondi = (s: number) => {
  const m = Math.floor(s / 60) % (24 * 60);
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
};

export function metri(a: [number, number], b: [number, number]): number {
  const r = 6371000;
  const dp = rad(b[0] - a[0]);
  const dl = rad(b[1] - a[1]);
  const h = Math.sin(dp / 2) ** 2 + Math.cos(rad(a[0])) * Math.cos(rad(b[0])) * Math.sin(dl / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(h));
}
