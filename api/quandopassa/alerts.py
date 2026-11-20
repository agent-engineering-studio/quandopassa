"""Avvisi di servizio: deviazioni temporanee, fermate sospese, giorni di servizio sospeso, informazioni.

Gli avvisi si scrivono nel backoffice (Postgres) e a ogni modifica vengono salvati in `alerts.json` accanto al
feed GTFS generato: l'app pubblica li legge da lì e funziona anche senza database.

  info               messaggio informativo per tutti o per alcune linee
  detour             deviazione temporanea di una o più linee: fermate non servite ed eventuale tracciato provvisorio
  stop_closed        fermate sospese (lavori, eventi, maltempo...): nessuna salita o discesa
  service_suspended  servizio sospeso in uno o più giorni (sciopero, festività...): nel GTFS diventa calendar_dates
"""
from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

KINDS = {
    "info": "Informazione",
    "detour": "Deviazione temporanea",
    "stop_closed": "Fermata sospesa",
    "service_suspended": "Servizio sospeso",
}
ALERTS_FILE = "alerts.json"
HORIZON = timedelta(days=7)  # gli avvisi futuri si mostrano una settimana prima


@dataclass
class Alert:
    id: int
    kind: str
    title: str
    description: str
    starts_at: datetime
    ends_at: datetime | None
    route_ids: list[str] = field(default_factory=list)   # vuoto = tutte le linee
    stop_ids: list[str] = field(default_factory=list)    # fermate sospese o non servite dalla deviazione
    shape: list[list[float]] | None = None               # tracciato provvisorio della deviazione

    def active_at(self, when: datetime) -> bool:
        return self.starts_at <= when and (self.ends_at is None or when < self.ends_at)

    def visible_at(self, when: datetime) -> bool:
        return (self.ends_at is None or when < self.ends_at) and self.starts_at <= when + HORIZON

    def applies_to_route(self, route_id: str) -> bool:
        return not self.route_ids or route_id in self.route_ids

    def json(self, when: datetime | None = None) -> dict:
        out = asdict(self)
        out["starts_at"] = self.starts_at.isoformat(timespec="minutes")
        out["ends_at"] = self.ends_at.isoformat(timespec="minutes") if self.ends_at else None
        out["kind_label"] = KINDS.get(self.kind, self.kind)
        if when is not None:
            out["active"] = self.active_at(when)
        return out

    @classmethod
    def from_json(cls, data: dict, tz: ZoneInfo) -> Alert:
        def parse(value):
            if not value:
                return None
            d = value if isinstance(value, datetime) else datetime.fromisoformat(value)
            return d if d.tzinfo else d.replace(tzinfo=tz)

        return cls(id=int(data["id"]), kind=data["kind"], title=data["title"], description=data.get("description") or "",
                   starts_at=parse(data["starts_at"]), ends_at=parse(data.get("ends_at")),
                   route_ids=list(data.get("route_ids") or []), stop_ids=list(data.get("stop_ids") or []),
                   shape=data.get("shape") or None)


class AlertBoard:
    """Gli avvisi in vigore, con le domande che servono all'app (fermata sospesa? deviazioni ora?)."""

    def __init__(self, alerts: list[Alert]):
        self.alerts = sorted(alerts, key=lambda a: (a.starts_at, a.id))

    @classmethod
    def load(cls, folder: Path, tz: ZoneInfo) -> AlertBoard:
        path = folder / ALERTS_FILE
        if not path.exists():
            return cls([])
        return cls([Alert.from_json(a, tz) for a in json.loads(path.read_text(encoding="utf-8"))])

    def visible(self, when: datetime, route_ids: set[str] | None = None, stop_id: str | None = None) -> list[Alert]:
        """Avvisi in corso o in arrivo, eventualmente solo quelli che riguardano linee o fermata indicate."""
        out = []
        for a in self.alerts:
            if not a.visible_at(when):
                continue
            if route_ids is not None and a.route_ids and not (set(a.route_ids) & route_ids):
                if not (stop_id and stop_id in a.stop_ids):
                    continue
            if stop_id is not None and a.kind == "stop_closed" and stop_id not in a.stop_ids:
                continue
            out.append(a)
        return out

    def closed_stops(self, when: datetime, route_id: str | None = None) -> set[str]:
        """Fermate dove non si sale né si scende all'istante dato (sospese o saltate da una deviazione)."""
        out: set[str] = set()
        for a in self.alerts:
            # senza linea (itinerari) conta ogni chiusura, anche quelle di una deviazione che riguarda altre linee
            if a.kind in ("stop_closed", "detour") and a.active_at(when) and (
                    route_id is None or a.applies_to_route(route_id)):
                out.update(a.stop_ids)
        return out

    def closure(self, stop_id: str, when: datetime, route_id: str | None = None) -> Alert | None:
        for a in self.alerts:
            if (a.kind in ("stop_closed", "detour") and stop_id in a.stop_ids and a.active_at(when)
                    and (route_id is None or a.applies_to_route(route_id))):
                return a
        return None

    def detours(self, when: datetime) -> list[Alert]:
        return [a for a in self.alerts if a.kind == "detour" and a.visible_at(when)]


# ===================================================================== servizio sospeso -> GTFS
def suspended_dates(alert: Alert, tz: ZoneInfo) -> list[date]:
    """Giorni interi coperti da un avviso di servizio sospeso (dal giorno di inizio a quello di fine)."""
    if alert.kind != "service_suspended" or alert.ends_at is None:
        return []
    first = alert.starts_at.astimezone(tz).date()
    last = (alert.ends_at - timedelta(seconds=1)).astimezone(tz).date()
    return [first + timedelta(days=k) for k in range((last - first).days + 1)]


def apply_suspensions(src: dict, alerts: list[Alert], tz: ZoneInfo) -> dict:
    """Copia delle sorgenti con i giorni di servizio sospeso come eccezioni (tipo 2) dei calendari interessati."""
    out = copy.deepcopy(src)
    lines = out["percorsi"]["linee"]
    calendars = {c["service_id"]: c for c in out["percorsi"]["calendar"]}
    for alert in alerts:
        days = suspended_dates(alert, tz)
        if not days:
            continue
        services = {line["service_id"] for line in lines if alert.applies_to_route(line["route_id"])}
        for service_id in services:
            calendar = calendars.get(service_id)
            if calendar is None:
                continue
            exceptions = {e["data"]: e for e in calendar.setdefault("eccezioni", [])}
            for d in days:
                exceptions[d.strftime("%Y%m%d")] = {"data": d.strftime("%Y%m%d"), "tipo": 2}
            calendar["eccezioni"] = sorted(exceptions.values(), key=lambda e: e["data"])
    return out
