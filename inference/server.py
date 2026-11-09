"""Server di inferenza di QuandoPassa, OpenAI-compatibile.

Endpoint:
  GET  /health                 stato e backend attivo
  GET  /v1/models              elenco modelli (formato OpenAI)
  POST /v1/chat/completions    chat (formato OpenAI): proxy verso l'LLM o risposta deterministica
  POST /v1/tasks/intent        frase -> {intento, luogo, linea, ora}
  POST /v1/tasks/answer        dati calcolati dall'app + bozza -> risposta in italiano semplice
  POST /v1/tasks/faq           domanda + documenti -> risposta fondata solo sui documenti
  POST /v1/tasks/summary       recensioni -> sintesi in 2-3 frasi

Backend (INFERENCE_BACKEND):
  rules   (predefinito) deterministico, offline, nessun dato esce dal container
  openai  endpoint OpenAI-compatibile: Ollama, vLLM, llama.cpp, Azure OpenAI, Anthropic (compat.)

Garanzie (AI Act art. 50, L. 132/2025, Linee guida AgID):
  - l'IA capisce e riformula, ma orari e minuti li calcola l'app dall'orario GTFS;
  - una riformulazione che cambia numeri o orari viene scartata a favore della bozza;
  - i dati personali sono rimossi prima di ogni invio all'LLM;
  - ogni risposta dichiara `generato_da_ia` e il backend usato.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import rules

log = logging.getLogger("inference")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")

BACKEND = os.getenv("INFERENCE_BACKEND", "rules").lower()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://ollama:11434/v1").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:1.5b-instruct")
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "20"))

app = FastAPI(title="QuandoPassa – inference server", version="0.1.0")

_PII = [
    (re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b", re.I), "[CODICE_FISCALE]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL]"),
    (re.compile(r"(?:\+39\s?)?\b3\d{2}[\s.]?\d{6,7}\b|\b0\d{1,3}[\s.]?\d{5,8}\b"), "[TELEFONO]"),
]


def redigi(testo: str) -> str:
    for rx, sost in _PII:
        testo = rx.sub(sost, testo)
    return testo


class IntentIn(BaseModel):
    testo: str = Field(..., min_length=1, max_length=500)


class AnswerIn(BaseModel):
    domanda: str = Field(..., min_length=1, max_length=500)
    intento: str
    dati: dict = Field(default_factory=dict)
    bozza: str = Field(..., min_length=1, max_length=2000)


class Documento(BaseModel):
    id: str
    titolo: str
    testo: str


class FaqIn(BaseModel):
    domanda: str = Field(..., min_length=2, max_length=500)
    documenti: list[Documento] = Field(..., min_length=1, max_length=50)


class Recensione(BaseModel):
    voto: int = Field(..., ge=1, le=5)
    testo: str = ""
    tag: list[str] = Field(default_factory=list)


class SummaryIn(BaseModel):
    oggetto: str = Field(..., min_length=1, max_length=200)
    recensioni: list[Recensione] = Field(..., max_length=100)


class Messaggio(BaseModel):
    role: str
    content: str


class ChatIn(BaseModel):
    model: str | None = None
    messages: list[Messaggio]
    temperature: float | None = 0.0
    max_tokens: int | None = 400


def _llm(messaggi: list[dict], json_mode: bool = False, max_tokens: int = 300) -> str:
    corpo = {"model": LLM_MODEL, "messages": messaggi, "temperature": 0, "max_tokens": max_tokens}
    if json_mode:
        corpo["response_format"] = {"type": "json_object"}
    r = httpx.post(f"{LLM_BASE_URL}/chat/completions", json=corpo, timeout=LLM_TIMEOUT,
                   headers={"Authorization": f"Bearer {LLM_API_KEY}"})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


PROMPT_INTENT = (
    "Sei il parser dell'assistente del bus urbano di un piccolo Comune italiano. Dalla frase estrai un JSON con: "
    "intento (vicina|prossimo|dove_bus|percorso|orari_linea|recensioni|info|sconosciuto), "
    "luogo (nome di fermata, via o luogo citato, o null), linea (lettera maiuscola o null), "
    "ora (HH:MM o null). Rispondi solo con JSON valido."
)
PROMPT_ANSWER = (
    "Sei l'assistente del bus urbano. Riscrivi la BOZZA in italiano semplice e cordiale, massimo 3 frasi. "
    "Usa SOLO i fatti della bozza e dei dati: non cambiare, aggiungere o arrotondare orari, minuti, distanze, "
    "nomi di fermate o linee. Non aggiungere saluti."
)
PROMPT_FAQ = (
    "Sei l'assistente del bus urbano del Comune. Rispondi in italiano semplice, massimo 3 frasi, usando SOLO i "
    "documenti forniti. Se la risposta non c'è, rispondi esattamente: NON_PRESENTE. Non inventare tariffe o orari."
)
PROMPT_SUMMARY = (
    "Riassumi in massimo 3 frasi neutre le recensioni dei cittadini su una fermata o linea del bus urbano: "
    "giudizio complessivo, punti di forza, criticità ricorrenti. Non citare persone, non inventare fatti, "
    "ignora insulti e dati personali."
)

_NUMERI = re.compile(r"\d{1,2}[:.]\d{2}|\d+")


def _stessi_numeri(bozza: str, testo: str) -> bool:
    """La riformulazione non deve introdurre numeri nuovi né perdere gli orari della bozza."""
    def norm(s):
        return {x.replace(".", ":") for x in _NUMERI.findall(s)}
    orari_bozza = {x for x in norm(bozza) if ":" in x}
    return norm(testo) <= norm(bozza) and orari_bozza <= norm(testo)


@app.get("/health")
def health():
    return {"stato": "ok", "backend": BACKEND, "modello": LLM_MODEL if BACKEND == "openai" else "rules-it-tpl-v1"}


@app.get("/v1/models")
def models():
    nome = LLM_MODEL if BACKEND == "openai" else "rules-it-tpl-v1"
    return {"object": "list", "data": [{"id": nome, "object": "model", "owned_by": "comune"}]}


@app.post("/v1/tasks/intent")
def intent(body: IntentIn):
    base = rules.estrai_intento(body.testo)
    usato = "rules"
    if BACKEND == "openai" and base["confidenza"] < 1.0:
        try:
            llm = json.loads(_llm([{"role": "system", "content": PROMPT_INTENT},
                                   {"role": "user", "content": redigi(body.testo)}], json_mode=True, max_tokens=120))
            # l'LLM completa, il codice valida
            if base["intento"] == "sconosciuto" and llm.get("intento") in rules.INTENTI:
                base["intento"] = llm["intento"]
            if not base["luogo"] and isinstance(llm.get("luogo"), str) and 2 < len(llm["luogo"]) < 80:
                base["luogo"] = llm["luogo"].strip()
            if not base["linea"] and isinstance(llm.get("linea"), str) and re.fullmatch(r"[A-Z]", llm["linea"]):
                base["linea"] = llm["linea"]
            if not base["ora"] and isinstance(llm.get("ora"), str) and re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", llm["ora"]):
                base["ora"] = llm["ora"]
            usato = f"openai:{LLM_MODEL}"
        except Exception as e:  # noqa: BLE001 - degrado controllato
            log.warning("LLM intent non disponibile: %s", e)
    return {**base, "backend": usato, "generato_da_ia": usato != "rules"}


@app.post("/v1/tasks/answer")
def answer(body: AnswerIn):
    if BACKEND != "openai":
        return {"risposta": body.bozza, "backend": "rules", "generato_da_ia": False}
    try:
        testo = _llm([{"role": "system", "content": PROMPT_ANSWER},
                      {"role": "user", "content": f"Domanda: {redigi(body.domanda)}\nBOZZA: {body.bozza}\n"
                                                  f"DATI: {json.dumps(body.dati, ensure_ascii=False)[:3000]}"}]).strip()
        if testo and _stessi_numeri(body.bozza, testo):
            return {"risposta": testo, "backend": f"openai:{LLM_MODEL}", "generato_da_ia": True}
        log.info("riformulazione scartata: numeri diversi dalla bozza")
    except Exception as e:  # noqa: BLE001
        log.warning("LLM answer non disponibile: %s", e)
    return {"risposta": body.bozza, "backend": "rules", "generato_da_ia": False}


@app.post("/v1/tasks/faq")
def faq(body: FaqIn):
    docs = [d.model_dump() for d in body.documenti]
    base = rules.rispondi_faq(body.domanda, docs)
    if BACKEND != "openai":
        return {**base, "backend": "rules", "generato_da_ia": False}
    top = [d for _, d in rules.classifica(body.domanda, docs, k=3)] or docs[:3]
    contesto = "\n\n".join(f"[{d['id']}] {d['titolo']}\n{d['testo']}" for d in top)
    try:
        testo = _llm([{"role": "system", "content": PROMPT_FAQ},
                      {"role": "user", "content": f"Documenti:\n{contesto}\n\nDomanda: {redigi(body.domanda)}"}])
        if "NON_PRESENTE" in testo:
            return {"risposta": None, "fonti": [], "trovata": False, "backend": f"openai:{LLM_MODEL}", "generato_da_ia": True}
        return {"risposta": testo.strip(), "fonti": [d["id"] for d in top], "trovata": True,
                "backend": f"openai:{LLM_MODEL}", "generato_da_ia": True}
    except Exception as e:  # noqa: BLE001
        log.warning("LLM faq non disponibile: %s", e)
        return {**base, "backend": "rules", "generato_da_ia": False}


@app.post("/v1/tasks/summary")
def summary(body: SummaryIn):
    recensioni = [r.model_dump() for r in body.recensioni]
    base = rules.sintesi_recensioni(body.oggetto, recensioni)
    if BACKEND != "openai" or len(recensioni) < 3 or not any(r["testo"].strip() for r in recensioni):
        return {"sintesi": base, "backend": "rules", "generato_da_ia": False}
    elenco = "\n".join(f"- {r['voto']}/5 [{', '.join(r['tag'])}] {redigi(r['testo'])[:300]}" for r in recensioni[:30])
    try:
        testo = _llm([{"role": "system", "content": PROMPT_SUMMARY},
                      {"role": "user", "content": f"Oggetto: {body.oggetto}\nRecensioni:\n{elenco}"}], max_tokens=200)
        return {"sintesi": testo.strip(), "statistiche": base, "backend": f"openai:{LLM_MODEL}", "generato_da_ia": True}
    except Exception as e:  # noqa: BLE001
        log.warning("LLM summary non disponibile: %s", e)
        return {"sintesi": base, "backend": "rules", "generato_da_ia": False}


@app.post("/v1/chat/completions")
def chat(body: ChatIn):
    messaggi = [{"role": m.role, "content": redigi(m.content)} for m in body.messages]
    if BACKEND == "openai":
        try:
            contenuto = _llm(messaggi, max_tokens=body.max_tokens or 400)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(503, f"LLM non disponibile: {e}") from e
        modello = LLM_MODEL
    else:
        ultimo = next((m["content"] for m in reversed(messaggi) if m["role"] == "user"), "")
        contenuto = json.dumps(rules.estrai_intento(ultimo), ensure_ascii=False)
        modello = "rules-it-tpl-v1"
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}", "object": "chat.completion", "created": int(time.time()),
        "model": modello,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": contenuto}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
