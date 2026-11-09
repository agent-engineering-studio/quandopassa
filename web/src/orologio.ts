import { useCallback, useEffect, useState } from "react";
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

/**
 * Orologio del servizio: allineato all'ora del server (che in demo può partire da DEMO_ORA)
 * e, se l'utente sceglie "simula orario", spostato all'istante voluto. Scorre in entrambi i casi.
 */
export function useOrologio(passoMs = 1000) {
  const [scartoServer, setScartoServer] = useState(0);
  const [scartoSimulato, setScartoSimulato] = useState<number | null>(null);
  const [adesso, setAdesso] = useState(() => new Date());

  useEffect(() => {
    const t0 = Date.now();
    api
      .ora()
      .then((r) => {
        const rtt = Date.now() - t0;
        setScartoServer(new Date(r.ora).getTime() + rtt / 2 - Date.now());
      })
      .catch(() => setScartoServer(0));
  }, []);

  const scarto = scartoServer + (scartoSimulato ?? 0);
  useEffect(() => {
    const tick = () => setAdesso(new Date(Date.now() + scarto));
    tick();
    const id = window.setInterval(tick, passoMs);
    return () => window.clearInterval(id);
  }, [scarto, passoMs]);

  const simula = useCallback(
    (istante: Date | null) => {
      if (istante === null) setScartoSimulato(null);
      else setScartoSimulato(istante.getTime() - (Date.now() + scartoServer));
    },
    [scartoServer],
  );

  return { adesso, simulato: scartoSimulato !== null, simula };
}

/** Converte "YYYY-MM-DDTHH:mm" (ora di Roma) in Date. */
export function daLocale(iso: string): Date {
  // stima dell'offset di Roma per quella data (CET/CEST)
  const prova = new Date(`${iso}:00Z`);
  const comeRoma = new Date(isoLocale(prova) + "Z");
  return new Date(prova.getTime() - (comeRoma.getTime() - prova.getTime()));
}
