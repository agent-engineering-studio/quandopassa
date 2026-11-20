// Fermate: elenco, mappa con i punti trascinabili e scheda di modifica.
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Marker, Tooltip, useMapEvents } from "react-leaflet";
import { admin, type Stop } from "../api";
import { BaseMap, ConfirmButton, Field, PageTitle, stopIcon, useAdmin, useSave } from "../ui";

const EMPTY: Stop = {
  stop_id: "", stop_code: "", stop_name: "", category: "", note: "", search_hint: "", lat: null, lon: null, source: "manuale",
};

function PlaceOnClick({ active, onPlace }: { active: boolean; onPlace: (lat: number, lon: number) => void }) {
  const map = useMapEvents({ click: (e) => active && onPlace(e.latlng.lat, e.latlng.lng) });
  useEffect(() => {
    map.getContainer().style.cursor = active ? "crosshair" : "";
  }, [active, map]);
  return null;
}

const round6 = (n: number) => Math.round(n * 1e6) / 1e6;

export default function Stops() {
  const { data } = useAdmin();
  const { save, busy } = useSave();
  const [selected, setSelected] = useState<string | null>(null); // id originale, "" = nuova
  const [form, setForm] = useState<Stop>(EMPTY);
  const [filter, setFilter] = useState("");
  const [placing, setPlacing] = useState(false);

  const stops = useMemo(() => data?.stops ?? [], [data]);
  const usage = useMemo(() => {
    const out: Record<string, string[]> = {};
    for (const v of data?.variants ?? []) {
      for (const s of v.stops) {
        const names = (out[s.stop_id] ??= []);
        if (!names.includes(v.short_name)) names.push(v.short_name);
      }
    }
    return out;
  }, [data]);

  function open(stopId: string) {
    const s = stops.find((x) => x.stop_id === stopId);
    if (!s) return;
    setForm({ ...s });
    setSelected(stopId);
    setPlacing(false);
  }

  const visible = stops.filter((s) =>
    `${s.stop_code} ${s.stop_id} ${s.stop_name}`.toLowerCase().includes(filter.trim().toLowerCase()),
  );
  const editing = selected !== null;
  const set = (k: keyof Stop) => (v: string) => setForm((f) => ({ ...f, [k]: v }));
  const setCoord = (k: "lat" | "lon") => (v: string) =>
    setForm((f) => ({ ...f, [k]: v === "" ? null : Number(v), source: "manuale" }));

  function startNew() {
    const next = String(stops.length + 1).padStart(2, "0");
    setSelected("");
    setForm({ ...EMPTY, stop_code: next });
    setPlacing(true);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const result = await save(() => admin.saveStop(selected || null, form), `Fermata «${form.stop_name}» salvata.`);
    if (result) {
      setSelected(form.stop_id);
      setPlacing(false);
    }
  }

  async function remove() {
    const result = await save(() => admin.deleteStop(selected!), `Fermata «${form.stop_name}» eliminata.`);
    if (result) setSelected(null);
  }

  const points = stops.filter((s) => s.lat !== null).map((s) => [s.lat!, s.lon!] as [number, number]);

  return (
    <>
      <PageTitle title="Fermate">
        <button type="button" className="btn btn-primary btn-sm" onClick={startNew}>
          Nuova fermata
        </button>
      </PageTitle>
      <p className="small text-muted">
        Trascina un punto sulla mappa per spostare una fermata, poi salva. Le fermate senza coordinate hanno il
        bordo tratteggiato: l'app le mostra in una posizione provvisoria.
      </p>
      <div className="row g-4">
        <div className="col-12 col-xl-7">
          <BaseMap label="Mappa delle fermate" fit={selected === null ? points : []}>
            <PlaceOnClick
              active={placing}
              onPlace={(lat, lon) => {
                setForm((f) => ({ ...f, lat: round6(lat), lon: round6(lon), source: "manuale" }));
                setPlacing(false);
              }}
            />
            {stops
              .filter((s) => s.lat !== null && s.stop_id !== selected)
              .map((s) => (
                <Marker
                  key={s.stop_id}
                  position={[s.lat!, s.lon!]}
                  icon={stopIcon(s.stop_code || s.stop_id, "normal")}
                  eventHandlers={{ click: () => open(s.stop_id) }}
                  keyboard
                  title={s.stop_name}
                >
                  <Tooltip>{s.stop_name}</Tooltip>
                </Marker>
              ))}
            {editing && form.lat !== null && form.lon !== null && (
              <Marker
                position={[form.lat, form.lon]}
                icon={stopIcon(form.stop_code || "?", "selected")}
                draggable
                eventHandlers={{
                  dragend: (e) => {
                    const p = e.target.getLatLng();
                    setForm((f) => ({ ...f, lat: round6(p.lat), lon: round6(p.lng), source: "manuale" }));
                  },
                }}
                title={`${form.stop_name} (trascinabile)`}
              >
                <Tooltip permanent direction="top" offset={[0, -16]}>
                  {form.stop_name || "Nuova fermata"}
                </Tooltip>
              </Marker>
            )}
          </BaseMap>
          {placing && <p className="small mt-2 fw-semibold">Fai clic sulla mappa nel punto della fermata.</p>}
        </div>

        <div className="col-12 col-xl-5">
          {editing ? (
            <form onSubmit={submit} aria-label={selected ? `Modifica della fermata ${form.stop_name}` : "Nuova fermata"}>
              <h2 className="h5">{selected ? "Modifica fermata" : "Nuova fermata"}</h2>
              <div className="row">
                <Field className="col-6" label="Identificativo" value={form.stop_id} onChange={set("stop_id")} required help="Usato nel GTFS, es. R21" />
                <Field className="col-6" label="Codice" value={form.stop_code} onChange={set("stop_code")} help="Numero sulla palina" />
              </div>
              <Field label="Nome" value={form.stop_name} onChange={set("stop_name")} required />
              <div className="row">
                <Field className="col-6" label="Latitudine" type="number" step="0.000001" value={form.lat} onChange={setCoord("lat")} />
                <Field className="col-6" label="Longitudine" type="number" step="0.000001" value={form.lon} onChange={setCoord("lon")} />
              </div>
              <div className="mb-3 d-flex gap-2 flex-wrap">
                <button type="button" className="btn btn-outline-primary btn-sm" onClick={() => setPlacing(true)}>
                  Scegli il punto sulla mappa
                </button>
                {form.lat !== null && (
                  <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setForm({ ...form, lat: null, lon: null, source: "" })}>
                    Togli le coordinate
                  </button>
                )}
              </div>
              <Field label="Tipologia" value={form.category} onChange={set("category")} help="Es. Pensilina, Palina" />
              <Field label="Note" value={form.note} onChange={set("note")} textarea rows={2} />
              <Field label="Fonte della posizione" value={form.source} onChange={set("source")} help="«manuale» se verificata sul posto" />
              {selected && usage[selected] && (
                <p className="small">Servita dalle linee: {usage[selected].join(", ")}</p>
              )}
              <div className="d-flex gap-2 flex-wrap align-items-center">
                <button type="submit" className="btn btn-primary" disabled={busy}>
                  {busy ? "Salvataggio…" : "Salva"}
                </button>
                <button type="button" className="btn btn-outline-secondary" onClick={() => { setSelected(null); setPlacing(false); }}>
                  Chiudi
                </button>
                {selected && (
                  <ConfirmButton label="Elimina" confirmLabel="Conferma eliminazione" onConfirm={remove} disabled={busy || !!usage[selected]} />
                )}
              </div>
              {selected && usage[selected] && (
                <p className="small text-muted mt-2">Per eliminarla, toglila prima dai percorsi delle linee.</p>
              )}
            </form>
          ) : (
            <>
              <label htmlFor="filtro-fermate" className="small fw-semibold mb-1 d-block">
                Cerca una fermata
              </label>
              <input id="filtro-fermate" className="form-control mb-2" value={filter} onChange={(e) => setFilter(e.target.value)} />
              <div className="list-group lista-admin">
                {visible.map((s) => (
                  <button
                    type="button"
                    key={s.stop_id}
                    className="list-group-item list-group-item-action d-flex justify-content-between align-items-center gap-2"
                    onClick={() => open(s.stop_id)}
                  >
                    <span>
                      <span className="fw-semibold">{s.stop_code || s.stop_id}</span> · {s.stop_name}
                      {s.lat === null && <span className="badge bg-warning text-dark ms-2">senza posizione</span>}
                    </span>
                    <span className="small text-muted text-nowrap">{(usage[s.stop_id] ?? []).join(" ") || "nessuna linea"}</span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
