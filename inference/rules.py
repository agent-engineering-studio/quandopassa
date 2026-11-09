"""Backend deterministico (nessun modello): intenti in italiano sul bus urbano e FAQ.

È il backend predefinito: gira ovunque, non invia dati a terzi e rende i test riproducibili.
Un LLM, se configurato, interviene solo quando le regole non bastano e viene comunque
validato da questo modulo.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

INTENTI = ("vicina", "prossimo", "dove_bus", "percorso", "orari_linea", "info", "sconosciuto")
STOP = set("il lo la i gli le un una di a da in con su per tra fra e o che non si ci mi ti come quanto quanti "
           "quando dove cosa qual quale e sono del della dei delle al alla ai alle nel nella posso devo "
           "voglio vorrei serve servono mio mia".split())
NUMERI = {"una": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7, "otto": 8, "nove": 9,
          "dieci": 10, "undici": 11, "dodici": 12, "mezzogiorno": 12}


def normalizza(testo: str) -> str:
    t = unicodedata.normalize("NFKD", testo.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("’", "'")
    return re.sub(r"\s+", " ", t).strip()


def _linea(t: str) -> str | None:
    m = re.search(r"\b(?:linea|circolare)\s+([a-z])\b", t)
    if m:
        return m.group(1).upper()
    m = re.search(r"\b(?:bus|autobus|navetta|la|il)\s+([bcdfgh])\b(?!')", t)
    return m.group(1).upper() if m else None


def _ora(t: str) -> str | None:
    m = re.search(r"\b(?:alle|ore|verso le|per le|dopo le)\s*(\d{1,2})(?:[:.](\d{2}))?\b", t)
    if m:
        h, mm = int(m.group(1)), int(m.group(2) or 0)
    else:
        m = re.search(r"\b(?:alle|ore|verso le|per le|dopo le)\s+(" + "|".join(NUMERI) + r")\b", t)
        if not m:
            return None
        h, mm = NUMERI[m.group(1)], 0
    if re.search(r"\b(pomeriggio|sera|stasera)\b", t) and h < 12:
        h += 12
    if 0 <= h <= 23 and 0 <= mm <= 59:
        return f"{h:02d}:{mm:02d}"
    return None


_LUOGO_DOPO = (r"(?:arrivo|arrivare|andare|vado|porta(?:mi)?|raggiungo|raggiungere|per|verso|fino)\s+"
               r"(?:(?:alla|allo|alle|al|ai|a|in|presso|fino a|verso)\s+|all')?(.+)")
_LUOGO_FERMATA = r"(?:fermata|fermate|passa(?:no)?|parte|partono|arriva|arrivano|bus|autobus)\s+(?:di|da|a|in|per|del|della|dello|dal|dalla|al|alla|all')\s+(.+)"
_PULISCI = re.compile(r"\b(?:prossimo|prossima|bus|autobus|linea [a-z]|circolare [a-z]|oggi|domani|adesso|ora|"
                      r"alle \d{1,2}(?:[:.]\d{2})?|per favore|grazie|la fermata|fermata)\b")


def _luogo(t: str, schema: str) -> str | None:
    m = re.search(schema, t)
    if not m:
        return None
    luogo = re.split(r"[?!.,;]| alle \d| e poi | con il | con la ", m.group(1))[0]
    luogo = _PULISCI.sub(" ", luogo)
    luogo = re.sub(r"^(?:a|al|alla|allo|ai|alle|in|di|da|del|della|dal|dalla|il|la|lo|l')\s+", "", luogo.strip())
    luogo = re.sub(r"\s+", " ", luogo).strip(" '")
    return luogo if len(luogo) >= 3 and luogo not in STOP else None


def estrai_intento(testo: str) -> dict:
    t = normalizza(testo)
    out = {"intento": "sconosciuto", "luogo": None, "linea": _linea(t), "ora": _ora(t), "confidenza": 0.0}
    if re.search(r"\b(piu vicin|vicino a me|qui vicino|vicino casa|intorno a me|fermata vicina|dove prendo)", t):
        out["intento"] = "vicina"
    elif re.search(r"\b(come (?:arrivo|ci arrivo|vado|raggiungo|faccio ad andare)|per andare|devo andare|"
                   r"voglio andare|portami|che bus prendo|quale bus|come si arriva|arrivare a|andare a)\b", t):
        out["intento"] = "percorso"
        out["luogo"] = _luogo(t, _LUOGO_DOPO)
    elif re.search(r"\b(dov'? ?e|dove si trova|dove sta|dove e|a che punto|posizione)\b.*\b(bus|autobus|linea|"
                   r"circolare|navetta|pullman)\b|\bdove (?:sono|stanno) (?:i|gli) (?:bus|autobus)", t):
        out["intento"] = "dove_bus"
    elif re.search(r"\b(orari|orario|tabella|a che ora (?:parte|inizia|finisce)|prima corsa|ultima corsa|"
                   r"quante corse|frequenza)\b", t) and (out["linea"] or re.search(r"\b(linea|circolare|linee)\b", t)):
        out["intento"] = "orari_linea"
    elif re.search(r"\b(quando passa|quando arriva|prossim[oa]|a che ora passa|passa il|tra quanto|quando parte|"
                   r"che ora passa|fra quanto|orari della fermata|orari fermata|parte il)\b", t):
        out["intento"] = "prossimo"
        out["luogo"] = _luogo(t, _LUOGO_FERMATA) or _luogo(t, r".*\b(?:da|dalla|dal|a|alla|al|in)\s+(.+)")
    elif re.search(r"\b(biglietto|costa|prezzo|tariff|abbonament|domenica|festiv|telefono|contatt|gps|"
                   r"privacy|reclam|smarrit|pensilin|ritardo)", t):
        out["intento"] = "info"
    segnali = (out["intento"] != "sconosciuto") + bool(out["luogo"]) + bool(out["linea"] or out["ora"])
    out["confidenza"] = round(min(1.0, segnali / 2), 2)
    return out


# ---------------------------------------------------------------- FAQ / retrieval (BM25 compatto)
def _token(t: str) -> list[str]:
    parole = re.findall(r"[a-z0-9]+", normalizza(t))
    return [(re.sub(r"[aeiou]$", "", p) if len(p) > 4 else p)[:6] for p in parole if p not in STOP and len(p) > 1]


def classifica(domanda: str, documenti: list[dict], k: int = 3) -> list[tuple[float, dict]]:
    docs = [(_token(d.get("titolo", "") * 2 + " " + d.get("titolo", "") + " " + d.get("testo", "")), d)
            for d in documenti]
    if not docs:
        return []
    n = len(docs)
    avgdl = sum(len(t) for t, _ in docs) / n or 1
    df = Counter(w for t, _ in docs for w in set(t))
    q = _token(domanda)
    k1, b = 1.4, 0.75
    risultati = []
    for toks, d in docs:
        tf = Counter(toks)
        s = 0.0
        for w in q:
            if w in tf:
                idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * len(toks) / avgdl))
        risultati.append((s, d))
    risultati.sort(key=lambda x: x[0], reverse=True)
    return [r for r in risultati[:k] if r[0] > 0.5]


def rispondi_faq(domanda: str, documenti: list[dict]) -> dict:
    top = classifica(domanda, documenti, k=2)
    if not top:
        return {"risposta": None, "fonti": [], "trovata": False}
    return {"risposta": top[0][1]["testo"], "fonti": [top[0][1]["id"]], "trovata": True}
