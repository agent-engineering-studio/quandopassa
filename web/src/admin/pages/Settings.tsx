// Impostazioni: intestazione dell'app (logo, ente, titolo), mappa, ricerca dei luoghi, biglietti.
import { useEffect, useState, type FormEvent } from "react";
import { IconaBus } from "../../Icona";
import { admin, type SettingsResponse } from "../api";
import { Field, PageTitle, errorMessage, useAdmin, useSave } from "../ui";

const HEADER_KEYS = ["comune", "entity_url", "app_title", "servizio", "logo_alt"];

export default function Settings() {
  const { notify, info } = useAdmin();
  const { save, busy } = useSave();
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [logoFile, setLogoFile] = useState<File | null>(null);

  const load = () =>
    admin
      .settings()
      .then((s) => {
        setSettings(s);
        setValues(Object.fromEntries(s.fields.map((f) => [f.key, f.value])));
      })
      .catch((e) => notify(errorMessage(e)));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => void load(), []);

  if (!settings) return <p>Caricamento…</p>;
  const changed = settings.fields.filter((f) => values[f.key] !== f.value);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const body = Object.fromEntries(changed.map((f) => [f.key, values[f.key]]));
    if (await save(() => admin.saveSettings(body), "Impostazioni salvate.")) await load();
  }

  async function reset(key: string) {
    if (await save(() => admin.saveSettings({ [key]: null }), "Ripristinato il valore del file .env.")) await load();
  }

  async function uploadLogo() {
    if (!logoFile) return;
    if (await save(() => admin.uploadLogo(logoFile), "Logo aggiornato.")) {
      setLogoFile(null);
      await load();
    }
  }

  const renderField = (key: string) => {
    const f = settings.fields.find((x) => x.key === key);
    if (!f) return null;
    return (
      <div key={key}>
        <Field
          label={f.label}
          value={values[key] ?? ""}
          onChange={(v) => setValues({ ...values, [key]: v })}
          help={`${f.help}${f.custom ? ` Valore del .env: «${f.env_value || "vuoto"}».` : ""}`}
          textarea={key === "biglietti" || key === "mappa_attribuzione"}
          rows={2}
        />
        {f.custom && (
          <button type="button" className="btn btn-link btn-sm p-0 mb-3" onClick={() => reset(key)} disabled={busy}>
            Torna al valore del .env
          </button>
        )}
      </div>
    );
  };

  const logoUrl = settings.logo;
  return (
    <>
      <PageTitle title="Impostazioni" />
      <form onSubmit={submit}>
        <div className="row g-4">
          <div className="col-12 col-lg-6">
            <h2 className="h5">Intestazione dell'app</h2>
            <p className="small text-muted">Come appare in alto nella pagina dei cittadini.</p>
            <div className="anteprima-testata mb-3" aria-label="Anteprima dell'intestazione">
              <div className="bg-primary-dark text-white small px-3 py-1" style={{ background: "#004d99" }}>
                {values.comune || "—"}
                {values.entity_url && <span className="opacity-75"> · {values.entity_url}</span>}
              </div>
              <div className="d-flex align-items-center gap-2 px-3 py-2 text-white" style={{ background: "#0066cc" }}>
                {logoUrl ? <img src={logoUrl} alt={values.logo_alt || ""} /> : <IconaBus dim={40} />}
                <div>
                  <div className="fw-bold fs-5 lh-1">{values.app_title || "QuandoPassa"}</div>
                  <div className="small">{values.servizio}</div>
                </div>
              </div>
            </div>
            {HEADER_KEYS.map(renderField)}

            <h3 className="h6">Logo</h3>
            <p className="small text-muted">PNG, JPEG, WebP o SVG fino a 512 kB; meglio su sfondo trasparente e chiaro sul blu.</p>
            <div className="d-flex flex-wrap gap-2 align-items-center mb-3">
              <label htmlFor="file-logo" className="visually-hidden">File del logo</label>
              <input
                id="file-logo"
                type="file"
                className="form-control"
                accept="image/png,image/jpeg,image/webp,image/svg+xml"
                onChange={(e) => setLogoFile(e.target.files?.[0] ?? null)}
              />
              <button type="button" className="btn btn-outline-primary btn-sm" disabled={!logoFile || busy} onClick={uploadLogo}>
                Carica il logo
              </button>
              {logoUrl && (
                <button type="button" className="btn btn-outline-danger btn-sm" disabled={busy} onClick={async () => { if (await save(() => admin.deleteLogo(), "Logo rimosso.")) await load(); }}>
                  Togli il logo
                </button>
              )}
            </div>
          </div>

          <div className="col-12 col-lg-6">
            <h2 className="h5">Mappa e ricerca</h2>
            {["centro", "mappa_tiles", "mappa_attribuzione", "geocoder"].map(renderField)}
            <h2 className="h5 mt-4">Biglietti</h2>
            {["biglietti", "link_biglietti", "biglietteria_nome"].map(renderField)}
          </div>
        </div>
        <div className="d-flex gap-2 align-items-center mb-4">
          <button type="submit" className="btn btn-primary" disabled={busy || changed.length === 0}>
            {busy ? "Salvataggio…" : changed.length ? `Salva (${changed.length} modifiche)` : "Nessuna modifica"}
          </button>
        </div>
      </form>

      <h2 className="h5">Solo nel file .env</h2>
      <p className="small text-muted">
        Credenziali, cartelle, indirizzi interni e intelligenza artificiale si cambiano solo dal sistemista, per
        sicurezza. Ora: {info.header.title}.
      </p>
      <table className="table table-sm small">
        <tbody>
          {settings.read_only.map((r) => (
            <tr key={r.variable}>
              <th scope="row" className="font-monospace">{r.variable}</th>
              <td className="text-break">{r.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
