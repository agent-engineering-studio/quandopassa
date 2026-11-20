// Feed GTFS: azienda di trasporto, periodo di validità ed export.
import { useEffect, useState, type FormEvent } from "react";
import { admin, type Agency, type FeedInfo } from "../api";
import { Field, PageTitle, useAdmin, useSave } from "../ui";

export default function Feed() {
  const { data } = useAdmin();
  const { save, busy } = useSave();
  const [agency, setAgency] = useState<Agency | null>(null);
  const [feedInfo, setFeedInfo] = useState<FeedInfo | null>(null);

  useEffect(() => {
    if (data) {
      setAgency({ ...data.agency });
      setFeedInfo({ ...data.feed_info });
    }
  }, [data]);

  if (!agency || !feedInfo) return <p>Caricamento…</p>;
  const setA = (k: keyof Agency) => (v: string) => setAgency((a) => (a ? { ...a, [k]: v } : a));
  const setF = (k: keyof FeedInfo) => (v: string) => setFeedInfo((f) => (f ? { ...f, [k]: v } : f));

  async function submit(e: FormEvent) {
    e.preventDefault();
    const { feed_version: _ignored, ...fi } = feedInfo!;
    void _ignored;
    await save(() => admin.saveFeed(agency!, fi), "Dati del feed salvati.");
  }

  return (
    <>
      <PageTitle title="Feed GTFS">
        <a className="btn btn-outline-primary btn-sm" href={admin.exportUrl(false)}>
          Scarica il GTFS (zip)
        </a>
        <a className="btn btn-outline-secondary btn-sm" href={admin.exportUrl(true)}>
          Zip con le sorgenti
        </a>
      </PageTitle>
      <p className="small text-muted">
        Il feed GTFS si rigenera a ogni salvataggio ed è sempre allineato al database: lo zip si può pubblicare sul
        portale open data o consegnare ad altri servizi (Google Maps, Moovit, ecc.). La versione viene assegnata
        automaticamente: ora è <span className="font-monospace">{feedInfo.feed_version || "—"}</span>.
      </p>
      <form onSubmit={submit}>
        <div className="row">
          <div className="col-12 col-lg-6">
            <h2 className="h5">Azienda di trasporto</h2>
            <Field label="Identificativo" value={agency.agency_id} onChange={setA("agency_id")} required />
            <Field label="Nome" value={agency.agency_name} onChange={setA("agency_name")} required />
            <Field label="Sito" type="url" value={agency.agency_url} onChange={setA("agency_url")} required />
            <Field label="Telefono" value={agency.agency_phone} onChange={setA("agency_phone")} />
            <Field label="Fuso orario" value={agency.agency_timezone} onChange={setA("agency_timezone")} required help="Es. Europe/Rome" />
            <Field label="Lingua" value={agency.agency_lang} onChange={setA("agency_lang")} help="Es. it" />
          </div>
          <div className="col-12 col-lg-6">
            <h2 className="h5">Pubblicazione e validità</h2>
            <Field label="Valido dal" type="date" value={feedInfo.feed_start_date} onChange={setF("feed_start_date")} required />
            <Field
              label="Valido fino al"
              type="date"
              value={feedInfo.feed_end_date}
              onChange={setF("feed_end_date")}
              required
              help="Dopo questa data l'app non mostra più bus: va prorogata con il nuovo orario."
            />
            <Field label="Editore del feed" value={feedInfo.feed_publisher_name} onChange={setF("feed_publisher_name")} required />
            <Field label="Sito dell'editore" type="url" value={feedInfo.feed_publisher_url} onChange={setF("feed_publisher_url")} required />
            <Field label="Lingua del feed" value={feedInfo.feed_lang} onChange={setF("feed_lang")} />
          </div>
        </div>
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? "Salvataggio…" : "Salva"}
        </button>
      </form>
    </>
  );
}
