# app.py - Yarrow-AI-Server v3 (FastAPI + SQLite + WS)
# lancer: uvicorn app:app --reload --host 0.0.0.0 --port 8080

import sqlite3, os, time, math, random, asyncio
from datetime import datetime, timedelta
from typing import Dict, Literal, Optional, List
from fastapi import FastAPI, WebSocket, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DB_PATH = os.environ.get("YARROW_DB", "yarrow_ai.db")
API_TOKEN = os.environ.get("YARROW_TOKEN", "changeme")

app = FastAPI(title="Yarrow-AI-Server v3")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def db():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

CON = db()
CON.execute("""CREATE TABLE IF NOT EXISTS telemetry(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL, ph REAL, ec REAL, air_t REAL, water_level REAL, root_t REAL
);""")
CON.execute("""CREATE TABLE IF NOT EXISTS actions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL, kind TEXT, payload TEXT, source TEXT, status TEXT
);""")
CON.commit()

Cult = Literal["cannabis","fraise","tomate","laitue"]
Phase = Literal["semis","croissance","floraison","standard"]
PROFILS: Dict[Cult, Dict[Phase, Dict[str, float]]] = {
    "cannabis": {
        "semis": {"ph": 5.9, "ec": 0.8},
        "croissance": {"ph": 6.0, "ec": 1.6},
        "floraison": {"ph": 5.8, "ec": 2.2},
    },
    "fraise": {"standard": {"ph": 6.0, "ec": 1.6}},
    "tomate": {"croissance": {"ph": 6.0, "ec": 2.0}, "floraison": {"ph": 5.8, "ec": 2.3}},
    "laitue": {"standard": {"ph": 6.1, "ec": 1.2}},
}

LIMITES = {"ph": {"min":4.8,"max":7.5}, "ec":{"min":0.2,"max":3.0}, "air_t":{"min":12,"max":36}}
COOLDOWNS_MIN = {"ph":30, "ec":20}
PH_STEP, EC_STEP = 0.15, 0.2

STATE = {"culture":"cannabis", "phase":"floraison", "last_ph_action": datetime.min, "last_ec_action": datetime.min}

class TelemetryUpload(BaseModel):
    ph: float = Field(..., ge=4.0, le=8.0)
    ec: float = Field(..., ge=0.0, le=5.0)
    air_t: float
    water_level: float = Field(..., ge=0.0, le=1.0)
    root_t: Optional[float] = None

class TelemetryOut(BaseModel):
    ts: float; ph: float; ec: float; air_t: float; water_level: float; root_t: Optional[float]=None

class ProfileUpdate(BaseModel):
    culture: Cult; phase: Phase

class Decision(BaseModel):
    status_global: Literal["Optimal","Attention","Alerte"]
    culture_cible: Cult; phase: Phase
    reco_action: str
    data_environnement: Dict[str, float]
    justification_ia: str
    suggestion_cmd: Optional[Dict] = None

_raw = dict(ph=6.9, ec=1.5, air_t=24.3, water_level=0.72, root_t=22.5)

def _step(dt=1.0):
    t = time.time()
    _raw["air_t"] += (24.0 - _raw["air_t"])*0.02*dt + 0.05*math.sin(t/30)
    _raw["ph"]    += (6.10 - _raw["ph"])*0.04*dt + (random.random()-0.5)*0.01
    _raw["ec"]    += (1.60 - _raw["ec"])*0.03*dt + (random.random()-0.5)*0.01
    _raw["water_level"] = max(0.15, _raw["water_level"] - 0.0004*dt)

def snapshot() -> TelemetryOut:
    return TelemetryOut(ts=time.time(), ph=round(_raw["ph"],2), ec=round(_raw["ec"],2),
                        air_t=round(_raw["air_t"],2), water_level=round(_raw["water_level"],2),
                        root_t=round(_raw.get("root_t",22.0),2))

def _auth(token: Optional[str]):
    if not token or token != f"Bearer {API_TOKEN}":
        raise HTTPException(401, "Unauthorized")

def calc_ph_dose(ph_actuel: float, ph_cible: float, step: float) -> float:
    delta = min(step, max(0.05, abs(ph_actuel - ph_cible)))
    return round(2.0 * (delta/step), 1)

def calc_ec_dose(ec_actuel: float, ec_cible: float, step: float) -> float:
    delta = min(step, max(0.1, ec_cible - ec_actuel))
    return round(5.0 * (delta/step), 1)

def decision_engine(t: TelemetryOut) -> Decision:
    culture, phase = STATE["culture"], STATE["phase"]
    profil = PROFILS[culture][phase if phase in PROFILS[culture] else "standard"]
    ph_target, ec_target = profil["ph"], profil["ec"]

    status, reco, justifs, cmd = "Optimal", [], [], None
    now = datetime.now()
    since_ph = (now - STATE["last_ph_action"]).total_seconds()/60
    since_ec = (now - STATE["last_ec_action"]).total_seconds()/60

    if t.ph > ph_target + 0.4:
        if since_ph < COOLDOWNS_MIN["ph"]:
            status="Attention"; reco.append("Attente stabilisation pH")
            justifs.append(f"pH↑ corr. récente ({int(since_ph)} min)")
        else:
            status="Attention"; reco.append(f"Micro-dosing pH Down (~{PH_STEP})")
            justifs.append(f"pH {t.ph} > cible {ph_target}. Step progressif.")
            cmd = {"target":"pump_acid","action":"dose","params":{"ml": calc_ph_dose(t.ph, ph_target, PH_STEP)}}

    if t.ec < ec_target - 0.4:
        if since_ec < COOLDOWNS_MIN["ec"]:
            status="Attention"; reco.append("Reporter nutriments (cooldown)")
        else:
            status="Attention"; reco.append(f"Nutri+ (ΔEC ~ {EC_STEP})")
            cmd = {"target":"pump_nutrients","action":"dose","params":{"ml": calc_ec_dose(t.ec, ec_target, EC_STEP)}}

    if t.air_t > 30.0:
        status="Alerte"; reco.append("Ventilation max / baisser LED")
        if cmd is None: cmd = {"target":"fan","action":"on","params":{"pwm":255,"seconds":120}}

    if not reco:
        reco.append("Routine stable"); justifs.append("Paramètres OK")

    return Decision(
        status_global=status, culture_cible=culture, phase=phase,
        reco_action=" + ".join(reco),
        data_environnement={"ph_actuel":t.ph,"ph_cible_reco":ph_target,"ec_actuel":t.ec,"ec_cible_reco":ec_target,"temp_air":t.air_t,"temp_racine":t.root_t or 22.0,"niveau_eau":t.water_level},
        justification_ia=" | ".join(justifs),
        suggestion_cmd=cmd
    )

@app.get("/api/v1/live_data", response_model=Decision)
def live_data():
    _step(1.0)
    t = snapshot()
    return decision_engine(t)

@app.websocket("/ws")
async def ws_stream(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            _step(1.0)
            t = snapshot()
            dec = decision_engine(t)
            await ws.send_json(dec.model_dump())
            await asyncio.sleep(1.0)
    except Exception:
        await ws.close()
