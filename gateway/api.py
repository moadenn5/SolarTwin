"""api.py — L'API REST que consommera Unreal (VaRest).
Lance historian + alerts dans le même processus, puis sert le tout en HTTP."""

import json
from datetime import timedelta

from fastapi import FastAPI

import historian
import alerts

historian.start()
alerts.start()

app = FastAPI(title="SolarTwin Gateway")


@app.get("/plant/summary")
def plant_summary():
    invs = {k: v for k, v in historian.LATEST.items()
            if "/INV" in k and "STR" not in k}
    total_kw = sum(v.get("p_ac_kw", 0) for v in invs.values())
    weather = historian.LATEST.get("solartwin/WST01/telemetry", {})
    return {
        "ts": weather.get("ts"),
        "p_pv_kw": round(total_kw, 1),
        "p_grid_kw": round(total_kw, 1),   # == PV en V1 ; divergera avec le BESS en V2
        "poa": weather.get("poa"),
        "t_amb": weather.get("t_amb"),
        "wind": weather.get("wind"),
        "cloud_factor": weather.get("cloud_factor"),
        "sun_elevation": weather.get("sun_elevation"),
        "sun_azimuth": weather.get("sun_azimuth"),
        "active_alarms": alerts.count_active(),
        "energy_today_kwh": historian.energy_today(),
    }


@app.get("/strings/live")
def strings_live():
    """Payload compact pour colorer 480 tables d'un coup dans Unreal."""
    out = []
    for topic, v in historian.LATEST.items():
        if "-STR" in topic:
            sid = topic.split("/")[2]
            out.append({"id": sid,
                        "p": v.get("p_dc_w", 0),
                        "q": v.get("quality", "GOOD"),
                        "st": alerts.status_of(sid)})
    return {"strings": out}


@app.get("/string/{sid}")
def string_detail(sid: str):
    inv = sid.split("-")[0]
    v = historian.LATEST.get(f"solartwin/{inv}/{sid}/telemetry")
    return v or {"error": "unknown string"}


@app.get("/inverter/{iid}")
def inverter_detail(iid: str):
    v = historian.LATEST.get(f"solartwin/{iid}/telemetry")
    return v or {"error": "unknown inverter"}


@app.get("/alarms")
def alarms(active_only: bool = True):
    if active_only:
        return {"alarms": alerts.active_list()}
    with historian.LOCK:
        rows = historian.DB.execute(
            "SELECT id, ts, equipment, severity, message, active "
            "FROM alarms ORDER BY ts DESC LIMIT 200").fetchall()
    return {"alarms": [dict(zip(
        ("id", "ts", "equipment", "severity", "message", "active"), r))
        for r in rows]}


@app.get("/history")
def history(tag: str = "INV01", minutes: int = 60, step_s: int = 60):
    """Ex: /history?tag=INV01&minutes=180 -> points pour le graphique UMG."""
    t = historian.sim_now()
    if t is None:
        return {"points": []}
    start_iso = (t - timedelta(minutes=minutes)).isoformat()
    with historian.LOCK:
        rows = historian.DB.execute(
            "SELECT ts, payload FROM telemetry "
            "WHERE topic = ? AND ts >= ? ORDER BY ts",
            (f"solartwin/{tag}/telemetry", start_iso)).fetchall()
    points, last_ts = [], None
    for ts, payload in rows:
        if last_ts is None or ts[:16] != last_ts:   # ~1 point / minute simulée
            p = json.loads(payload)
            points.append({"ts": ts, "v": p.get("p_ac_kw", p.get("p_dc_w", 0))})
            last_ts = ts[:16]
    return {"tag": tag, "points": points}