// Linee e orari: dati della linea, percorso con i minuti dalla partenza, partenze e tracciato su strada.
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Marker, Polyline, Tooltip } from "react-leaflet";
import { admin, parseTimes, seriesOfTimes, type Variant } from "../api";
import { BaseMap, ConfirmButton, Field, PageTitle, Select, stopIcon, useAdmin, useSave } from "../ui";

const EMPTY: Variant = {
  variant_id: "", route_id: "", short_name: "", long_name: "", color: "0066CC", text_color: "FFFFFF",
  service_id: "", headsign: "", direction_id: 0, sort_order: 0, stops: [], departures: [],
};

export default function Lines() {
  const { data, status } = useAdmin();
  const { save, busy } = useSave();
  const [selected, setSelected] = useState<string | null>(null); // id originale, "" = nuova
  const [form, setForm] = useState<Variant>(EMPTY);
  const [timesText, setTimesText] = useState("");
  const [series, setSeries] = useState({ start: "08:00", end: "12:00", every: 30 });
  const [addStop, setAddStop] = useState("");

  const variants = useMemo(() => data?.variants ?? [], [data]);
  const stops = useMemo(() => data?.stops ?? [], [data]);
  const stopById = useMemo(() => Object.fromEntries(stops.map((s) => [s.stop_id, s])), [stops]);

  // dopo un salvataggio (es. tracciato ricalcolato) il tracciato si aggiorna dai dati appena ricaricati
  useEffect(() => {
    const v = variants.find((x) => x.variant_id === selected);
    if (v) setForm((f) => ({ ...f, shape: v.shape }));
  }, [selected, variants]);

  function open(variantId: string) {
    const v = variants.find((x) => x.variant_id === variantId);
    if (!v) return;
    setForm({ ...v, stops: v.stops.map((s) => ({ ...s })), departures: [...v.departures] });
    setTimesText(v.departures.join(" "));
    setSelected(variantId);
  }

  if (!data) return <p>Caricamento…</p>;
  const set = <K extends keyof Variant>(k: K) => (v: Variant[K]) => setForm((f) => ({ ...f, [k]: v }));
  const parsed = parseTimes(timesText);

  function startNew() {
    setSelected("");
    setForm({ ...EMPTY, service_id: data!.calendars[0]?.service_id ?? "", sort_order: variants.length });
    setTimesText("");
  }

  function moveStop(i: number, delta: number) {
    const list = [...form.stops];
    const [item] = list.splice(i, 1);
    list.splice(i + delta, 0, item);
    setForm({ ...form, stops: list });
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const variant = { ...form, departures: parsed.times, variant_id: form.variant_id || form.route_id };
    const result = await save(() => admin.saveVariant(selected || null, variant), `Linea ${variant.short_name} salvata.`);
    if (result) {
      setForm(variant);
      setSelected(variant.variant_id);
    }
  }

  const path = form.stops.map((s) => stopById[s.stop_id]).filter((s) => s && s.lat !== null);
  const line: [number, number][] = form.shape?.length ? form.shape : path.map((s) => [s!.lat!, s!.lon!]);

  return (
    <>
      <PageTitle title="Linee e orari">
        <button type="button" className="btn btn-primary btn-sm" onClick={startNew}>
          Nuova linea
        </button>
      </PageTitle>

      {selected === null ? (
        <div className="list-group">
          {variants.map((v) => (
            <button type="button" key={v.variant_id} className="list-group-item list-group-item-action" onClick={() => open(v.variant_id)}>
              <span className="badge-colore me-2" style={{ background: `#${v.color}`, color: `#${v.text_color}` }}>
                {v.short_name}
              </span>
              <span className="fw-semibold">{v.long_name || v.headsign}</span>
              {v.variant_id !== v.route_id && <span className="small text-muted"> · variante {v.variant_id}</span>}
              <span className="d-block small text-muted">
                {v.stops.length} fermate · {v.departures.length} partenze · calendario {v.service_id}
                {v.shape?.length ? " · tracciato su strada" : " · senza tracciato"}
              </span>
            </button>
          ))}
        </div>
      ) : (
        <form onSubmit={submit}>
          <div className="row g-4">
            <div className="col-12 col-xl-5">
              <h2 className="h5">{selected ? `Linea ${form.short_name}` : "Nuova linea"}</h2>
              <div className="row">
                <Field className="col-6" label="Linea (route_id)" value={form.route_id} onChange={set("route_id")} required help="Es. A" />
                <Field className="col-6" label="Variante" value={form.variant_id} onChange={set("variant_id")} help="Vuoto = uguale alla linea; per percorsi alternativi es. A-mercato" />
                <Field className="col-6" label="Nome breve" value={form.short_name} onChange={set("short_name")} required />
                <Field className="col-6" label="Direzione / destinazione" value={form.headsign} onChange={set("headsign")} />
              </div>
              <Field label="Nome esteso" value={form.long_name} onChange={set("long_name")} />
              <div className="row">
                <div className="col-6 mb-3">
                  <label className="small fw-semibold mb-1 d-block" htmlFor="colore-linea">Colore</label>
                  <input id="colore-linea" type="color" className="form-control form-control-color" value={`#${form.color}`} onChange={(e) => set("color")(e.target.value.slice(1).toUpperCase())} />
                </div>
                <div className="col-6 mb-3">
                  <label className="small fw-semibold mb-1 d-block" htmlFor="colore-testo">Colore del testo</label>
                  <input id="colore-testo" type="color" className="form-control form-control-color" value={`#${form.text_color}`} onChange={(e) => set("text_color")(e.target.value.slice(1).toUpperCase())} />
                </div>
              </div>
              <Select
                label="Calendario"
                value={form.service_id}
                onChange={set("service_id")}
                required
                options={data.calendars.map((c) => ({ value: c.service_id, label: `${c.service_id}${c.note ? ` – ${c.note}` : ""}` }))}
              />

              <h3 className="h6 mt-4">Partenze dal capolinea</h3>
              <Field
                label="Orari di partenza"
                value={timesText}
                onChange={setTimesText}
                textarea
                rows={3}
                help={`${parsed.times.length} partenze. Scrivi gli orari separati da spazi o virgole, es. 8:30 9:00 9:30.`}
              />
              {parsed.invalid.length > 0 && (
                <p className="small text-danger">Orari non validi: {parsed.invalid.join(", ")}</p>
              )}
              <fieldset className="border rounded p-2 mb-3">
                <legend className="small fw-semibold float-none w-auto px-1 mb-0">Aggiungi una serie</legend>
                <div className="d-flex flex-wrap gap-2 align-items-end">
                  <Field className="mb-0" label="Dalle" type="time" value={series.start} onChange={(v) => setSeries({ ...series, start: v })} />
                  <Field className="mb-0" label="Alle" type="time" value={series.end} onChange={(v) => setSeries({ ...series, end: v })} />
                  <Field className="mb-0" label="Ogni (min)" type="number" min={1} value={series.every} onChange={(v) => setSeries({ ...series, every: Number(v) })} />
                  <button
                    type="button"
                    className="btn btn-outline-primary btn-sm"
                    onClick={() => setTimesText(parseTimes(`${timesText} ${seriesOfTimes(series.start, series.end, series.every).join(" ")}`).times.join(" "))}
                  >
                    Aggiungi
                  </button>
                </div>
              </fieldset>
            </div>

            <div className="col-12 col-xl-7">
              <h3 className="h6">Percorso</h3>
              <p className="small text-muted mb-2">Minuti dalla partenza al capolinea a ogni fermata, nell'ordine in cui il bus le serve.</p>
              <div className="table-responsive">
                <table className="table table-sm tabella-percorso">
                  <thead>
                    <tr>
                      <th scope="col">#</th>
                      <th scope="col">Fermata</th>
                      <th scope="col">Minuti</th>
                      <th scope="col"><span className="visually-hidden">Azioni</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {form.stops.map((s, i) => (
                      <tr key={`${s.stop_id}-${i}`}>
                        <td>{i + 1}</td>
                        <td>{stopById[s.stop_id]?.stop_name ?? <span className="text-danger">{s.stop_id} (non esiste)</span>}</td>
                        <td>
                          <input
                            type="number"
                            min={0}
                            className="form-control form-control-sm"
                            aria-label={`Minuti alla fermata ${i + 1}`}
                            value={s.minutes}
                            onChange={(e) => {
                              const list = [...form.stops];
                              list[i] = { ...s, minutes: Number(e.target.value) };
                              setForm({ ...form, stops: list });
                            }}
                          />
                        </td>
                        <td className="text-nowrap">
                          <button type="button" className="btn btn-sm btn-link px-1" disabled={i === 0} onClick={() => moveStop(i, -1)} aria-label={`Sposta su la fermata ${i + 1}`}>↑</button>
                          <button type="button" className="btn btn-sm btn-link px-1" disabled={i === form.stops.length - 1} onClick={() => moveStop(i, 1)} aria-label={`Sposta giù la fermata ${i + 1}`}>↓</button>
                          <button type="button" className="btn btn-sm btn-link px-1 text-danger" onClick={() => setForm({ ...form, stops: form.stops.filter((_, k) => k !== i) })} aria-label={`Togli la fermata ${i + 1}`}>✕</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="d-flex gap-2 align-items-end mb-3">
                <div className="flex-grow-1">
                  <Select
                    label="Aggiungi una fermata in fondo"
                    value={addStop}
                    onChange={setAddStop}
                    options={[{ value: "", label: "— scegli —" }, ...stops.map((s) => ({ value: s.stop_id, label: `${s.stop_code || s.stop_id} · ${s.stop_name}` }))]}
                  />
                </div>
                <button
                  type="button"
                  className="btn btn-outline-primary mb-3"
                  disabled={!addStop}
                  onClick={() => {
                    const last = form.stops[form.stops.length - 1]?.minutes ?? -1;
                    setForm({ ...form, stops: [...form.stops, { stop_id: addStop, minutes: last + 1 }] });
                    setAddStop("");
                  }}
                >
                  Aggiungi
                </button>
              </div>

              <BaseMap label={`Percorso della linea ${form.short_name}`} fit={line} height={340}>
                {line.length > 1 && <Polyline positions={line} pathOptions={{ color: `#${form.color}`, weight: 5 }} />}
                {path.map((s, i) => (
                  <Marker key={`${s!.stop_id}-${i}`} position={[s!.lat!, s!.lon!]} icon={stopIcon(String(i + 1))}>
                    <Tooltip>{s!.stop_name}</Tooltip>
                  </Marker>
                ))}
              </BaseMap>
              {selected && (
                <div className="d-flex flex-wrap gap-2 align-items-center mt-2 small">
                  <span>{form.shape?.length ? `Tracciato su strada: ${form.shape.length} punti.` : "Senza tracciato: fermate unite in linea retta."}</span>
                  {status?.osrm && (
                    <button type="button" className="btn btn-outline-primary btn-sm" disabled={busy} onClick={() => save(() => admin.computeShape(selected), "Tracciato calcolato sulle strade.")}>
                      Calcola sulle strade
                    </button>
                  )}
                  {form.shape?.length ? (
                    <ConfirmButton label="Togli il tracciato" confirmLabel="Conferma" disabled={busy} onConfirm={() => save(() => admin.setShape(selected, null), "Tracciato rimosso.")} />
                  ) : null}
                </div>
              )}
              {selected && <p className="small text-muted mt-1">Il tracciato si calcola sul percorso salvato: dopo aver cambiato le fermate, salva e poi ricalcolalo.</p>}
            </div>
          </div>

          <div className="d-flex gap-2 flex-wrap mt-3 align-items-center">
            <button type="submit" className="btn btn-primary" disabled={busy || parsed.invalid.length > 0 || form.stops.length < 2}>
              {busy ? "Salvataggio…" : "Salva la linea"}
            </button>
            <button type="button" className="btn btn-outline-secondary" onClick={() => setSelected(null)}>
              Torna all'elenco
            </button>
            {selected && (
              <ConfirmButton label="Elimina la linea" confirmLabel="Conferma eliminazione" disabled={busy} onConfirm={async () => {
                if (await save(() => admin.deleteVariant(selected), `Linea ${form.short_name} eliminata.`)) setSelected(null);
              }} />
            )}
          </div>
        </form>
      )}
    </>
  );
}
