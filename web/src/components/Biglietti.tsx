import { useCallback, useEffect, useState } from "react";
import type { Acquisto, InfoBiglietti, Tariffa, Titolo } from "../api";
import { api, euro, hhmm } from "../api";
import Icona from "../Icona";
import { notifica } from "../notifiche";
import { isoLocale } from "../orologio";
import * as portafoglio from "../portafoglio";

interface Props {
  info: InfoBiglietti;
  adesso: Date;
}

type Fase = { tariffa: Tariffa; acquisto?: Acquisto; attesa?: boolean };

/** Colore del giorno: cambia ogni giorno, così uno screenshot di ieri si riconosce a colpo d'occhio. */
function coloreDelGiorno(giorno: string): string {
  let h = 0;
  for (const c of giorno) h = (h * 31 + c.charCodeAt(0)) % 360;
  return `hsl(${h} 70% 32%)`;
}

const conto = (ms: number) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h > 24 ? `${Math.floor(h / 24)} giorni` : `${h ? `${h}:` : ""}${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};

export default function Biglietti({ info, adesso }: Props) {
  const [titoli, setTitoli] = useState<Titolo[]>([]);
  const [fase, setFase] = useState<Fase | null>(null);
  const [daAttivare, setDaAttivare] = useState<string | null>(null);
  const [salvabile, setSalvabile] = useState(true);

  const carica = useCallback(async () => {
    const voci = portafoglio.leggi();
    // acquisti pagati ma non ancora confermati (pagina chiusa durante il pagamento): si riprova
    await Promise.all(
      voci.filter((v) => !v.titoloId).map((v) =>
        api
          .conferma(v.acquistoId, v.chiave)
          .then((t) => portafoglio.aggiungi({ ...v, titoloId: t.id }))
          .catch(() => undefined),
      ),
    );
    const chiavi = portafoglio.leggi().filter((v) => v.titoloId).map((v) => v.chiave);
    setTitoli(chiavi.length ? await api.portafoglio(chiavi).catch(() => []) : []);
  }, []);

  useEffect(() => {
    carica();
  }, [carica]);

  // alla scadenza di un biglietto attivo si ricarica lo stato
  const prossimaScadenza = titoli
    .map((t) => t.attivazione && new Date(t.attivazione.scade).getTime())
    .filter((x): x is number => !!x)
    .sort()[0];
  useEffect(() => {
    if (prossimaScadenza && adesso.getTime() >= prossimaScadenza) carica();
  }, [adesso, prossimaScadenza, carica]);

  const inizia = async (t: Tariffa) => {
    setFase({ tariffa: t, attesa: true });
    try {
      const a = await api.acquista(t.tipo);
      setSalvabile(portafoglio.aggiungi({ acquistoId: a.acquisto_id, chiave: a.chiave }));
      if (a.url_pagamento) window.location.assign(a.url_pagamento);
      else setFase({ tariffa: t, acquisto: a });
    } catch (e) {
      setFase(null);
      notifica("danger", (e as Error).message, "Acquisto non avviato");
    }
  };

  const paga = async (pagato: boolean) => {
    if (!fase?.acquisto) return;
    const a = fase.acquisto;
    setFase({ ...fase, attesa: true });
    try {
      await api.pagamentoSimulato(a, pagato);
      if (!pagato) {
        portafoglio.salva(portafoglio.leggi().filter((v) => v.acquistoId !== a.acquisto_id));
        notifica("info", "Pagamento annullato: nessun biglietto emesso.");
      } else {
        const t = await api.conferma(a.acquisto_id, a.chiave);
        portafoglio.aggiungi({ acquistoId: a.acquisto_id, chiave: a.chiave, titoloId: t.id });
        notifica("success", `${t.nome}: è nei tuoi biglietti. Attivalo quando sali.`, "Biglietto emesso");
      }
      setFase(null);
      await carica();
    } catch (e) {
      setFase({ ...fase, attesa: false });
      notifica("danger", (e as Error).message);
    }
  };

  const attiva = async (t: Titolo) => {
    const voce = portafoglio.leggi().find((v) => v.titoloId === t.id);
    if (!voce) return;
    try {
      const nuovo = await api.attiva(t.id, voce.chiave);
      setTitoli((x) => x.map((y) => (y.id === t.id ? nuovo : y)));
      setDaAttivare(null);
    } catch (e) {
      notifica("danger", (e as Error).message, "Biglietto non attivato");
    }
  };

  const simulato = info.pagamenti === "simulato";

  return (
    <section aria-labelledby="titolo-biglietti">
      <h2 id="titolo-biglietti" className="h5">
        I miei biglietti
      </h2>
      {titoli.length === 0 ? (
        <p className="small text-muted">Nessun biglietto su questo dispositivo.</p>
      ) : (
        <ul className="list-unstyled d-flex flex-column gap-3 mb-4">
          {titoli.map((t) => (
            <li key={t.id}>
              {t.attivazione ? (
                <BigliettoAttivo t={t} adesso={adesso} />
              ) : (
                <div className="card-titolo p-3">
                  <div className="d-flex justify-content-between align-items-start gap-2">
                    <div>
                      <h3 className="h6 mb-1">{t.nome}</h3>
                      <span className="small text-muted">
                        {t.corse_rimaste !== null && `${t.corse_rimaste} di ${t.corse_totali} corse rimaste`}
                        {t.valido_al && `valido fino al ${new Date(t.valido_al).toLocaleDateString("it-IT")}`}
                      </span>
                    </div>
                    <span className={`esito ${t.stato === "pronto" ? "esito-ok" : "esito-no"}`}>
                      {{ pronto: "da attivare", attivo: "attivo", esaurito: "esaurito", scaduto: "scaduto" }[t.stato]}
                    </span>
                  </div>
                  {t.stato === "pronto" &&
                    (daAttivare === t.id ? (
                      <div className="alert alert-warning py-2 mt-3 mb-0 small">
                        <strong>Attiva solo quando sali sul bus.</strong>{" "}
                        {t.tipo === "abbonamento"
                          ? "L'abbonamento resta valido fino alla scadenza."
                          : `La corsa vale ${t.validita_min} minuti e non si può annullare.`}
                        <div className="d-flex gap-2 mt-2">
                          <button type="button" className="btn btn-primary btn-xs" onClick={() => attiva(t)}>
                            Attiva adesso
                          </button>
                          <button type="button" className="btn btn-outline-primary btn-xs" onClick={() => setDaAttivare(null)}>
                            Non ancora
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button type="button" className="btn btn-primary btn-sm w-100 mt-3" onClick={() => setDaAttivare(t.id)}>
                        {t.tipo === "abbonamento" ? "Mostra l'abbonamento" : "Attiva una corsa"}
                      </button>
                    ))}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {fase?.acquisto && simulato ? (
        <div className="pagopa-simulato p-3 mb-4" role="dialog" aria-labelledby="titolo-pagopa">
          <p className="small text-uppercase fw-semibold mb-1">pagoPA · pagamento simulato</p>
          <h3 id="titolo-pagopa" className="h5 mb-3">
            Paga {euro(fase.acquisto.importo_cent)}
          </h3>
          <dl className="row small mb-3">
            <dt className="col-5">Causale</dt>
            <dd className="col-7">{fase.acquisto.causale}</dd>
            <dt className="col-5">Codice avviso</dt>
            <dd className="col-7 tabular">{fase.acquisto.riferimento}</dd>
          </dl>
          <div className="d-flex gap-2">
            <button type="button" className="btn btn-primary flex-fill" disabled={fase.attesa} onClick={() => paga(true)}>
              Paga
            </button>
            <button type="button" className="btn btn-outline-primary flex-fill" disabled={fase.attesa} onClick={() => paga(false)}>
              Annulla
            </button>
          </div>
          <p className="small mb-0 mt-2">
            <Icona nome="it-info-circle" classe="icon-xs" /> Prototipo: nessun addebito reale.
          </p>
        </div>
      ) : (
        <>
          <h2 className="h5">Acquista</h2>
          <ul className="list-unstyled d-flex flex-column gap-2 mb-2">
            {(info.tariffe ?? []).map((t) => (
              <li key={t.tipo} className="card-titolo p-3 d-flex justify-content-between align-items-center gap-3">
                <span>
                  <strong className="d-block">{t.nome}</strong>
                  <span className="small text-muted">{t.descrizione}</span>
                </span>
                <span className="text-end text-nowrap">
                  <strong className="d-block tabular fs-5">{euro(t.importo_cent)}</strong>
                  <button
                    type="button"
                    className="btn btn-outline-primary btn-xs"
                    disabled={!!fase}
                    onClick={() => inizia(t)}
                    aria-label={`Acquista ${t.nome} a ${euro(t.importo_cent)}`}
                  >
                    Acquista
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      {!salvabile && (
        <div className="alert alert-warning py-2 small">
          Il browser non permette di salvare il biglietto: non chiudere questa pagina finché non lo hai usato.
        </div>
      )}
      <p className="small text-muted mb-0">
        <Icona nome="it-info-circle" classe="icon-xs" /> {info.fonte} Senza registrazione: il biglietto resta su questo
        dispositivo.{simulato ? " Pagamento simulato: nessun addebito." : ""}
      </p>
    </section>
  );
}

function BigliettoAttivo({ t, adesso }: { t: Titolo; adesso: Date }) {
  const a = t.attivazione!;
  const restano = new Date(a.scade).getTime() - adesso.getTime();
  const oggi = isoLocale(adesso).slice(0, 10);
  return (
    <article className="biglietto-attivo" style={{ ["--giorno" as string]: coloreDelGiorno(oggi) }} aria-live="polite">
      <div className="biglietto-testa">
        <span className="biglietto-fasce" aria-hidden="true" />
        <span className="small text-uppercase fw-semibold">{t.nome}</span>
        <strong className="biglietto-valido">VALIDO</strong>
        <span className="tabular fs-4" aria-label="Ora attuale">
          {isoLocale(adesso).slice(11, 19)}
        </span>
      </div>
      <div className="p-3 text-center">
        <p className="mb-1">
          fino alle <strong className="tabular">{hhmm(isoLocale(new Date(a.scade)))}</strong> · resta{" "}
          <strong className="tabular">{conto(restano)}</strong>
        </p>
        <p className="biglietto-codice tabular mb-2" aria-label={`Codice ${a.codice.split("").join(" ")}`}>
          {a.codice.slice(0, 3)} {a.codice.slice(3)}
        </p>
        <img className="biglietto-qr d-block mx-auto" src={a.qr_img} alt="QR del biglietto da far leggere al controllore" />
        <p className="small mt-2 mb-0">
          Mostralo all'autista. Il colore cambia ogni giorno e l'ora scorre: uno screenshot non vale.
          {t.corse_rimaste !== null && ` Corse rimaste: ${t.corse_rimaste}.`}
        </p>
      </div>
    </article>
  );
}
