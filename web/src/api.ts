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
}

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
  avvisi: string[];
  tracciati_stradali: boolean;
  biglietti: InfoBiglietti;
}

export interface Tariffa {
  tipo: "corsa" | "carnet" | "abbonamento";
  nome: string;
  importo_cent: number;
  corse: number | null;
  validita_min: number | null;
  giorni: number | null;
  descrizione: string;
}

export interface InfoBiglietti {
  attivi: boolean;
  tariffe?: Tariffa[];
  pagamenti?: string;
  fonte?: string;
}

export interface Acquisto {
  acquisto_id: string;
  chiave: string;
  tipo: string;
  nome: string;
  importo_cent: number;
  causale: string;
  riferimento: string;
  url_pagamento: string | null;
  simulato: boolean;
}

export interface Titolo {
  id: string;
  tipo: "corsa" | "carnet" | "abbonamento";
  nome: string;
  stato: "pronto" | "attivo" | "esaurito" | "scaduto";
  corse_totali: number | null;
  corse_rimaste: number | null;
  valido_dal: string;
  valido_al: string | null;
  validita_min: number | null;
  attivazione: { codice: string; attivata: string; scade: string; qr: string; qr_img: string } | null;
}

export interface EsitoVerifica {
  esito: "valido" | "scaduto" | "non_valido";
  messaggio: string;
  verificato: string;
  codice?: string;
  titolo?: string;
  scade?: string;
}

export interface Luogo {
  tipo: "fermata" | "luogo" | "posizione" | "mappa";
  id?: string;
  nome: string;
  dettaglio?: string;
  lat: number;
  lon: number;
}

export interface PuntoItinerario {
  id?: string;
  nome: string;
  lat: number;
  lon: number;
  orario?: string;
}

export interface TrattoPiedi {
  tipo: "piedi";
  da: PuntoItinerario;
  a: PuntoItinerario;
  metri: number;
  minuti: number;
  partenza: string;
  arrivo: string;
  punti: [number, number][];
}

export interface TrattoBus {
  tipo: "bus";
  linea: string;
  linea_id: string;
  nome_linea: string;
  colore: string;
  corsa_id: string;
  destinazione: string;
  salita: PuntoItinerario;
  discesa: PuntoItinerario;
  fermate_intermedie: number;
  minuti: number;
  attesa_min: number;
  punti: [number, number][];
}

export interface Itinerario {
  partenza: string;
  arrivo: string;
  durata_min: number;
  attesa_iniziale_min: number;
  cambi: number;
  a_piedi_m: number;
  a_piedi_min: number;
  linee: string[];
  tratti: (TrattoPiedi | TrattoBus)[];
}

export interface RispostaItinerari {
  ora: string;
  origine: PuntoItinerario;
  destinazione: PuntoItinerario;
  opzioni: Itinerario[];
  avviso: string;
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
  luoghi: (testo: string) => richiesta<Luogo[]>(`/luoghi?${q({ q: testo })}`),
  itinerari: (da: Luogo, a: Luogo) =>
    richiesta<RispostaItinerari>(
      `/itinerari?${q({ da_lat: da.lat, da_lon: da.lon, a_lat: a.lat, a_lon: a.lon, da_nome: da.nome, a_nome: a.nome })}`,
    ),
  acquista: (tipo: string) => richiesta<Acquisto>("/biglietti/acquisti", { method: "POST", body: JSON.stringify({ tipo }) }),
  pagamentoSimulato: (a: Acquisto, pagato: boolean) =>
    richiesta<{ pagato: boolean }>(`/biglietti/acquisti/${a.acquisto_id}/pagamento-simulato`, {
      method: "POST",
      body: JSON.stringify({ chiave: a.chiave, pagato }),
    }),
  conferma: (acquistoId: string, chiave: string) =>
    richiesta<Titolo>(`/biglietti/acquisti/${acquistoId}/conferma`, { method: "POST", body: JSON.stringify({ chiave }) }),
  portafoglio: (chiavi: string[]) =>
    richiesta<Titolo[]>("/biglietti/portafoglio", { method: "POST", body: JSON.stringify({ chiavi }) }),
  attiva: (id: string, chiave: string) =>
    richiesta<Titolo>(`/biglietti/titoli/${id}/attiva`, { method: "POST", body: JSON.stringify({ chiave }) }),
  verifica: (codice: string, credenziali: string) =>
    richiesta<EsitoVerifica>("/biglietti/verifica", {
      method: "POST",
      body: JSON.stringify({ codice }),
      headers: { Authorization: `Basic ${credenziali}` },
    }),
  assistente: (testo: string, lat?: number, lon?: number, ora?: string) =>
    richiesta<RispostaAssistente>(`/assistente?${q({ testo, lat, lon, ora })}`),
};

// ------------------------------------------------------------------ formattazione
export const hhmm = (iso: string) => iso.slice(11, 16);
export const euro = (cent: number) => `${(cent / 100).toFixed(2).replace(".", ",")} €`;

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
