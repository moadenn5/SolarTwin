"""publisher.py — La boucle principale : le "terrain" qui tourne.
Assemble physics + sensors + faults et publie tout sur MQTT."""

import json
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import paho.mqtt.client as mqtt

import physics
import sensors
import faults

CFG = physics.CFG
TZ = ZoneInfo(CFG["plant"]["timezone"])

# --- Horloge simulée : 1 s réelle = TIME_SCALE s simulées ---
TIME_SCALE = 60          # 60 => une journée en 24 min. Mets 1 pour du temps réel.
_start_real = time.time()
#_start_sim = datetime.now(TZ)
_start_sim = datetime.now(TZ).replace(hour=11, minute=0, second=0)


def now_sim():
    if TIME_SCALE == 1:
        return datetime.now(TZ)
    elapsed = (time.time() - _start_real) * TIME_SCALE
    return _start_sim + timedelta(seconds=elapsed)


# --- Construction des capteurs à partir de la config ---
string_ids = [f"{inv['id']}-STR{str(i + 1).zfill(3)}"
              for inv in CFG["inverters"] for i in range(inv["strings"])]
print(f"{len(string_ids)} strings construits.")

current_sensors = {sid: sensors.VirtualSensor(f"{sid}-I", "A", noise_pct=1.0,
                   resolution=0.01, range_max=15) for sid in string_ids}
voltage_sensors = {sid: sensors.VirtualSensor(f"{sid}-V", "V", noise_pct=0.5,
                   resolution=0.1, range_max=1100) for sid in string_ids}
pyranometer = sensors.VirtualSensor("WST01-POA", "W/m2", noise_pct=2.0,
                   resolution=0.1, range_max=1500)
t_amb_sensor = sensors.VirtualSensor("WST01-TAMB", "C", noise_pct=0,
                   resolution=0.1, range_min=-20, range_max=60, sample_period_s=5)

fault_engine = faults.FaultEngine(string_ids)
cloud_engine = faults.CloudEngine(events_per_day=4)

# --- MQTT ---
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect("localhost", 1883)
client.loop_start()


def publish(topic, payload):
    client.publish(f"solartwin/{topic}", json.dumps(payload), qos=0)


# --- Boucle principale : 1 tick par seconde réelle ---
print(f"Simulation démarrée (TIME_SCALE={TIME_SCALE}). Ctrl+C pour arrêter.")
try:
    #fault_engine.kill_string("INV01-STR005", datetime.now(TZ)) #a supprimer
    #pyranometer.fail("stuck", stuck_value=850.0)
  
    while True:
        t = now_sim()
        cloud = cloud_engine.tick(TIME_SCALE)          # dt simulé = TIME_SCALE s
        cond = physics.compute_conditions(t.replace(tzinfo=None), cloud)
        derates = fault_engine.tick(t, string_ids)
        now_s = time.time()

        # Station météo
        poa_meas, poa_q = pyranometer.read(cond["poa"], now_s)
        tamb_meas, tamb_q = t_amb_sensor.read(cond["t_amb"], now_s)
        publish("WST01/telemetry", {
            "ts": t.isoformat(), "poa": poa_meas, "poa_quality": poa_q,
            "ghi": round(cond["ghi"], 1), "t_amb": tamb_meas,
            "wind": round(cond["wind"], 1), "t_cell_model": round(cond["t_cell"], 1),
            "sun_elevation": round(cond["sun_elevation"], 2),
            "sun_azimuth": round(cond["sun_azimuth"], 2),
            "cloud_factor": round(cloud, 2),
        })

        # Strings
        inv_power = {}
        for sid in string_ids:
            pdc = physics.string_dc_power(cond["poa"], cond["t_cell"], derates[sid])
            vmp, imp = physics.string_iv(pdc, cond["poa"])
            i_meas, i_q = current_sensors[sid].read(imp, now_s)
            v_meas, v_q = voltage_sensors[sid].read(vmp, now_s)
            inv_id = sid.split("-")[0]
            inv_power[inv_id] = inv_power.get(inv_id, 0) + (i_meas or 0) * (v_meas or 0)
            publish(f"{inv_id}/{sid}/telemetry", {
                "ts": t.isoformat(), "i_dc": i_meas, "v_dc": v_meas,
                "p_dc_w": round((i_meas or 0) * (v_meas or 0), 0),
                "quality": "BAD" if i_q == "BAD" else i_q,
                "derate_truth": derates[sid],
            })

        # Onduleurs (rendement 98 %, échauffement lié à la charge)
        for inv in CFG["inverters"]:
            p_ac = inv_power.get(inv["id"], 0) * 0.98 / 1000  # kW
            t_inv = cond["t_amb"] + 25 * (p_ac / inv["pac_max_kw"]) + 5
            publish(f"{inv['id']}/telemetry", {
                "ts": t.isoformat(), "p_ac_kw": round(p_ac, 1),
                "t_internal": round(t_inv, 1),
                "status": "RUN" if p_ac > 1 else "STANDBY",
            })

        time.sleep(1)
except KeyboardInterrupt:
    print("Arrêt.")
    client.loop_stop()