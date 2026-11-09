import { useSyncExternalStore } from "react";
import Icona from "./Icona";

type Tipo = "success" | "danger" | "warning" | "info";
interface Notifica {
  id: number;
  tipo: Tipo;
  titolo?: string;
  testo: string;
}

let elenco: Notifica[] = [];
let prossimo = 1;
const ascoltatori = new Set<() => void>();
const avvisa = () => ascoltatori.forEach((f) => f());

function chiudi(id: number) {
  elenco = elenco.filter((n) => n.id !== id);
  avvisa();
}

/** Messaggio temporaneo (alert di Bootstrap Italia), annunciato agli screen reader. */
export function notifica(tipo: Tipo, testo: string, titolo?: string) {
  const id = prossimo++;
  elenco = [...elenco, { id, tipo, testo, titolo }];
  avvisa();
  setTimeout(() => chiudi(id), 6000);
}

export function Notifiche() {
  const voci = useSyncExternalStore(
    (f) => {
      ascoltatori.add(f);
      return () => ascoltatori.delete(f);
    },
    () => elenco,
  );
  return (
    <div className="notifiche" aria-live="assertive" role="status">
      {voci.map((n) => (
        <div key={n.id} className={`alert alert-${n.tipo} alert-dismissible bg-white shadow mb-2`}>
          {n.titolo && <strong className="d-block">{n.titolo}</strong>}
          {n.testo}
          <button type="button" className="btn-close" aria-label="Chiudi avviso" onClick={() => chiudi(n.id)}>
            <Icona nome="it-close" />
          </button>
        </div>
      ))}
    </div>
  );
}
