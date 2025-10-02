# simulator.py - pushes fake telemetry to server

import os, time, math, random, requests

BASE = os.environ.get("YARROW_URL", "http://127.0.0.1:8080")
TOKEN = os.environ.get("YARROW_TOKEN", "changeme")
HDR  = {"Authorization": f"Bearer {TOKEN}", "Content-Type":"application/json"}

ph, ec, air_t, lvl = 6.9, 1.5, 24.0, 0.75

def step(dt=2.0, tsec=0):
    global ph, ec, air_t, lvl
    air_t += (24.0-air_t)*0.02*dt + 0.03*math.sin(tsec/25)
    ph    += (6.10-ph)*0.04*dt + (random.random()-0.5)*0.02
    ec    += (1.60-ec)*0.03*dt + (random.random()-0.5)*0.02
    lvl   = max(0.15, lvl - 0.0005*dt)
    return dict(ph=round(ph,2), ec=round(ec,2), air_t=round(air_t,2), water_level=round(lvl,2))

if __name__ == "__main__":
    t0 = time.time()
    while True:
        t = time.time()-t0
        data = step(2.0, t)
        try:
            r = requests.post(f"{BASE}/api/v1/telemetry/upload", headers=HDR, json=data, timeout=5)
            print("push", data, "->", r.status_code)
        except Exception as e:
            print("ERR", e)
        time.sleep(2.0)
