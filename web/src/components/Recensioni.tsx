import { useCallback, useEffect, useId, useState } from "react";
import type { Recensione, RiepilogoConSintesi, TipoRecensione } from "../api";
import { api } from "../api";
import Icona from "../Icona";
import { notifica } from "../notifiche";

interface Props {
  tipo: TipoRecensione;
  id: string;
  etichette: string[];
  titolo?: string;
  onCambio?: () => void;
}

const data = (iso: string) =>
  new Date(iso).toLocaleDateString("it-IT", { day: "numeric", month: "short", year: "numeric" });

function Stelle({ voto, max = 5 }: { voto: number; max?: number }) {
  const piene = Math.round(voto);
  return (
    <span className="stelle" role="img" aria-label={`${voto.toFixed(1).replace(".", ",")} stelle su ${max}`}>
      {Array.from({ length: max }).map((_, i) => (
        <Icona key={i} nome={i < piene ? "it-star-full" : "it-star-outline"} />
      ))}
    </span>
  );
}

export default function Recensioni({ tipo, id, etichette, titolo, onCambio }: Props) {
  const uid = useId();
  const [riepilogo, setRiepilogo] = useState<RiepilogoConSintesi | null>(null);
  const [elenco, setElenco] = useState<Recensione[]>([]);
  const [caricamento, setCaricamento] = useState(true);
  const [scrivi, setScrivi] = useState(false);
  const [voto, setVoto] = useState(0);
  const [tag, setTag] = useState<string[]>([]);
  const [testo, setTesto] = useState("");
  const [autore, setAutore] = useState("");
  const [invio, setInvio] = useState(false);

  const carica = useCallback(async () => {
    setCaricamento(true);
    try {
      const [r, l] = await Promise.all([api.riepilogo(tipo, id), api.recensioni(tipo, id)]);
      setRiepilogo(r);
      setElenco(l.recensioni);
    } finally {
      setCaricamento(false);
    }
  }, [tipo, id]);

  useEffect(() => {
    carica();
    setScrivi(false);
  }, [carica]);

  const invia = async () => {
    setInvio(true);
    try {
      await api.recensisci({ tipo, id, voto, testo, tag, autore });
      notifica("success", "La tua recensione è pubblicata.", "Grazie!");
      setScrivi(false);
      setVoto(0);
      setTag([]);
      setTesto("");
      await carica();
      onCambio?.();
    } catch (e) {
      notifica("danger", (e as Error).message, "Recensione non inviata");
    } finally {
      setInvio(false);
    }
  };

  if (caricamento && !riepilogo)
    return (
      <div className="progress progress-indeterminate" role="progressbar" aria-label="Caricamento recensioni">
        <div className="progress-bar" />
      </div>
    );
  const n = riepilogo?.conteggio ?? 0;

  return (
    <section aria-labelledby={`${uid}-titolo`}>
      <div className="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-3">
        <h3 id={`${uid}-titolo`} className="h5 mb-0">
          {titolo ?? "Recensioni"}
        </h3>
        {!scrivi && (
          <button type="button" className="btn btn-outline-primary btn-xs" onClick={() => setScrivi(true)}>
            Scrivi una recensione
          </button>
        )}
      </div>

      {n > 0 && riepilogo && (
        <div className="d-flex gap-4 align-items-start mb-3">
          <div className="text-center" style={{ minWidth: 80 }}>
            <div className="media-voto">{riepilogo.media?.toFixed(1).replace(".", ",")}</div>
            <Stelle voto={riepilogo.media ?? 0} />
            <div className="small text-muted">
              {n} {n === 1 ? "recensione" : "recensioni"}
            </div>
          </div>
          <dl className="flex-grow-1 mb-0">
            {[5, 4, 3, 2, 1].map((s) => {
              const quante = riepilogo.distribuzione[String(s)] ?? 0;
              return (
                <div key={s} className="d-flex align-items-center gap-2">
                  <dt className="small fw-normal" style={{ width: 14 }}>
                    {s}
                  </dt>
                  <dd className="flex-grow-1 mb-0">
                    <div className="progress" style={{ height: 6 }}>
                      <div
                        className="progress-bar bg-warning"
                        role="progressbar"
                        style={{ width: `${(100 * quante) / n}%` }}
                        aria-label={`${s} stelle: ${quante}`}
                        aria-valuenow={quante}
                        aria-valuemin={0}
                        aria-valuemax={n}
                      />
                    </div>
                  </dd>
                </div>
              );
            })}
          </dl>
        </div>
      )}

      {riepilogo && riepilogo.tag.length > 0 && (
        <ul className="list-unstyled d-flex flex-wrap gap-2 mb-3">
          {riepilogo.tag.map((t) => (
            <li key={t.tag} className="chip chip-simple">
              <span className="chip-label">
                {t.tag} · {t.conteggio}
              </span>
            </li>
          ))}
        </ul>
      )}

      {riepilogo?.sintesi && (
        <div className="callout note mt-0 mb-3">
          <div className="callout-title">
            <Icona nome="it-info-circle" />
            {riepilogo.sintesi.generato_da_ia ? "Sintesi generata dall'IA" : "Sintesi automatica"}
          </div>
          <p className="mb-0">{riepilogo.sintesi.sintesi}</p>
        </div>
      )}

      {scrivi && (
        <form
          className="card card-bg no-after p-3 mb-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (voto >= 1) invia();
          }}
        >
          <fieldset className="mb-3">
            <legend className="small fw-semibold mb-1 px-0">Il tuo voto (obbligatorio)</legend>
            <div className="voto-input" role="radiogroup" aria-label="Voto da 1 a 5 stelle">
              {[1, 2, 3, 4, 5].map((s) => (
                <button
                  key={s}
                  type="button"
                  role="radio"
                  aria-checked={voto === s}
                  aria-label={`${s} ${s === 1 ? "stella" : "stelle"}`}
                  onClick={() => setVoto(s)}
                >
                  <Icona nome={s <= voto ? "it-star-full" : "it-star-outline"} />
                </button>
              ))}
            </div>
          </fieldset>
          <fieldset className="mb-3">
            <legend className="small fw-semibold mb-1 px-0">Aspetti (facoltativi)</legend>
            <div className="d-flex flex-wrap gap-2">
              {etichette.map((e) => {
                const attivo = tag.includes(e);
                return (
                  <button
                    key={e}
                    type="button"
                    className={`btn btn-xs ${attivo ? "btn-primary" : "btn-outline-primary"}`}
                    aria-pressed={attivo}
                    onClick={() => setTag((t) => (attivo ? t.filter((x) => x !== e) : [...t, e]))}
                  >
                    {e}
                  </button>
                );
              })}
            </div>
          </fieldset>
          <div className="form-group">
            <label htmlFor={`${uid}-testo`} className="active">
              La tua esperienza (facoltativo)
            </label>
            <textarea
              id={`${uid}-testo`}
              className="form-control"
              rows={3}
              maxLength={1000}
              value={testo}
              onChange={(e) => setTesto(e.currentTarget.value)}
            />
          </div>
          <div className="form-group">
            <label htmlFor={`${uid}-autore`} className="active">
              Nome da mostrare (facoltativo)
            </label>
            <input
              id={`${uid}-autore`}
              type="text"
              className="form-control"
              maxLength={40}
              value={autore}
              onChange={(e) => setAutore(e.currentTarget.value)}
            />
          </div>
          <p className="small text-muted">
            La recensione è pubblica e anonima: non scrivere dati personali (email e numeri di telefono vengono rimossi).
          </p>
          <div className="d-flex justify-content-end gap-2">
            <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setScrivi(false)}>
              Annulla
            </button>
            <button type="submit" className="btn btn-primary btn-sm" disabled={voto < 1 || invio}>
              {invio ? "Invio…" : "Pubblica"}
            </button>
          </div>
        </form>
      )}

      {n === 0 && !scrivi && <div className="alert alert-info py-2">Ancora nessuna recensione: lascia la prima!</div>}

      <ul className="list-unstyled d-flex flex-column gap-2 mb-0">
        {elenco.map((r) => (
          <li key={r.id} className="border rounded p-2">
            <div className="d-flex justify-content-between flex-wrap gap-1">
              <span className="d-flex align-items-center gap-2">
                <strong className="small">{r.autore || "Utente anonimo"}</strong>
                <Stelle voto={r.voto} />
              </span>
              <span className="small text-muted">{data(r.creata_il)}</span>
            </div>
            {r.tag.length > 0 && <div className="small text-muted">{r.tag.join(" · ")}</div>}
            {r.testo && <p className="small mb-0 mt-1">{r.testo}</p>}
          </li>
        ))}
      </ul>
    </section>
  );
}
