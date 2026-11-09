import { useEffect, useRef, useState } from "react";
import type { RispostaAssistente } from "../api";
import { api } from "../api";
import Icona from "../Icona";

interface Messaggio {
  da: "utente" | "assistente";
  testo: string;
  meta?: RispostaAssistente;
}

interface Props {
  esempi: string[];
  posizione: { lat: number; lon: number } | null;
  ora?: string;
  onFermata?: (id: string) => void;
}

export default function Assistente({ esempi, posizione, ora, onFermata }: Props) {
  const [messaggi, setMessaggi] = useState<Messaggio[]>([
    {
      da: "assistente",
      testo:
        "Ciao! Sono l'assistente del bus urbano. Chiedimi quando passa il bus, come arrivare in un posto o dove si trova una linea.",
    },
  ]);
  const [testo, setTesto] = useState("");
  const [attesa, setAttesa] = useState(false);
  const chat = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chat.current?.scrollTo({ top: chat.current.scrollHeight, behavior: "smooth" });
  }, [messaggi]);

  const chiedi = async (domanda: string) => {
    if (!domanda.trim() || attesa) return;
    setMessaggi((m) => [...m, { da: "utente", testo: domanda }]);
    setTesto("");
    setAttesa(true);
    try {
      const r = await api.assistente(domanda, posizione?.lat, posizione?.lon, ora);
      setMessaggi((m) => [...m, { da: "assistente", testo: r.risposta, meta: r }]);
      const f = (r.dati as { fermata?: { id: string } }).fermata;
      if (f?.id) onFermata?.(f.id);
    } catch (e) {
      setMessaggi((m) => [...m, { da: "assistente", testo: (e as Error).message }]);
    } finally {
      setAttesa(false);
    }
  };

  return (
    <section aria-labelledby="titolo-assistente">
      <h2 id="titolo-assistente" className="h5">
        Chiedi all'assistente
      </h2>
      <div ref={chat} className="chat d-flex flex-column gap-2 mb-3" aria-live="polite">
        {messaggi.map((m, i) => (
          <div key={i} className={`fumetto ${m.da === "utente" ? "fumetto-utente" : "fumetto-assistente"}`}>
            <span className="visually-hidden">{m.da === "utente" ? "Tu: " : "Assistente: "}</span>
            {m.testo}
            {m.meta && (
              <span className="d-block small text-muted mt-1">
                {m.meta.generato_da_ia ? "Risposta generata con IA" : "Risposta automatica"} ·{" "}
                {m.meta.fonti.join(", ") || "base di conoscenza"}
              </span>
            )}
          </div>
        ))}
        {attesa && <p className="small text-muted mb-0">Sto controllando l'orario…</p>}
      </div>

      <div className="d-flex flex-wrap gap-2 mb-3" role="group" aria-label="Domande di esempio">
        {esempi.slice(0, 4).map((e) => (
          <button key={e} type="button" className="btn btn-outline-primary btn-xs" onClick={() => chiedi(e)}>
            {e}
          </button>
        ))}
      </div>

      <form
        className="d-flex gap-2 align-items-end"
        onSubmit={(e) => {
          e.preventDefault();
          chiedi(testo);
        }}
      >
        <div className="form-group mb-0 flex-grow-1">
          <label htmlFor="domanda" className="active">
            La tua domanda
          </label>
          <input
            id="domanda"
            type="text"
            className="form-control"
            placeholder="es. quando passa la A in piazza?"
            value={testo}
            maxLength={500}
            autoComplete="off"
            onChange={(e) => setTesto(e.currentTarget.value)}
          />
        </div>
        <button type="submit" className="btn btn-primary" disabled={attesa || !testo.trim()}>
          <Icona nome="it-arrow-right" classe="icon-white icon-sm" />
          <span className="visually-hidden">Invia</span>
        </button>
      </form>
      <p className="small text-muted mt-2 mb-0">
        <Icona nome="it-info-circle" classe="icon-xs" /> Assistente automatico (IA): le risposte si basano sull'orario
        programmato, verifica sempre alla fermata. La posizione, se attiva, serve solo a questa domanda e non viene
        salvata.
      </p>
    </section>
  );
}
