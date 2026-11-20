// Registro: chi ha modificato cosa e quando.
import { useEffect, useState } from "react";
import { admin, formatDateTime, type AuditEntry } from "../api";
import { PageTitle, errorMessage, useAdmin } from "../ui";

export default function Audit() {
  const { notify } = useAdmin();
  const [rows, setRows] = useState<AuditEntry[] | null>(null);
  useEffect(() => {
    admin.audit(300).then(setRows).catch((e) => notify(errorMessage(e)));
  }, [notify]);
  return (
    <>
      <PageTitle title="Registro delle modifiche" />
      <p className="small text-muted">Le ultime 300 operazioni. Il registro si conserva per il tempo stabilito con il RPD.</p>
      {!rows ? (
        <p>Caricamento…</p>
      ) : (
        <div className="table-responsive">
          <table className="table table-sm small">
            <thead>
              <tr>
                <th scope="col">Quando</th>
                <th scope="col">Utente</th>
                <th scope="col">Operazione</th>
                <th scope="col">Oggetto</th>
                <th scope="col">Dettagli</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="text-nowrap">{formatDateTime(r.at)}</td>
                  <td>{r.username}</td>
                  <td>{r.action}</td>
                  <td>{r.target}</td>
                  <td>
                    {r.details && (
                      <details>
                        <summary>mostra</summary>
                        <pre className="small mb-0">{JSON.stringify(r.details, null, 1)}</pre>
                      </details>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
