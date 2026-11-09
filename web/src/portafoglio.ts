// Le chiavi dei biglietti restano su questo dispositivo: senza account, sono la prova d'acquisto.
// localStorage può mancare (navigazione privata, dati bloccati): ogni accesso è protetto.

const CHIAVE = "quandopassa.biglietti";

export interface VoceTitolo {
  acquistoId: string;
  chiave: string;
  titoloId?: string;
}

export function leggi(): VoceTitolo[] {
  try {
    return JSON.parse(localStorage.getItem(CHIAVE) || "[]") as VoceTitolo[];
  } catch {
    return [];
  }
}

export function salva(voci: VoceTitolo[]): boolean {
  try {
    localStorage.setItem(CHIAVE, JSON.stringify(voci));
    return true;
  } catch {
    return false;
  }
}

export function aggiungi(v: VoceTitolo): boolean {
  return salva([v, ...leggi().filter((x) => x.acquistoId !== v.acquistoId)]);
}
