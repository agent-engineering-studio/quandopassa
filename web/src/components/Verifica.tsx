import { useEffect, useRef, useState } from "react";
import type { EsitoVerifica } from "../api";
import { api } from "../api";
import Icona, { IconaBus } from "../Icona";

const CHIAVE = "quandopassa.controllore";

interface Rilevatore {
  detect: (v: HTMLVideoElement) => Promise<{ rawValue: string }[]>;
}

/** Pagina del controllore (/verifica): codice o QR del biglietto, esito immediato. */
export default function Verifica() {
  const [credenziali, setCredenziali] = useState<string | null>(() => {
    try {
      return sessionStorage.getItem(CHIAVE);
    } catch {
      return null;
    }
  });
  const [utente, setUtente] = useState("");
  const [password, setPassword] = useState("");
  const [codice, setCodice] = useState("");
  const [esito, setEsito] = useState<EsitoVerifica | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [camera, setCamera] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const puoScansionare = typeof window !== "undefined" && "BarcodeDetector" in window;

  const verifica = async (dato: string) => {
    if (!credenziali || !dato.trim()) return;
    setErrore(null);
    try {
      setEsito(await api.verifica(dato, credenziali));
      setCodice("");
    } catch (e) {
      const m = (e as Error).message;
      if (m.includes("Credenziali")) esci();
      setErrore(m);
    }
  };

  const esci = () => {
    try {
      sessionStorage.removeItem(CHIAVE);
    } catch {
      /* niente da fare */
    }
    setCredenziali(null);
  };

  // lettura del QR con la fotocamera (BarcodeDetector, dove il browser lo offre)
  useEffect(() => {
    if (!camera || !video.current) return;
    let fermo = false;
    let flusso: MediaStream | null = null;
    const Rilev = (window as unknown as { BarcodeDetector: new (o: object) => Rilevatore }).BarcodeDetector;
    const rilevatore = new Rilev({ formats: ["qr_code"] });
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment" } })
      .then(async (s) => {
        flusso = s;
        video.current!.srcObject = s;
        await video.current!.play();
        while (!fermo) {
          const trovati = await rilevatore.detect(video.current!).catch(() => []);
          if (trovati[0]) {
            setCamera(false);
            verifica(trovati[0].rawValue);
            break;
          }
          await new Promise((r) => setTimeout(r, 250));
        }
      })
      .catch(() => {
        setCamera(false);
        setErrore("Fotocamera non disponibile: inserisci il codice a mano.");
      });
    return () => {
      fermo = true;
      flusso?.getTracks().forEach((t) => t.stop());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [camera]);

  return (
    <>
      <header className="it-header-wrapper">
        <div className="it-nav-wrapper">
          <div className="it-header-center-wrapper it-small-header">
            <div className="container">
              <div className="it-header-center-content-wrapper">
                <div className="it-brand-wrapper ps-0">
                  <a href="/">
                    <span className="me-2 text-white d-inline-flex">
                      <IconaBus dim={36} />
                    </span>
                    <div className="it-brand-text">
                      <div className="it-brand-title">QuandoPassa</div>
                      <div className="it-brand-tagline">Verifica dei biglietti</div>
                    </div>
                  </a>
                </div>
              </div>
            </div>
          </div>
        </div>
      </header>
      <main className="container my-4 verifica" style={{ maxWidth: 560 }}>
        {!credenziali ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const c = btoa(`${utente}:${password}`);
              try {
                sessionStorage.setItem(CHIAVE, c);
              } catch {
                /* resta valida finché la pagina è aperta */
              }
              setCredenziali(c);
            }}
          >
            <h1 className="h3">Accesso controllore</h1>
            <div className="form-group">
              <label htmlFor="utente" className="active">
                Utente
              </label>
              <input id="utente" className="form-control" autoComplete="username" value={utente} onChange={(e) => setUtente(e.currentTarget.value)} />
            </div>
            <div className="form-group">
              <label htmlFor="password" className="active">
                Password
              </label>
              <input
                id="password"
                type="password"
                className="form-control"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.currentTarget.value)}
              />
            </div>
            <button type="submit" className="btn btn-primary w-100" disabled={!utente || !password}>
              Entra
            </button>
          </form>
        ) : (
          <>
            <div className="d-flex justify-content-between align-items-center mb-3">
              <h1 className="h3 mb-0">Verifica biglietto</h1>
              <button type="button" className="btn btn-outline-primary btn-xs" onClick={esci}>
                Esci
              </button>
            </div>
            {esito && (
              <div className={`esito-verifica esito-verifica-${esito.esito} mb-3`} role="status" aria-live="assertive">
                <strong className="d-block fs-2">
                  {{ valido: "✓ VALIDO", scaduto: "✕ SCADUTO", non_valido: "✕ NON VALIDO" }[esito.esito]}
                </strong>
                <span className="d-block">{esito.messaggio}</span>
                {esito.titolo && (
                  <span className="small">
                    {esito.titolo} · codice {esito.codice}
                  </span>
                )}
              </div>
            )}
            {errore && <div className="alert alert-danger py-2">{errore}</div>}
            {camera && <video ref={video} className="w-100 rounded mb-3" muted playsInline aria-label="Inquadra il QR del biglietto" />}
            <form
              className="d-flex gap-2 align-items-end"
              onSubmit={(e) => {
                e.preventDefault();
                verifica(codice);
              }}
            >
              <div className="form-group mb-0 flex-grow-1">
                <label htmlFor="codice" className="active">
                  Codice del biglietto (6 caratteri)
                </label>
                <input
                  id="codice"
                  className="form-control tabular text-uppercase"
                  autoComplete="off"
                  maxLength={200}
                  value={codice}
                  onChange={(e) => setCodice(e.currentTarget.value)}
                />
              </div>
              <button type="submit" className="btn btn-primary" disabled={!codice.trim()}>
                Verifica
              </button>
            </form>
            {puoScansionare && !camera && (
              <button type="button" className="btn btn-outline-primary btn-icon w-100 mt-3" onClick={() => setCamera(true)}>
                <Icona nome="it-zoom-in" classe="icon-sm icon-primary" />
                <span>Leggi il QR con la fotocamera</span>
              </button>
            )}
            <p className="small text-muted mt-3 mb-0">
              Ogni verifica registra solo codice, esito e ora: nessun dato della persona.
            </p>
          </>
        )}
      </main>
    </>
  );
}
