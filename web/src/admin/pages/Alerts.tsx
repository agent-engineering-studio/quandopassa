// Avvisi ai cittadini: deviazioni temporanee, fermate sospese, giorni di servizio sospeso, informazioni.
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Marker, Polyline, Tooltip, useMapEvents } from "react-leaflet";
import type { AlertKind } from "../../api";
import { admin, formatDateTime, fromLocalInput, toLocalInput, type AdminAlert } from "../api";
import { BaseMap, ConfirmButton, Field, PageTitle, Select, errorMessage, stopIcon, useAdmin, useSave } from "../ui";

const KINDS: { value: AlertKind; label: string; help: string }[] = [
  { value: "stop_closed", label: "Fermata sospesa", help: "Lavori, eventi, maltempo: nessuna salita o discesa alle fermate scelte. Gli itinerari le evitano." },
  { value: "detour", label: "Deviazione temporanea", help: "Le linee scelte cambiano strada: indica le fermate saltate e, se vuoi, disegna il percorso provvisorio." },
  { value: "service_suspended", label: "Servizio sospeso", help: "Sciopero o festività: nei giorni indicati i bus delle linee scelte (o di tutte) non circolano." },
  { value: "info", label: "Informazione", help: "Un messaggio per i cittadini, senza effetti sugli orari." },
];

const pad = (n: number) => String(n).padStart(2, "0");
const dayToIso = (day: string, addDays = 0) => {
  const d = new Date(`${day}T00:00:00`);
  d.setDate(d.getDate() + addDays);
  return d.toISOString();
};
const isoToDay = (iso: string | null, minusOneDay = false) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (minusOneDay) d.setDate(d.getDate() - 1);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};

function emptyAlert(): AdminAlert {
  return { kind: "stop_closed", title: "", description: "", starts_at: new Date().toISOString(), ends_at: null, route_ids: [], stop_ids: [], shape: null };
}

function DrawOnClick({ active, onPoint }: { active: boolean; onPoint: (p: [number, number]) => void }) {
  const map = useMapEvents({ click: (e) => active && onPoint([Math.round(e.latlng.lat * 1e6) / 1e6, Math.round(e.latlng.lng * 1e6) / 1e6]) });
  useEffect(() => {
    map.getContainer().style.cursor = active ? "crosshair" : "";
  }, [active, map]);
  return null;
}

export default function Alerts() {
  const { data, notify } = useAdmin();
  const { save, busy } = useSave();
  const [alerts, setAlerts] = useState<AdminAlert[] | null>(null);
  const [includePast, setIncludePast] = useState(false);
  const [selected, setSelected] = useState<number | "new" | null>(null);
  const [form, setForm] = useState<AdminAlert>(emptyAlert());
  const [untilFurtherNotice, setUntilFurtherNotice] = useState(true);
  const [drawing, setDrawing] = useState(false);

  const load = useCallback(() => {
    admin.alerts(includePast).then(setAlerts).catch((e) => notify(errorMessage(e)));
  }, [includePast, notify]);
  useEffect(load, [load]);

  const routes = useMemo(() => {
    const out = new Map<string, { name: string; color: string }>();
    for (const v of data?.variants ?? []) if (!out.has(v.route_id)) out.set(v.route_id, { name: v.long_name || v.short_name, color: v.color });
    return out;
  }, [data]);
  const stops = data?.stops ?? [];
  const stopName = (id: string) => stops.find((s) => s.stop_id === id)?.stop_name ?? id;

  function edit(a: AdminAlert | null) {
    const next = a ? { ...a, route_ids: [...a.route_ids], stop_ids: [...a.stop_ids] } : emptyAlert();
    setForm(next);
    setUntilFurtherNotice(!next.ends_at);
    setDrawing(false);
    setSelected(a?.id ?? "new");
  }

  const toggle = (list: string[], id: string) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
  const kind = KINDS.find((k) => k.value === form.kind)!;
  const isSuspension = form.kind === "service_suspended";

  async function submit(e: FormEvent) {
    e.preventDefault();
    const body: AdminAlert = {
      ...form,
      ends_at: isSuspension ? form.ends_at : untilFurtherNotice ? null : form.ends_at,
      shape: form.kind === "detour" && form.shape && form.shape.length > 1 ? form.shape : null,
    };
    const result = await save(() => admin.saveAlert(selected === "new" ? null : (selected as number), body), `Avviso «${form.title}» pubblicato.`);
    if (result) {
      setSelected(null);
      load();
    }
  }

  async function remove(id: number) {
    if (await save(() => admin.deleteAlert(id), "Avviso eliminato.")) {
      setSelected(null);
      load();
    }
  }

  const state = (a: AdminAlert) => {
    const now = Date.now();
    if (a.ends_at && new Date(a.ends_at).getTime() <= now) return { label: "concluso", cls: "bg-secondary" };
    if (new Date(a.starts_at).getTime() > now) return { label: "programmato", cls: "bg-info text-dark" };
    return { label: "in corso", cls: "bg-success" };
  };

  return (
    <>
      <PageTitle title="Avvisi ai cittadini">
        <button type="button" className="btn btn-primary btn-sm" onClick={() => edit(null)}>
          Nuovo avviso
        </button>
      </PageTitle>
      <p className="small text-muted">
        Gli avvisi compaiono nell'app dal momento della pubblicazione (quelli programmati una settimana prima
        dell'inizio) e spariscono da soli alla fine.
      </p>

      {selected === null ? (
        <>
          <div className="form-check mb-2">
            <input id="mostra-conclusi" type="checkbox" checked={includePast} onChange={(e) => setIncludePast(e.target.checked)} />
            <label htmlFor="mostra-conclusi">Mostra anche gli avvisi conclusi</label>
          </div>
          {!alerts ? (
            <p>Caricamento…</p>
          ) : alerts.length === 0 ? (
            <p>Nessun avviso in corso o programmato.</p>
          ) : (
            <div className="list-group">
              {alerts.map((a) => (
                <button type="button" key={a.id} className="list-group-item list-group-item-action" onClick={() => edit(a)}>
                  <span className={`badge ${state(a).cls} me-2`}>{state(a).label}</span>
                  <span className="fw-semibold">{a.title}</span>
                  <span className="d-block small text-muted">
                    {KINDS.find((k) => k.value === a.kind)?.label} · dal {formatDateTime(a.starts_at)}
                    {a.ends_at ? ` al ${formatDateTime(a.ends_at)}` : " fino a nuovo avviso"}
                    {a.route_ids.length ? ` · linee ${a.route_ids.join(", ")}` : ""}
                    {a.stop_ids.length ? ` · ${a.stop_ids.length} fermate` : ""}
                  </span>
                </button>
              ))}
            </div>
          )}
        </>
      ) : (
        <form onSubmit={submit}>
          <div className="row g-4">
            <div className="col-12 col-xl-5">
              <Select label="Tipo di avviso" value={form.kind} onChange={(v) => setForm({ ...form, kind: v as AlertKind })} options={KINDS} help={kind.help} />
              <Field label="Titolo" value={form.title} onChange={(v) => setForm((f) => ({ ...f, title: v }))} required help="Breve: compare in evidenza nell'app" />
              <Field label="Descrizione" value={form.description} onChange={(v) => setForm((f) => ({ ...f, description: v }))} textarea rows={3} help="Cosa cambia e cosa fare, es. «Usare la fermata di via Roma»" />

              {isSuspension ? (
                <div className="row">
                  <Field className="col-6" label="Dal giorno" type="date" required value={isoToDay(form.starts_at)} onChange={(v) => v && setForm({ ...form, starts_at: dayToIso(v) })} />
                  <Field className="col-6" label="Al giorno (compreso)" type="date" required value={isoToDay(form.ends_at, true)} onChange={(v) => v && setForm({ ...form, ends_at: dayToIso(v, 1) })} />
                </div>
              ) : (
                <>
                  <Field label="Dal" type="datetime-local" required value={toLocalInput(form.starts_at)} onChange={(v) => v && setForm({ ...form, starts_at: fromLocalInput(v) })} />
                  <div className="form-check mb-2">
                    <input id="nuovo-avviso" type="checkbox" checked={untilFurtherNotice} onChange={(e) => setUntilFurtherNotice(e.target.checked)} />
                    <label htmlFor="nuovo-avviso">Fino a nuovo avviso</label>
                  </div>
                  {!untilFurtherNotice && (
                    <Field label="Al" type="datetime-local" required value={toLocalInput(form.ends_at)} onChange={(v) => v && setForm({ ...form, ends_at: fromLocalInput(v) })} />
                  )}
                </>
              )}

              <fieldset className="mb-3">
                <legend className="small fw-semibold mb-1">
                  Linee interessate {form.kind === "detour" ? "*" : "(nessuna = tutte)"}
                </legend>
                <div className="d-flex flex-wrap gap-3">
                  {[...routes.entries()].map(([id, r]) => (
                    <div className="form-check" key={id}>
                      <input id={`linea-${id}`} type="checkbox" checked={form.route_ids.includes(id)} onChange={() => setForm({ ...form, route_ids: toggle(form.route_ids, id) })} />
                      <label htmlFor={`linea-${id}`}>
                        <span className="badge-colore me-1" style={{ background: `#${r.color}`, color: "#fff" }}>{id}</span>
                        {r.name}
                      </label>
                    </div>
                  ))}
                </div>
              </fieldset>

              {(form.kind === "stop_closed" || form.kind === "detour") && (
                <fieldset className="mb-3">
                  <legend className="small fw-semibold mb-1">
                    {form.kind === "stop_closed" ? "Fermate sospese *" : "Fermate non servite durante la deviazione"}
                  </legend>
                  <p className="small text-muted mb-1">Fai clic sulle fermate nella mappa o scegli dall'elenco.</p>
                  <select
                    className="form-select mb-2"
                    aria-label="Aggiungi una fermata"
                    value=""
                    onChange={(e) => e.target.value && setForm({ ...form, stop_ids: toggle(form.stop_ids, e.target.value) })}
                  >
                    <option value="">— aggiungi una fermata —</option>
                    {stops.filter((s) => !form.stop_ids.includes(s.stop_id)).map((s) => (
                      <option key={s.stop_id} value={s.stop_id}>{`${s.stop_code || s.stop_id} · ${s.stop_name}`}</option>
                    ))}
                  </select>
                  <ul className="list-unstyled small mb-0">
                    {form.stop_ids.map((id) => (
                      <li key={id}>
                        {stopName(id)}{" "}
                        <button type="button" className="btn btn-link btn-sm p-0 text-danger" onClick={() => setForm({ ...form, stop_ids: toggle(form.stop_ids, id) })}>
                          togli
                        </button>
                      </li>
                    ))}
                  </ul>
                </fieldset>
              )}
            </div>

            <div className="col-12 col-xl-7">
              <BaseMap label="Mappa dell'avviso" height={420}>
                <DrawOnClick active={drawing} onPoint={(p) => setForm((f) => ({ ...f, shape: [...(f.shape ?? []), p] }))} />
                {stops.filter((s) => s.lat !== null).map((s) => (
                  <Marker
                    key={s.stop_id}
                    position={[s.lat!, s.lon!]}
                    icon={stopIcon(s.stop_code || s.stop_id, form.stop_ids.includes(s.stop_id) ? "closed" : "normal")}
                    eventHandlers={{
                      click: () => !drawing && (form.kind === "stop_closed" || form.kind === "detour") && setForm({ ...form, stop_ids: toggle(form.stop_ids, s.stop_id) }),
                    }}
                    title={s.stop_name}
                  >
                    <Tooltip>{s.stop_name}{form.stop_ids.includes(s.stop_id) ? " (sospesa)" : ""}</Tooltip>
                  </Marker>
                ))}
                {form.kind === "detour" && form.shape && form.shape.length > 0 && (
                  <Polyline positions={form.shape} pathOptions={{ color: "#d9364f", weight: 6, dashArray: "10 8" }} />
                )}
              </BaseMap>
              {form.kind === "detour" && (
                <div className="d-flex flex-wrap gap-2 mt-2 align-items-center small">
                  <button type="button" className={`btn btn-sm ${drawing ? "btn-primary" : "btn-outline-primary"}`} onClick={() => setDrawing(!drawing)} aria-pressed={drawing}>
                    {drawing ? "Fine disegno" : "Disegna il percorso provvisorio"}
                  </button>
                  <button type="button" className="btn btn-sm btn-outline-secondary" disabled={!form.shape?.length} onClick={() => setForm({ ...form, shape: (form.shape ?? []).slice(0, -1) })}>
                    Togli l'ultimo punto
                  </button>
                  <button type="button" className="btn btn-sm btn-outline-secondary" disabled={!form.shape?.length} onClick={() => setForm({ ...form, shape: null })}>
                    Cancella il percorso
                  </button>
                  <span>{form.shape?.length ?? 0} punti{drawing ? " · fai clic sulla mappa lungo le strade della deviazione" : ""}</span>
                </div>
              )}
            </div>
          </div>

          <div className="d-flex gap-2 flex-wrap mt-3 align-items-center">
            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? "Pubblicazione…" : selected === "new" ? "Pubblica l'avviso" : "Salva le modifiche"}
            </button>
            <button type="button" className="btn btn-outline-secondary" onClick={() => setSelected(null)}>
              Torna all'elenco
            </button>
            {selected !== "new" && (
              <ConfirmButton label="Elimina l'avviso" confirmLabel="Conferma eliminazione" disabled={busy} onConfirm={() => remove(selected as number)} />
            )}
          </div>
          {form.kind === "service_suspended" && !form.ends_at && (
            <p className="small text-danger mt-2">Indica l'ultimo giorno di sospensione.</p>
          )}
        </form>
      )}
    </>
  );
}
