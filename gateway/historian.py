"""historian.py — Écoute MQTT, archive tout dans SQLite,
garde la dernière valeur de chaque topic en mémoire (cache LATEST).
Pattern d'un historian industriel : cache O(1) pour le temps réel,
SQL pour l'historique."""

import json
import sqlite3
import threading
from datetime import datetime, timedelta

import paho.mqtt.client as mqtt

DB = sqlite3.connect("historian.db", check_same_thread=False)
DB.execute("""CREATE TABLE IF NOT EXISTS telemetry(
    ts TEXT, topic TEXT, payload TEXT)""")
DB.execute("CREATE INDEX IF NOT EXISTS idx_topic_ts ON telemetry(topic, ts)")
DB.execute("""CREATE TABLE IF NOT EXISTS alarms(
    id TEXT PRIMARY KEY, ts TEXT, equipment TEXT,
    severity TEXT, message TEXT, active INTEGER)""")
LOCK = threading.Lock()

# Cache mémoire : dernière valeur connue de chaque topic
LATEST = {}
# Heure réelle de la dernière réception par topic (pour la détection de perte de com)
LAST_SEEN = {}

_insert_count = 0


def on_message(client, userdata, msg):
    global _insert_count
    try:
        payload = json.loads(msg.payload)
    except json.JSONDecodeError:
        return
    with LOCK:
        LATEST[msg.topic] = payload
        LAST_SEEN[msg.topic] = datetime.now()
        DB.execute("INSERT INTO telemetry VALUES (?,?,?)",
                   (payload.get("ts"), msg.topic, msg.payload.decode()))
        _insert_count += 1
        if _insert_count % 500 == 0:   # commit par paquets (perf)
            DB.commit()


def start():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_message = on_message
    client.connect("localhost", 1883)
    client.subscribe("solartwin/#")
    client.loop_start()
    return client


def sim_now():
    """Heure simulée courante = dernier ts reçu de la station météo."""
    w = LATEST.get("solartwin/WST01/telemetry")
    return datetime.fromisoformat(w["ts"]) if w else None


def energy_today():
    """Énergie du jour simulé (kWh), intégrée depuis l'historique des onduleurs."""
    t = sim_now()
    if t is None:
        return 0.0
    day_start = t.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    with LOCK:
        rows = DB.execute(
            """SELECT payload FROM telemetry
               WHERE topic LIKE 'solartwin/INV0_/telemetry' AND ts >= ?""",
            (day_start,)).fetchall()
    # Chaque échantillon couvre ~60 s simulées (1 s réelle x TIME_SCALE)
    kwh = sum(json.loads(r[0]).get("p_ac_kw", 0) for r in rows) * 60 / 3600
    return round(kwh, 1)


if __name__ == "__main__":
    import time
    start()
    print("Historian démarré — Ctrl+C pour arrêter.")
    while True:
        time.sleep(5)
        with LOCK:
            n = DB.execute("SELECT COUNT(*) FROM telemetry").fetchone()[0]
        w = LATEST.get("solartwin/WST01/telemetry", {})
        print(f"{n} lignes | topics: {len(LATEST)} | "
              f"heure sim: {w.get('ts', '—')} | POA: {w.get('poa', '—')}")