import L from "leaflet";
import { useEffect, useMemo } from "react";
import { Circle, CircleMarker, MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { Fermata, Info, LineaDettaglio } from "../api";
import type { Veicolo } from "../motore";
import { hhmmDaSecondi } from "../motore";

interface Props {
  info: Info;
  linee: LineaDettaglio[];
  fermate: Fermata[];
  veicoli: Veicolo[];
  lineeVisibili: string[];
  posizione: { lat: number; lon: number; accuratezza: number } | null;
  selezionata: string | null;
  corsaEvidenziata: string | null;
  onFermata: (id: string) => void;
  centraSu: [number, number] | null;
}

const cacheIcone = new Map<string, L.DivIcon>();

// icone riusate (direzione arrotondata a 10°): niente ricreazione del DOM a ogni secondo
function iconaBus(lettera: string, colore: string, direzioneEsatta: number, evidenziato: boolean) {
  const direzione = Math.round(direzioneEsatta / 10) * 10;
  const chiave = `${lettera}|${colore}|${direzione}|${evidenziato}`;
  const esistente = cacheIcone.get(chiave);
  if (esistente) return esistente;
  const icona = creaIcona(lettera, colore, direzione, evidenziato);
  cacheIcone.set(chiave, icona);
  return icona;
}

function creaIcona(lettera: string, colore: string, direzione: number, evidenziato: boolean) {
  const dim = evidenziato ? 40 : 34;
  return L.divIcon({
    className: "bus-icona",
    iconSize: [dim, dim],
    iconAnchor: [dim / 2, dim / 2],
    html: `<div class="bus${evidenziato ? " bus-evidenziato" : ""}" style="--c:${colore};width:${dim}px;height:${dim}px">
      <div class="bus-freccia" style="transform:rotate(${direzione}deg)"><span></span></div>
      <div class="bus-corpo"><svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="M6 2h12a3 3 0 0 1 3 3v11a2 2 0 0 1-1 1.7V20a1 1 0 0 1-1 1h-1a1 1 0 0 1-1-1v-1H7v1a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-2.3A2 2 0 0 1 3 16V5a3 3 0 0 1 3-3Zm0 3v6h12V5H6Zm1.5 8.5a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3Zm9 0a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3Z"/></svg><b>${lettera}</b></div>
    </div>`,
  });
}

function Centra({ centro }: { centro: [number, number] | null }) {
  const map = useMap();
  useEffect(() => {
    if (centro) map.flyTo(centro, Math.max(map.getZoom(), 16), { duration: 0.6 });
  }, [centro, map]);
  return null;
}

// il contenitore cambia dimensione (rotazione, layout mobile/desktop): Leaflet va avvisato
function Ridimensiona() {
  const map = useMap();
  useEffect(() => {
    const ro = new ResizeObserver(() => map.invalidateSize());
    ro.observe(map.getContainer());
    return () => ro.disconnect();
  }, [map]);
  return null;
}

function Adatta({ fermate }: { fermate: Fermata[] }) {
  const map = useMap();
  useEffect(() => {
    if (fermate.length) {
      map.fitBounds(L.latLngBounds(fermate.map((f) => [f.lat, f.lon] as [number, number])), { padding: [40, 40] });
    }
    // solo al primo caricamento
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fermate.length]);
  return null;
}

export default function Mappa(p: Props) {
  const coloreLinea = useMemo(() => new Map(p.linee.map((l) => [l.id, l.colore])), [p.linee]);
  const nomeLinea = useMemo(() => new Map(p.linee.map((l) => [l.id, l.nome])), [p.linee]);
  const fermateById = useMemo(() => new Map(p.fermate.map((f) => [f.id, f])), [p.fermate]);

  return (
    <MapContainer center={p.info.centro} zoom={15} zoomControl={false} className="mappa" preferCanvas={false}>
      <TileLayer url={p.info.mappa.tiles} attribution={p.info.mappa.attribuzione} maxZoom={19} />
      <Ridimensiona />
      <Adatta fermate={p.fermate} />
      <Centra centro={p.centraSu} />

      {p.linee
        .filter((l) => p.lineeVisibili.includes(l.id))
        .flatMap((l) =>
          l.tracciati.map((t) => (
            <Polyline
              key={t.id}
              positions={t.punti}
              pathOptions={{ color: l.colore, weight: 5, opacity: 0.75, lineJoin: "round" }}
            />
          )),
        )}

      {p.fermate
        .filter((f) => (f.linee ?? []).some((l) => p.lineeVisibili.includes(l)))
        .map((f) => {
          const sel = f.id === p.selezionata;
          const colore = coloreLinea.get((f.linee ?? [])[0] ?? "") ?? "#0066cc";
          return (
            <CircleMarker
              key={f.id}
              center={[f.lat, f.lon]}
              radius={sel ? 10 : 7}
              pathOptions={{
                color: (f.linee ?? []).length > 1 ? "#212529" : colore,
                weight: sel ? 4 : 3,
                fillColor: "#ffffff",
                fillOpacity: 1,
                dashArray: f.provvisoria ? "3 3" : undefined,
              }}
              eventHandlers={{ click: () => p.onFermata(f.id) }}
            >
              <Tooltip direction="top" offset={[0, -6]}>
                <strong>{f.nome}</strong>
                <br />
                Linee {(f.linee ?? []).join(", ")}
                {f.provvisoria ? <><br /><em>posizione provvisoria</em></> : null}
              </Tooltip>
            </CircleMarker>
          );
        })}

      {p.posizione && (
        <>
          <Circle
            center={[p.posizione.lat, p.posizione.lon]}
            radius={Math.min(p.posizione.accuratezza, 200)}
            pathOptions={{ color: "#0066cc", weight: 1, fillOpacity: 0.1 }}
          />
          <CircleMarker
            center={[p.posizione.lat, p.posizione.lon]}
            radius={8}
            pathOptions={{ color: "#fff", weight: 3, fillColor: "#0066cc", fillOpacity: 1 }}
          >
            <Tooltip>Sei qui</Tooltip>
          </CircleMarker>
        </>
      )}

      {p.veicoli
        .filter((v) => p.lineeVisibili.includes(v.corsa.linea_id))
        .map((v) => {
          const evid = v.corsa.id === p.corsaEvidenziata;
          const prossima = fermateById.get(v.corsa.fermate[v.prossima]);
          return (
            <Marker
              key={v.corsa.id}
              position={[v.lat, v.lon]}
              icon={iconaBus(nomeLinea.get(v.corsa.linea_id) ?? "?", coloreLinea.get(v.corsa.linea_id) ?? "#333", v.direzione, evid)}
              zIndexOffset={evid ? 1000 : 500}
            >
              <Tooltip direction="top" offset={[0, -16]}>
                <strong>Linea {nomeLinea.get(v.corsa.linea_id)}</strong> · {v.corsa.destinazione}
                <br />
                {v.stato === "in_fermata" ? "Ferma a " : "Prossima: "}
                {prossima?.nome} ({hhmmDaSecondi(v.arrivoProssima)})
                <br />
                <em>posizione stimata dall'orario</em>
              </Tooltip>
            </Marker>
          );
        })}
    </MapContainer>
  );
}
