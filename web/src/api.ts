// Tipi e chiamate alle API di QuandoPassa (/api/v1)

export interface Linea {
  id: string;
  nome: string;
  nome_esteso: string;
  colore: string;
  colore_testo: string;
}

export interface Fermata {
  id: string;
  codice: string;
  nome: string;
  lat: number;
  lon: number;
  descrizione: string;
  posizione: string;
  provvisoria: boolean;
  linee?: string[];
  recensioni?: { media: number; conteggio: number } | null;
}

export interface Partenza {
  corsa_id: string;
  linea_id: string;
  linea: string;
  colore: string;
  destinazione: string;
  orario: string;
  tra_minuti: number;
  in_corsa: boolean;
}

export interface FermataVicina extends Fermata {
  distanza_m: number;
  a_piedi_min: number;
  partenze: Partenza[];
}

export interface Tracciato {
  id: string;
  linea_id: string;
  fermate: string[];
  punti: [number, number][];
  progressive: number[];
  distanze_fermate: number[];
}

export interface Corsa {
  id: string;
  linea_id: string;
  destinazione: string;
  tracciato_id: string;
  fermate: string[];
  arrivi: number[];
  partenze: number[];
}

export interface OrarioGiorno {
  giorno: string;
  mezzanotte: string;
  corse: Corsa[];
  tracciati: Tracciato[];
}

export interface LineaDettaglio extends Linea {
  tracciati: Tracciato[];
  fermate: string[];
  recensioni: { media: number; conteggio: number } | null;
}

export type TipoRecensione = "fermata" | "linea" | "servizio";

export interface Info {
  agenzia: string;
  telefono: string;
  sito: string;
  versione_feed: string;
  fermate: number;
  fermate_provvisorie: number;
  linee: Linea[];
  comune: string;
  servizio: string;
  centro: [number, number];
  mappa: { tiles: string; attribuzione: string };
  ora: string;
  prossima_corsa: { corsa_id: string; linea: string; partenza: string; fermata: string } | null;
  assistente: boolean;
  esempi_assistente: string[];
  etichette: Record<TipoRecensione, string[]>;
  avvisi: string[];
  tracciati_stradali: boolean;
}

export interface Recensione {
  id: string;
  tipo: TipoRecensione;
  oggetto_id: string;
  voto: number;
  testo: string;
  tag: string[];
  autore: string;
  creata_il: string;
}

export interface Riepilogo {
  conteggio: number;
  media: number | null;
  distribuzione: Record<string, number>;
  tag: { tag: string; conteggio: number }[];
}

export interface RiepilogoConSintesi extends Riepilogo {
  oggetto: string;
  sintesi: { sintesi: string; backend: string; generato_da_ia: boolean } | null;
}

export interface RispostaAssistente {
  risposta: string;
  intento: string;
  dati: Record<string, unknown>;
  fonti: string[];
  backend: string;
  generato_da_ia: boolean;
  avviso: string;
}

async function richiesta<T>(percorso: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api/v1${percorso}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!r.ok) {
    let messaggio = `Errore ${r.status}`;
    try {
      const corpo = await r.json();
      messaggio = corpo.errore ?? (typeof corpo.detail === "string" ? corpo.detail : messaggio);
    } catch {
      /* risposta non JSON */
    }
    throw new Error(messaggio);
  }
  return r.json() as Promise<T>;
}

const q = (p: Record<string, string | number | undefined | null>) => {
  const s = new URLSearchParams();
  Object.entries(p).forEach(([k, v]) => v !== undefined && v !== null && s.set(k, String(v)));
  return s.toString();
};

export const api = {
  info: () => richiesta<Info>("/info"),
  ora: () => richiesta<{ ora: string; demo: boolean }>("/ora"),
  fermate: () => richiesta<Fermata[]>("/fermate"),
  linee: () => richiesta<LineaDettaglio[]>("/linee"),
  orario: (giorno: string) => richiesta<OrarioGiorno>(`/orario?${q({ giorno })}`),
  vicine: (lat: number, lon: number, ora?: string) =>
    richiesta<FermataVicina[]>(`/fermate/vicine?${q({ lat, lon, n: 3, ora })}`),
  partenze: (id: string, ora?: string) => richiesta<Partenza[]>(`/fermate/${id}/partenze?${q({ n: 6, ora })}`),
  assistente: (testo: string, lat?: number, lon?: number, ora?: string) =>
    richiesta<RispostaAssistente>(`/assistente?${q({ testo, lat, lon, ora })}`),
  recensioni: (tipo: TipoRecensione, id: string) =>
    richiesta<{ riepilogo: Riepilogo; recensioni: Recensione[] }>(`/recensioni?${q({ tipo, id })}`),
  riepilogo: (tipo: TipoRecensione, id: string) =>
    richiesta<RiepilogoConSintesi>(`/recensioni/riepilogo?${q({ tipo, id })}`),
  recensisci: (corpo: { tipo: TipoRecensione; id: string; voto: number; testo: string; tag: string[]; autore: string }) =>
    richiesta<Recensione>("/recensioni", { method: "POST", body: JSON.stringify(corpo) }),
};

// ------------------------------------------------------------------ formattazione
export const hhmm = (iso: string) => iso.slice(11, 16);

export function traMinuti(min: number): string {
  if (min <= 0) return "ora";
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} h ${String(min % 60).padStart(2, "0")}`;
  return `${Math.floor(h / 24)} g`;
}

export function giornoRelativo(iso: string, oggi: string): string {
  const d = iso.slice(0, 10);
  if (d === oggi) return "";
  const giorni = ["dom", "lun", "mar", "mer", "gio", "ven", "sab"];
  const dd = new Date(`${d}T12:00:00`);
  const domani = new Date(`${oggi}T12:00:00`);
  domani.setDate(domani.getDate() + 1);
  if (dd.toDateString() === domani.toDateString()) return "domani ";
  return `${giorni[dd.getDay()]} `;
}
