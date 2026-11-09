import { useEffect, useState } from "react";
import { api } from "./api";

const FUSO = "Europe/Rome";
const fmt = new Intl.DateTimeFormat("sv-SE", {
  timeZone: FUSO,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

/** "2026-11-11T09:05:00" nell'ora locale del servizio (Europe/Rome), come la vogliono le API. */
export function isoLocale(d: Date): string {
  return fmt.format(d).replace(" ", "T");
}

export const giornoLocale = (d: Date) => isoLocale(d).slice(0, 10);
export const oraLocale = (d: Date) => isoLocale(d).slice(11, 16);

/** Orologio del servizio: l'ora reale, allineata a quella del server per non dipendere dall'orologio del telefono. */
export function useOrologio(passoMs = 1000) {
  const [scarto, setScarto] = useState(0);
  const [adesso, setAdesso] = useState(() => new Date());

  useEffect(() => {
    const t0 = Date.now();
    api
      .ora()
      .then((r) => {
        const rtt = Date.now() - t0;
        setScarto(new Date(r.ora).getTime() + rtt / 2 - Date.now());
      })
      .catch(() => setScarto(0));
  }, []);

  useEffect(() => {
    const tick = () => setAdesso(new Date(Date.now() + scarto));
    tick();
    const id = window.setInterval(tick, passoMs);
    return () => window.clearInterval(id);
  }, [scarto, passoMs]);

  return adesso;
}
