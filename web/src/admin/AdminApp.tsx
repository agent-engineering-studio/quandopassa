// Backoffice di QuandoPassa: accesso, intestazione, menu e pagine (navigazione con l'hash dell'indirizzo).
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, type Info } from "../api";
import Icona, { IconaBus } from "../Icona";
import { admin, ApiError, setCsrf, type Snapshot, type Status } from "./api";
import Alerts from "./pages/Alerts";
import Audit from "./pages/Audit";
import Bikes from "./pages/Bikes";
import Calendars from "./pages/Calendars";
import Dashboard from "./pages/Dashboard";
import Feed from "./pages/Feed";
import Lines from "./pages/Lines";
import Settings from "./pages/Settings";
import Stops from "./pages/Stops";
import { AdminContext, Field, Notice, errorMessage, type Message } from "./ui";

const PAGES = [
  { hash: "", label: "Cruscotto", icon: "it-chart-line", component: Dashboard },
  { hash: "avvisi", label: "Avvisi", icon: "it-warning-circle", component: Alerts },
  { hash: "fermate", label: "Fermate", icon: "it-map-marker", component: Stops },
  { hash: "linee", label: "Linee e orari", icon: "it-list", component: Lines },
  { hash: "calendari", label: "Calendari", icon: "it-calendar", component: Calendars },
  { hash: "bike-sharing", label: "Bike sharing", icon: "it-map-marker-circle", component: Bikes },
  { hash: "feed", label: "Feed GTFS", icon: "it-file", component: Feed },
  { hash: "impostazioni", label: "Impostazioni", icon: "it-settings", component: Settings },
  { hash: "registro", label: "Registro", icon: "it-clock", component: Audit },
] as const;

const currentHash = () => window.location.hash.replace(/^#\/?/, "");

type Phase = "loading" | "disabled" | "login" | "ready" | "error";

export default function AdminApp() {
  const [phase, setPhase] = useState<Phase>("loading");
  const [username, setUsername] = useState("");
  const [info, setInfo] = useState<Info | null>(null);
  const [data, setData] = useState<Snapshot | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [message, setMessage] = useState<Message | null>(null);
  const [page, setPage] = useState(currentHash());
  const [fatal, setFatal] = useState("");

  useEffect(() => {
    const onHash = () => {
      setPage(currentHash());
      setMessage(null);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const reload = useCallback(async () => {
    const [d, s, i] = await Promise.all([admin.data(), admin.status(), api.info()]);
    setData(d);
    setStatus(s);
    setInfo(i);
  }, []);

  const enter = useCallback(
    async (user: string, csrf: string) => {
      setCsrf(csrf);
      setUsername(user);
      try {
        await reload();
        setPhase("ready");
      } catch (e) {
        setFatal(errorMessage(e).text);
        setPhase("error");
      }
    },
    [reload],
  );

  useEffect(() => {
    api.info().then(setInfo).catch(() => undefined);
    admin
      .session()
      .then((s) => enter(s.username, s.csrf))
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) setPhase("disabled");
        else if (e instanceof ApiError && e.status === 401) setPhase("login");
        else {
          setFatal(errorMessage(e).text);
          setPhase("error");
        }
      });
  }, [enter]);

  async function logout() {
    try {
      await admin.logout();
    } finally {
      setCsrf("");
      setData(null);
      setPhase("login");
    }
  }

  const current = PAGES.find((p) => p.hash === page) ?? PAGES[0];
  const Page = current.component;
  useEffect(() => {
    document.title = `${current.label} · Backoffice · ${info?.header?.title ?? "QuandoPassa"}`;
  }, [current.label, info]);

  return (
    <>
      <div className="skiplinks">
        <a className="visually-hidden-focusable" href="#contenuto">
          Vai al contenuto
        </a>
      </div>
      <header className="it-header-wrapper">
        <div className="it-header-slim-wrapper">
          <div className="container-xxl">
            <div className="it-header-slim-wrapper-content">
              <span className="navbar-brand">{info?.header?.entity_name ?? info?.comune ?? ""}</span>
              <div className="it-header-slim-right-zone gap-3">
                <a className="text-white small" href="/">
                  Vai all'app pubblica
                </a>
                {phase === "ready" && (
                  <>
                    <span className="text-white small d-none d-md-inline">Utente: {username}</span>
                    <button type="button" className="btn btn-sm btn-outline-light py-0" onClick={logout}>
                      Esci
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
        <div className="it-nav-wrapper">
          <div className="it-header-center-wrapper it-small-header">
            <div className="container-xxl">
              <div className="it-header-center-content-wrapper">
                <div className="it-brand-wrapper ps-0">
                  <a href="#/">
                    {info?.header?.logo_url ? (
                      <img src={info.header.logo_url} alt="" className="logo-testata me-2" />
                    ) : (
                      <span className="me-2 text-white d-inline-flex">
                        <IconaBus dim={40} />
                      </span>
                    )}
                    <div className="it-brand-text">
                      <div className="it-brand-title">{info?.header?.title ?? "QuandoPassa"}</div>
                      <div className="it-brand-tagline">Backoffice dell'ufficio trasporti</div>
                    </div>
                  </a>
                </div>
              </div>
            </div>
          </div>
          {phase === "ready" && (
            <div className="it-header-navbar-wrapper bg-primary">
              <div className="container-xxl">
                <nav aria-label="Sezioni del backoffice" className="admin-nav overflow-auto">
                  <ul className="nav">
                    {PAGES.map((p) => (
                      <li className="nav-item" key={p.hash}>
                        <a
                          className={`nav-link text-white d-flex align-items-center gap-1 ${p === current ? "active" : ""}`}
                          href={`#/${p.hash}`}
                          aria-current={p === current ? "page" : undefined}
                        >
                          <Icona nome={p.icon} classe="icon-sm icon-white" />
                          {p.label}
                        </a>
                      </li>
                    ))}
                  </ul>
                </nav>
              </div>
            </div>
          )}
        </div>
      </header>

      <main id="contenuto" className="container-xxl py-4 admin-main">
        {phase === "loading" && <p>Caricamento…</p>}
        {phase === "disabled" && (
          <div className="alert alert-info">
            <p className="fw-semibold mb-1">Il backoffice non è configurato su questa installazione.</p>
            <p className="mb-0">
              Mancano utente o password nel file <code>.env</code> (<code>ADMIN_USER</code>,{" "}
              <code>ADMIN_PASSWORD</code>): il sistemista li completa con <code>make env</code> (Docker) o rilanciando{" "}
              <code>deploy/install.sh</code> (macchina virtuale). La guida è nella documentazione, pagina «Backoffice».
            </p>
          </div>
        )}
        {phase === "error" && <div className="alert alert-danger">{fatal}</div>}
        {phase === "login" && <Login onLogin={enter} />}
        {phase === "ready" && info && (
          <AdminContext.Provider value={{ username, info, data, status, reload, notify: setMessage }}>
            <Notice message={message} onClose={() => setMessage(null)} />
            <Page />
          </AdminContext.Provider>
        )}
      </main>

      <footer className="it-footer">
        <div className="it-footer-small-prints py-2">
          <div className="container-xxl small text-white">
            QuandoPassa · backoffice · le modifiche sono registrate con utente e ora
          </div>
        </div>
      </footer>
    </>
  );
}

function Login({ onLogin }: { onLogin: (user: string, csrf: string) => void }) {
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const s = await admin.login(user, password);
      setPassword("");
      onLogin(s.username, s.csrf);
    } catch (err) {
      setError(errorMessage(err).text);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="row justify-content-center">
      <div className="col-12 col-md-6 col-lg-4">
        <h1 className="h3 mb-3">Accesso al backoffice</h1>
        <form onSubmit={submit} noValidate>
          <Field label="Utente" value={user} onChange={setUser} required />
          <Field label="Password" type="password" value={password} onChange={setPassword} required />
          <div aria-live="assertive">{error && <div className="alert alert-danger py-2">{error}</div>}</div>
          <button type="submit" className="btn btn-primary w-100" disabled={busy || !user || !password}>
            {busy ? "Accesso in corso…" : "Entra"}
          </button>
        </form>
        <p className="small text-muted mt-3">
          L'accesso è riservato all'ufficio trasporti. Dopo cinque tentativi sbagliati l'accesso si blocca per 15
          minuti.
        </p>
      </div>
    </div>
  );
}
