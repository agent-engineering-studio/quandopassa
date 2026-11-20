// Calendari di servizio: giorni della settimana, periodo ed eccezioni (giorni aggiunti o soppressi).
import { useState, type FormEvent } from "react";
import { admin, formatDate, type Calendar } from "../api";
import { ConfirmButton, Field, PageTitle, useAdmin, useSave } from "../ui";

const DAYS = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"];
const EMPTY: Calendar = { service_id: "", days: "1111110", start_date: null, end_date: null, note: "", exceptions: [] };

export default function Calendars() {
  const { data } = useAdmin();
  const { save, busy } = useSave();
  const [selected, setSelected] = useState<string | null>(null);
  const [form, setForm] = useState<Calendar>(EMPTY);
  const [newDay, setNewDay] = useState("");
  const [newType, setNewType] = useState<1 | 2>(2);

  if (!data) return <p>Caricamento…</p>;
  function open(serviceId: string) {
    const c = data!.calendars.find((x) => x.service_id === serviceId);
    if (!c) return;
    setForm({ ...c, exceptions: c.exceptions.map((e) => ({ ...e })) });
    setSelected(serviceId);
  }
  const usedBy = (id: string) => data.variants.filter((v) => v.service_id === id).map((v) => v.short_name);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const result = await save(() => admin.saveCalendar(selected || null, form), `Calendario ${form.service_id} salvato.`);
    if (result) setSelected(form.service_id);
  }

  return (
    <>
      <PageTitle title="Calendari di servizio">
        <button type="button" className="btn btn-primary btn-sm" onClick={() => { setSelected(""); setForm(EMPTY); }}>
          Nuovo calendario
        </button>
      </PageTitle>
      <p className="small text-muted">
        Ogni linea segue un calendario. Per un giorno di sciopero o una festività conviene un avviso «Servizio sospeso»
        (pagina Avvisi): i cittadini lo vedono e il GTFS si aggiorna da solo. Le eccezioni qui sotto servono per i
        cambi stabili dell'orario.
      </p>
      <div className="row g-4">
        <div className="col-12 col-lg-4">
          <div className="list-group">
            {data.calendars.map((c) => (
              <button type="button" key={c.service_id} className={`list-group-item list-group-item-action ${c.service_id === selected ? "active" : ""}`} onClick={() => open(c.service_id)}>
                <span className="fw-semibold">{c.service_id}</span>
                <span className="d-block small">
                  {DAYS.filter((_, i) => c.days[i] === "1").map((d) => d.slice(0, 3)).join(" ") || "nessun giorno"}
                  {usedBy(c.service_id).length ? ` · linee ${usedBy(c.service_id).join(", ")}` : " · non usato"}
                </span>
              </button>
            ))}
          </div>
        </div>
        <div className="col-12 col-lg-8">
          {selected !== null && (
            <form onSubmit={submit}>
              <h2 className="h5">{selected ? `Calendario ${selected}` : "Nuovo calendario"}</h2>
              <Field label="Identificativo" value={form.service_id} onChange={(v) => setForm((f) => ({ ...f, service_id: v }))} required help="Es. FERIALE" />
              <Field label="Descrizione" value={form.note} onChange={(v) => setForm((f) => ({ ...f, note: v }))} />
              <fieldset className="mb-3">
                <legend className="small fw-semibold mb-1">Giorni di servizio</legend>
                <div className="giorni-settimana">
                  {DAYS.map((d, i) => (
                    <div className="form-check" key={d}>
                      <input
                        id={`giorno-${i}`}
                        type="checkbox"
                        checked={form.days[i] === "1"}
                        onChange={(e) => setForm({ ...form, days: form.days.slice(0, i) + (e.target.checked ? "1" : "0") + form.days.slice(i + 1) })}
                      />
                      <label htmlFor={`giorno-${i}`}>{d}</label>
                    </div>
                  ))}
                </div>
              </fieldset>
              <div className="row">
                <Field className="col-6" label="Dal (facoltativo)" type="date" value={form.start_date} onChange={(v) => setForm({ ...form, start_date: v || null })} help="Vuoto = inizio di validità del feed" />
                <Field className="col-6" label="Al (facoltativo)" type="date" value={form.end_date} onChange={(v) => setForm({ ...form, end_date: v || null })} help="Vuoto = fine di validità del feed" />
              </div>
              <h3 className="h6">Eccezioni</h3>
              {form.exceptions.length ? (
                <ul className="list-unstyled small">
                  {form.exceptions.map((e, i) => (
                    <li key={e.day} className="d-flex gap-2 align-items-center">
                      {formatDate(e.day)} · {e.type === 2 ? "servizio soppresso" : "servizio aggiunto"}
                      <button type="button" className="btn btn-link btn-sm text-danger p-0" onClick={() => setForm({ ...form, exceptions: form.exceptions.filter((_, k) => k !== i) })}>
                        togli
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="small text-muted">Nessuna eccezione.</p>
              )}
              <div className="d-flex flex-wrap gap-2 align-items-end mb-3">
                <Field className="mb-0" label="Giorno" type="date" value={newDay} onChange={setNewDay} />
                <div>
                  <label htmlFor="tipo-eccezione" className="small fw-semibold mb-1 d-block">Tipo</label>
                  <select id="tipo-eccezione" className="form-select" value={newType} onChange={(e) => setNewType(Number(e.target.value) as 1 | 2)}>
                    <option value={2}>soppresso</option>
                    <option value={1}>aggiunto</option>
                  </select>
                </div>
                <button
                  type="button"
                  className="btn btn-outline-primary"
                  disabled={!newDay}
                  onClick={() => {
                    const rest = form.exceptions.filter((e) => e.day !== newDay);
                    setForm({ ...form, exceptions: [...rest, { day: newDay, type: newType }].sort((a, b) => a.day.localeCompare(b.day)) });
                    setNewDay("");
                  }}
                >
                  Aggiungi
                </button>
              </div>
              <div className="d-flex gap-2 flex-wrap align-items-center">
                <button type="submit" className="btn btn-primary" disabled={busy}>
                  {busy ? "Salvataggio…" : "Salva"}
                </button>
                {selected && (
                  <ConfirmButton
                    label="Elimina"
                    confirmLabel="Conferma eliminazione"
                    disabled={busy || usedBy(selected).length > 0}
                    onConfirm={async () => {
                      if (await save(() => admin.deleteCalendar(selected), `Calendario ${selected} eliminato.`)) setSelected(null);
                    }}
                  />
                )}
              </div>
              {selected && usedBy(selected).length > 0 && (
                <p className="small text-muted mt-2">Usato dalle linee {usedBy(selected).join(", ")}: per eliminarlo, assegna loro un altro calendario.</p>
              )}
            </form>
          )}
        </div>
      </div>
    </>
  );
}
