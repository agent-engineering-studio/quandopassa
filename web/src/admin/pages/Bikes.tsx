// Bike sharing: sistemi (gestore, app, feed GBFS), import delle stazioni da GBFS, stazioni sulla mappa con le
// fermate del bus vicine. Le stazioni salvate a mano non vengono sovrascritte dagli import successivi.
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { CircleMarker, Marker, Tooltip, useMapEvents } from "react-leaflet";
import {
  admin,
  formatDateTime,
  type BikeImportPreview,
  type BikeLiveCheck,
  type BikesData,
  type BikeStation,
  type BikeSystem,
} from "../api";
import { BaseMap, bikeIcon, ConfirmButton, errorMessage, Field, PageTitle, useAdmin, useSave } from "../ui";

const EMPTY_SYSTEM: BikeSystem = {
  system_id: "", name: "", operator: "", app_url: "", gbfs_url: "", status_url: "", license_url: "", live: true,
};
const EMPTY_STATION: BikeStation = {
  station_id: "", name: "", short_name: "", address: "", lat: null, lon: null, capacity: null, active: true, note: "",
};
const round6 = (n: number) => Math.round(n * 1e6) / 1e6;

function Check({ label, checked, onChange, help }: { label: string; checked: boolean; onChange: (v: boolean) => void; help?: string }) {
  return (
    <div className="form-check mb-3">
      <input className="form-check-input" type="checkbox" id={`chk-${label}`} checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <label className="form-check-label" htmlFor={`chk-${label}`}>
        {label}
      </label>
      {help && <small className="form-text d-block text-muted">{help}</small>}
    </div>
  );
}

function PlaceOnClick({ active, onPlace }: { active: boolean; onPlace: (lat: number, lon: number) => void }) {
  const map = useMapEvents({ click: (e) => active && onPlace(e.latlng.lat, e.latlng.lng) });
  useEffect(() => {
    map.getContainer().style.cursor = active ? "crosshair" : "";
  }, [active, map]);
  return null;
}

export default function Bikes() {
  const { notify } = useAdmin();
  const [bikes, setBikes] = useState<BikesData | null>(null);
  const [systemId, setSystemId] = useState("");
  const [editingSystem, setEditingSystem] = useState<{ original: string | null; form: BikeSystem } | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await admin.bikes();
      setBikes(data);
      setSystemId((current) =>
        data.systems.some((s) => s.system_id === current) ? current : (data.systems[0]?.system_id ?? ""),
      );
    } catch (e) {
      notify(errorMessage(e));
    }
  }, [notify]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!bikes) return <p>Caricamento…</p>;
  const system = bikes.systems.find((s) => s.system_id === systemId) ?? null;

  return (
    <>
      <PageTitle title="Bike sharing">
        {bikes.systems.length > 1 && (
          <select className="form-select form-select-sm w-auto" aria-label="Sistema di bike sharing" value={systemId} onChange={(e) => { setSystemId(e.target.value); setEditingSystem(null); }}>
            {bikes.systems.map((s) => (
              <option key={s.system_id} value={s.system_id}>
                {s.name}
              </option>
            ))}
          </select>
        )}
        <button type="button" className="btn btn-primary btn-sm" onClick={() => setEditingSystem({ original: null, form: { ...EMPTY_SYSTEM } })}>
          Nuovo sistema
        </button>
      </PageTitle>
      <p className="small text-muted">
        Le stazioni di bike sharing compaiono nell'app accanto alle fermate del bus. Si importano dal feed{" "}
        <abbr title="General Bikeshare Feed Specification">GBFS</abbr> del gestore (indirizzo o file) oppure si
        inseriscono a mano. Bici e stalli liberi sono dati reali del gestore: li legge il server, senza mai inviare
        al gestore la posizione di chi usa l'app.
      </p>

      {editingSystem ? (
        <SystemForm
          original={editingSystem.original}
          initial={editingSystem.form}
          onClose={() => setEditingSystem(null)}
          onSaved={async (id) => {
            setEditingSystem(null);
            setSystemId(id);
            await load();
          }}
        />
      ) : !system ? (
        <div className="alert alert-info">
          Nessun sistema di bike sharing. Con «Nuovo sistema» si indicano il nome, il gestore e il link all'app per il
          noleggio; poi si importano le stazioni.
        </div>
      ) : (
        <>
          <SystemSummary system={system} onEdit={() => setEditingSystem({ original: system.system_id, form: { ...system } })} onChanged={load} />
          <ImportPanel key={`import-${system.system_id}`} system={system} onDone={load} />
          <Stations
            key={`stations-${system.system_id}`}
            system={system}
            stations={bikes.stations.filter((s) => s.system_id === system.system_id)}
            onChanged={load}
          />
        </>
      )}
    </>
  );
}

// ------------------------------------------------------------------ sistema
function SystemForm({ original, initial, onClose, onSaved }: {
  original: string | null;
  initial: BikeSystem;
  onClose: () => void;
  onSaved: (id: string) => Promise<void>;
}) {
  const { save, busy } = useSave();
  const [form, setForm] = useState<BikeSystem>(initial);
  const set = (k: keyof BikeSystem) => (v: string) => setForm((f) => ({ ...f, [k]: v }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    const { last_import: _l, stations: _s, updated_at: _u, ...body } = form;
    void _l; void _s; void _u;
    if (await save(() => admin.saveBikeSystem(original, body), `Sistema «${form.name}» salvato.`)) await onSaved(form.system_id);
  }

  return (
    <form onSubmit={submit} className="card card-bg shadow-sm mb-4" aria-label={original ? `Modifica del sistema ${initial.name}` : "Nuovo sistema"}>
      <div className="card-body">
        <h2 className="h5">{original ? "Modifica sistema" : "Nuovo sistema di bike sharing"}</h2>
        <div className="row">
          <Field className="col-12 col-md-4" label="Identificativo" value={form.system_id} onChange={set("system_id")} required help="Lettere, numeri, - e _; es. bici_gioia" />
          <Field className="col-12 col-md-4" label="Nome mostrato ai cittadini" value={form.name} onChange={set("name")} required help="Es. «Glor bike sharing»" />
          <Field className="col-12 col-md-4" label="Gestore" value={form.operator} onChange={set("operator")} />
        </div>
        <div className="row">
          <Field className="col-12 col-md-6" label="Link all'app o al sito per il noleggio" type="url" value={form.app_url} onChange={set("app_url")} help="Pulsante «Noleggia» nell'app: QuandoPassa non gestisce noleggi né pagamenti." />
          <Field className="col-12 col-md-6" label="Licenza dei dati" type="url" value={form.license_url} onChange={set("license_url")} help="Indicata dal gestore nel feed o nell'accordo." />
        </div>
        <div className="row">
          <Field className="col-12 col-md-6" label="Indirizzo del feed GBFS" type="url" value={form.gbfs_url} onChange={set("gbfs_url")} help="Di solito termina con gbfs.json; si compila da solo dopo un import da indirizzo." />
          <Field className="col-12 col-md-6" label="Indirizzo di station_status" type="url" value={form.status_url} onChange={set("status_url")} help="Bici e stalli liberi in tempo reale; si ricava dal gbfs.json." />
        </div>
        <Check label="Mostra bici e stalli liberi in tempo reale" checked={form.live} onChange={(live) => setForm((f) => ({ ...f, live }))} help="Senza, l'app mostra solo dove sono le stazioni." />
        <div className="d-flex gap-2">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? "Salvataggio…" : "Salva"}
          </button>
          <button type="button" className="btn btn-outline-secondary" onClick={onClose}>
            Annulla
          </button>
        </div>
      </div>
    </form>
  );
}

function SystemSummary({ system, onEdit, onChanged }: { system: BikeSystem; onEdit: () => void; onChanged: () => Promise<void> }) {
  const { save, busy } = useSave();
  const { notify } = useAdmin();
  const [live, setLive] = useState<BikeLiveCheck | null>(null);
  const [checking, setChecking] = useState(false);

  async function check() {
    setChecking(true);
    setLive(null);
    try {
      setLive(await admin.checkBikeStatus(system.system_id));
    } catch (e) {
      notify(errorMessage(e));
    } finally {
      setChecking(false);
    }
  }

  return (
    <section className="card card-bg shadow-sm mb-4" aria-labelledby="titolo-sistema">
      <div className="card-body">
        <div className="d-flex flex-wrap justify-content-between gap-2">
          <h2 className="h5 mb-2" id="titolo-sistema">
            {system.name} <span className="small text-muted fw-normal">· {system.stations ?? 0} stazioni</span>
          </h2>
          <div className="d-flex flex-wrap gap-2 align-items-start">
            <button type="button" className="btn btn-outline-primary btn-sm" onClick={onEdit}>
              Modifica
            </button>
            <button type="button" className="btn btn-outline-primary btn-sm" disabled={!system.status_url || checking} onClick={check}>
              {checking ? "Verifica…" : "Verifica disponibilità"}
            </button>
            <ConfirmButton
              label="Elimina sistema"
              confirmLabel="Elimina sistema e stazioni"
              disabled={busy}
              onConfirm={async () => { if (await save(() => admin.deleteBikeSystem(system.system_id), `Sistema «${system.name}» eliminato.`)) await onChanged(); }}
            />
          </div>
        </div>
        <dl className="row small mb-0">
          <dt className="col-sm-3">Gestore</dt>
          <dd className="col-sm-9">{system.operator || "—"}</dd>
          <dt className="col-sm-3">App per il noleggio</dt>
          <dd className="col-sm-9 text-break">{system.app_url ? <a href={system.app_url} target="_blank" rel="noreferrer">{system.app_url}</a> : "— (nessun pulsante «Noleggia»)"}</dd>
          <dt className="col-sm-3">Tempo reale</dt>
          <dd className="col-sm-9 text-break">
            {system.live && system.status_url ? `attivo · ${system.status_url}` : system.status_url ? "disattivato" : "— (manca station_status)"}
          </dd>
          {system.last_import && (
            <>
              <dt className="col-sm-3">Ultimo import</dt>
              <dd className="col-sm-9">
                {formatDateTime(system.last_import.at)} da {system.last_import.origin}: {system.last_import.added} nuove,{" "}
                {system.last_import.updated} aggiornate, {system.last_import.removed} rimosse
                {system.last_import.kept_manual > 0 && `, ${system.last_import.kept_manual} modificate a mano non toccate`}
                {system.last_import.missing > system.last_import.removed && `, ${system.last_import.missing - system.last_import.removed} non più nel feed`}
              </dd>
            </>
          )}
        </dl>
        <div aria-live="polite">
          {live && (
            <div className={`alert ${live.matched ? "alert-success" : "alert-warning"} small mt-3 mb-0`}>
              Il gestore risponde: {live.stations_in_feed} stazioni nel feed, {live.matched} collegate a quelle del
              sistema, {live.bikes} bici e {live.docks} stalli liberi. Aggiornamento ogni {live.ttl} secondi.
              {live.unknown.length > 0 && <> Stazioni nel feed ma non qui: {live.unknown.join(", ")}.</>}
              {live.without_status.length > 0 && <> Stazioni senza dati: {live.without_status.join(", ")}.</>}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ import GBFS
function ImportPanel({ system, onDone }: { system: BikeSystem; onDone: () => Promise<void> }) {
  const { notify } = useAdmin();
  const { save, busy } = useSave();
  const [mode, setMode] = useState<"url" | "file">(system.gbfs_url ? "url" : "file");
  const [url, setUrl] = useState(system.gbfs_url);
  const [file, setFile] = useState<File | null>(null);
  const [removeMissing, setRemoveMissing] = useState(false);
  const [preview, setPreview] = useState<BikeImportPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const source = mode === "url" ? url.trim() : file;

  useEffect(() => setPreview(null), [mode, url, file, removeMissing]);

  async function runPreview() {
    if (!source) return;
    setLoading(true);
    try {
      setPreview(await admin.previewBikeImport(system.system_id, source, removeMissing));
    } catch (e) {
      notify(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  async function runImport() {
    if (!source || !preview) return;
    const p = preview.plan;
    const result = await save(
      () => admin.importBikes(system.system_id, source, removeMissing),
      `Import completato: ${p.added.length} nuove, ${p.updated.length} aggiornate, ${p.removed.length} rimosse.`,
    );
    if (result) {
      setPreview(null);
      setFile(null);
      await onDone();
    }
  }

  const p = preview?.plan;
  const changes = p ? p.added.length + p.updated.length + p.removed.length : 0;
  return (
    <section className="card card-bg shadow-sm mb-4" aria-labelledby="titolo-import">
      <div className="card-body">
        <h2 className="h5" id="titolo-import">Importa le stazioni dal feed GBFS</h2>
        <fieldset className="mb-2">
          <legend className="visually-hidden">Origine del feed</legend>
          <div className="d-flex gap-4 flex-wrap">
            {(["url", "file"] as const).map((m) => (
              <div className="form-check" key={m}>
                <input className="form-check-input" type="radio" name="origine-gbfs" id={`origine-${m}`} checked={mode === m} onChange={() => setMode(m)} />
                <label className="form-check-label" htmlFor={`origine-${m}`}>
                  {m === "url" ? "Dall'indirizzo del gestore" : "Da un file (JSON o zip)"}
                </label>
              </div>
            ))}
          </div>
        </fieldset>
        {mode === "url" ? (
          <Field label="Indirizzo GBFS" type="url" value={url} onChange={setUrl} placeholder="https://…/gbfs.json" help="gbfs.json (con l'elenco dei file) oppure direttamente station_information.json." />
        ) : (
          <div className="mb-3">
            <label htmlFor="file-gbfs" className="small fw-semibold mb-1 d-block">
              File GBFS
            </label>
            <input id="file-gbfs" type="file" className="form-control" accept=".json,.zip,application/json,application/zip" onChange={(e) => setFile(e.target.files?.[0] ?? null)} aria-describedby="file-gbfs-aiuto" />
            <small id="file-gbfs-aiuto" className="form-text d-block text-muted">
              station_information.json, oppure uno zip con i file del feed (gbfs, system_information, station_information). Al massimo 5 MB.
            </small>
          </div>
        )}
        <Check
          label="Rimuovi le stazioni importate che non sono più nel feed"
          checked={removeMissing}
          onChange={setRemoveMissing}
          help="Le stazioni inserite o modificate a mano non vengono mai rimosse né sovrascritte."
        />
        <button type="button" className="btn btn-outline-primary" disabled={!source || loading || busy} onClick={runPreview}>
          {loading ? "Lettura del feed…" : "Anteprima delle modifiche"}
        </button>

        <div aria-live="polite">
          {preview && p && (
            <div className="mt-3">
              <h3 className="h6">Anteprima</h3>
              <ul className="small mb-2">
                <li>Nuove: {p.added.length}{p.added.length > 0 && ` (${p.added.slice(0, 15).join(", ")}${p.added.length > 15 ? "…" : ""})`}</li>
                <li>Aggiornate: {p.updated.length}{p.updated.length > 0 && ` (${p.updated.slice(0, 15).join(", ")}${p.updated.length > 15 ? "…" : ""})`}</li>
                <li>Invariate: {p.unchanged}</li>
                {p.kept_manual.length > 0 && <li>Modificate a mano, non toccate: {p.kept_manual.join(", ")}</li>}
                {p.missing.length > 0 && (
                  <li>
                    Non più nel feed: {p.missing.join(", ")} {removeMissing ? "— verranno rimosse" : "— restano (spuntare la casella per rimuoverle)"}
                  </li>
                )}
                {preview.status_url && <li>Disponibilità in tempo reale trovata: {preview.status_url}</li>}
                {preview.system_information?.name && (
                  <li>
                    Sistema nel feed: {preview.system_information.name}
                    {preview.system_information.operator && ` · ${preview.system_information.operator}`}
                  </li>
                )}
              </ul>
              {preview.warnings.length > 0 && (
                <details className="small mb-2">
                  <summary>Righe del feed scartate ({preview.warnings.length})</summary>
                  <ul className="mb-0">
                    {preview.warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                </details>
              )}
              <button type="button" className="btn btn-primary" disabled={busy} onClick={runImport}>
                {busy ? "Import in corso…" : changes ? `Importa (${changes} modifiche)` : "Importa (aggiorna solo i dati del sistema)"}
              </button>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ stazioni
function Stations({ system, stations, onChanged }: { system: BikeSystem; stations: BikeStation[]; onChanged: () => Promise<void> }) {
  const { data } = useAdmin();
  const { save, busy } = useSave();
  const [selected, setSelected] = useState<string | null>(null); // id originale, "" = nuova
  const [form, setForm] = useState<BikeStation>(EMPTY_STATION);
  const [filter, setFilter] = useState("");
  const [placing, setPlacing] = useState(false);

  const busStops = useMemo(() => (data?.stops ?? []).filter((s) => s.lat !== null), [data]);
  const visible = stations.filter((s) =>
    `${s.station_id} ${s.name} ${s.short_name} ${s.address}`.toLowerCase().includes(filter.trim().toLowerCase()),
  );
  const editing = selected !== null;
  const set = (k: keyof BikeStation) => (v: string) => setForm((f) => ({ ...f, [k]: v }));
  const setNumber = (k: "lat" | "lon" | "capacity") => (v: string) => setForm((f) => ({ ...f, [k]: v === "" ? null : Number(v) }));
  const current = stations.find((s) => s.station_id === selected);

  function open(id: string) {
    const s = stations.find((x) => x.station_id === id);
    if (!s) return;
    setForm({ ...s });
    setSelected(id);
    setPlacing(false);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const { system_id: _s, source: _o, nearby_stops: _n, updated_at: _u, ...body } = form;
    void _s; void _o; void _n; void _u;
    const result = await save(() => admin.saveBikeStation(system.system_id, selected || null, body), `Stazione «${form.name}» salvata.`);
    if (result) {
      setSelected(form.station_id);
      setPlacing(false);
      await onChanged();
    }
  }

  async function remove() {
    if (await save(() => admin.deleteBikeStation(system.system_id, selected!), `Stazione «${form.name}» eliminata.`)) {
      setSelected(null);
      await onChanged();
    }
  }

  const points = stations.filter((s) => s.lat !== null).map((s) => [s.lat!, s.lon!] as [number, number]);

  return (
    <section aria-labelledby="titolo-stazioni">
      <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-2">
        <h2 className="h5 mb-0" id="titolo-stazioni">Stazioni</h2>
        <button type="button" className="btn btn-outline-primary btn-sm" onClick={() => { setSelected(""); setForm({ ...EMPTY_STATION }); setPlacing(true); }}>
          Nuova stazione
        </button>
      </div>
      <p className="small text-muted">
        Quadrati verdi: stazioni (tratteggiate se disattivate). Punti grigi: fermate del bus. Trascina una stazione per
        spostarla, poi salva.
      </p>
      <div className="row g-4">
        <div className="col-12 col-xl-7">
          <BaseMap label="Mappa delle stazioni di bike sharing e delle fermate del bus" fit={selected === null ? points : []}>
            <PlaceOnClick active={placing} onPlace={(lat, lon) => { setForm((f) => ({ ...f, lat: round6(lat), lon: round6(lon) })); setPlacing(false); }} />
            {busStops.map((s) => (
              <CircleMarker key={`bus-${s.stop_id}`} center={[s.lat!, s.lon!]} radius={5} pathOptions={{ color: "#5c6f82", weight: 2, fillColor: "#fff", fillOpacity: 1 }}>
                <Tooltip>Fermata bus: {s.stop_name}</Tooltip>
              </CircleMarker>
            ))}
            {stations
              .filter((s) => s.station_id !== selected && s.lat !== null)
              .map((s) => (
                <Marker key={s.station_id} position={[s.lat!, s.lon!]} icon={bikeIcon(s.short_name || s.station_id, s.active ? "normal" : "inactive")} eventHandlers={{ click: () => open(s.station_id) }} keyboard title={s.name}>
                  <Tooltip>{s.name}</Tooltip>
                </Marker>
              ))}
            {editing && form.lat !== null && form.lon !== null && (
              <Marker
                position={[form.lat, form.lon]}
                icon={bikeIcon(form.short_name || form.station_id || "?", "selected")}
                draggable
                eventHandlers={{ dragend: (e) => { const p = e.target.getLatLng(); setForm((f) => ({ ...f, lat: round6(p.lat), lon: round6(p.lng) })); } }}
                title={`${form.name} (trascinabile)`}
              >
                <Tooltip permanent direction="top" offset={[0, -16]}>
                  {form.name || "Nuova stazione"}
                </Tooltip>
              </Marker>
            )}
          </BaseMap>
          {placing && <p className="small mt-2 fw-semibold">Fai clic sulla mappa nel punto della stazione.</p>}
        </div>

        <div className="col-12 col-xl-5">
          {editing ? (
            <form onSubmit={submit} aria-label={selected ? `Modifica della stazione ${form.name}` : "Nuova stazione"}>
              <h3 className="h6">{selected ? "Modifica stazione" : "Nuova stazione"}</h3>
              {current?.source === "gbfs" && (
                <p className="small alert alert-info py-2">
                  Stazione importata dal feed. Salvandola diventa «modificata a mano»: i prossimi import non la cambiano più.
                </p>
              )}
              <div className="row">
                <Field className="col-6" label="Identificativo" value={form.station_id} onChange={set("station_id")} required help="station_id del feed GBFS" />
                <Field className="col-6" label="Sigla" value={form.short_name} onChange={set("short_name")} help="Sul segnaposto in mappa" />
              </div>
              <Field label="Nome" value={form.name} onChange={set("name")} required />
              <Field label="Indirizzo" value={form.address} onChange={set("address")} />
              <div className="row">
                <Field className="col-6" label="Latitudine" type="number" step="0.000001" value={form.lat} onChange={setNumber("lat")} required />
                <Field className="col-6" label="Longitudine" type="number" step="0.000001" value={form.lon} onChange={setNumber("lon")} required />
              </div>
              <div className="mb-3">
                <button type="button" className="btn btn-outline-primary btn-sm" onClick={() => setPlacing(true)}>
                  Scegli il punto sulla mappa
                </button>
              </div>
              <Field label="Stalli" type="number" min={0} value={form.capacity} onChange={setNumber("capacity")} help="Numero di posti bici della stazione" />
              <Check label="Attiva (visibile nell'app)" checked={form.active} onChange={(active) => setForm((f) => ({ ...f, active }))} />
              <Field label="Note interne" value={form.note} onChange={set("note")} textarea rows={2} help="Non pubblicate" />
              {current?.nearby_stops && current.nearby_stops.length > 0 && (
                <p className="small">
                  Fermate del bus vicine: {current.nearby_stops.map((n) => `${n.name} (${n.meters} m)`).join(", ")}
                </p>
              )}
              <div className="d-flex gap-2 flex-wrap align-items-center">
                <button type="submit" className="btn btn-primary" disabled={busy || form.lat === null || form.lon === null}>
                  {busy ? "Salvataggio…" : "Salva"}
                </button>
                <button type="button" className="btn btn-outline-secondary" onClick={() => { setSelected(null); setPlacing(false); }}>
                  Chiudi
                </button>
                {selected && <ConfirmButton label="Elimina" confirmLabel="Conferma eliminazione" onConfirm={remove} disabled={busy} />}
              </div>
            </form>
          ) : (
            <>
              <label htmlFor="filtro-stazioni" className="small fw-semibold mb-1 d-block">
                Cerca una stazione
              </label>
              <input id="filtro-stazioni" className="form-control mb-2" value={filter} onChange={(e) => setFilter(e.target.value)} />
              {stations.length === 0 && <p className="small">Nessuna stazione: importale dal feed GBFS o aggiungile a mano.</p>}
              <div className="list-group lista-admin">
                {visible.map((s) => (
                  <button type="button" key={s.station_id} className="list-group-item list-group-item-action" onClick={() => open(s.station_id)}>
                    <span className="d-flex justify-content-between gap-2">
                      <span>
                        <span className="fw-semibold">{s.short_name || s.station_id}</span> · {s.name}
                        {!s.active && <span className="badge bg-secondary ms-2">disattivata</span>}
                        <span className={`badge ms-2 ${s.source === "gbfs" ? "bg-light text-dark border" : "bg-warning text-dark"}`}>
                          {s.source === "gbfs" ? "dal feed" : "manuale"}
                        </span>
                      </span>
                      <span className="small text-muted text-nowrap">{s.capacity ?? "?"} stalli</span>
                    </span>
                    <span className="small text-muted d-block">
                      {s.nearby_stops?.length
                        ? `Bus: ${s.nearby_stops.map((n) => `${n.stop_code || n.stop_id} ${n.name} (${n.meters} m)`).join(" · ")}`
                        : "Nessuna fermata del bus entro 300 m"}
                    </span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
