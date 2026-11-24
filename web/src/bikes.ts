// Bike sharing nell'app pubblica: distanze calcolate sul dispositivo (la posizione non lascia il browser)
import type { BikeStation } from "./api";

export const NEARBY_STOP_METERS = 300; // come nel backoffice: stazioni "vicine" a una fermata
const WALK_SPEED = 1.2; // m/s, come api/quandopassa/gtfs.py
const DETOUR = 1.3; // strada reale / linea d'aria

export interface NearbyBikeStation extends BikeStation {
  distance_m: number;
  walk_min: number;
}

export function distanceMeters(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const r = 6_371_000;
  const toRad = Math.PI / 180;
  const dLat = (lat2 - lat1) * toRad;
  const dLon = (lon2 - lon1) * toRad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) * Math.sin(dLon / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(a));
}

export function nearbyBikeStations(
  stations: BikeStation[],
  lat: number,
  lon: number,
  n = 3,
  radius?: number,
): NearbyBikeStation[] {
  return stations
    .map((s) => {
      const d = distanceMeters(lat, lon, s.lat, s.lon);
      return { ...s, distance_m: Math.round(d), walk_min: Math.max(1, Math.round((d * DETOUR) / WALK_SPEED / 60)) };
    })
    .filter((s) => radius === undefined || s.distance_m <= radius)
    .sort((a, b) => a.distance_m - b.distance_m)
    .slice(0, n);
}

/** Testo breve della disponibilità, per tooltip e lettori di schermo. */
export function availabilityText(s: BikeStation): string {
  if (!s.live || s.bikes === null) return s.capacity ? `${s.capacity} stalli` : "disponibilità non pubblicata";
  if (s.renting === false) return "noleggio non attivo";
  const bikes = s.bikes === 1 ? "1 bici libera" : `${s.bikes} bici libere`;
  if (s.docks === null) return bikes;
  return `${bikes}, ${s.docks === 1 ? "1 stallo libero" : `${s.docks} stalli liberi`}`;
}
