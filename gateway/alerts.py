"""alerts.py — Moteur d'alarmes : compare le cache LATEST aux seuils
toutes les 5 secondes. Règle clé : sous-performance vs médiane des pairs
(la vraie méthode du monitoring PV)."""

import itertools
import statistics
import threading
import time
from datetime import datetime

import historian

# Alarmes actives et historiques : {(rule, equipment): alarm_dict}
ALARMS = {}
_counter = itertools.count(1)
_first_seen = {}      # (rule, equipment) -> heure réelle de 1re détection
LOCK = threading.Lock()

UNDERPERF_HOLD_S = 30   # 30 s réelles = 30 min simulées à x60 (> "5 min" du cahier des charges)


def _raise(rule, equipment, severity, message):
    key = (rule, equipment)
    with LOCK:
        if key in ALARMS and ALARMS[key]["active"]:
            return
        alm = {"id": f"ALM-{next(_counter):04d}",
               "ts": (historian.sim_now() or datetime.now()).isoformat(),
               "equipment": equipment, "severity": severity,
               "message": message, "active": True}
        ALARMS[key] = alm
        historian.DB.execute(
            "INSERT OR REPLACE INTO alarms VALUES (?,?,?,?,?,1)",
            (alm["id"], alm["ts"], equipment, severity, message))
        print(f"[{severity}] {equipment}: {message}")


def _clear(rule, equipment):
    key = (rule, equipment)
    with LOCK:
        if key in ALARMS and ALARMS[key]["active"]:
            ALARMS[key]["active"] = False
            historian.DB.execute("UPDATE alarms SET active=0 WHERE id=?",
                                 (ALARMS[key]["id"],))
            print(f"[CLEAR] {equipment}")
    _first_seen.pop(key, None)


def check():
    now_real = time.time()
    weather = historian.LATEST.get("solartwin/WST01/telemetry", {})
    poa = weather.get("poa") or 0

    # --- Collecte des strings par onduleur ---
    strings = {}          # inv_id -> {sid: payload}
    for topic, v in historian.LATEST.items():
        if "-STR" in topic:
            sid = topic.split("/")[2]
            strings.setdefault(sid.split("-")[0], {})[sid] = (topic, v)

    for inv_id, members in strings.items():
        powers = {sid: (v.get("p_dc_w") or 0) for sid, (t, v) in members.items()}
        med = statistics.median(powers.values()) if powers else 0

        for sid, (topic, v) in members.items():
            # Règle 2 : string mort (CRITICAL)
            if poa > 200 and (v.get("i_dc") or 0) < 0.1:
                _raise("dead", sid, "CRITICAL",
                       "String current ~0 A while POA > 200 W/m2")
            else:
                _clear("dead", sid)

            # Règle 1 : sous-performance vs médiane des pairs (WARNING)
            key = ("underperf", sid)
            if poa > 300 and med > 500 and powers[sid] < 0.8 * med:
                _first_seen.setdefault(key, now_real)
                if now_real - _first_seen[key] > UNDERPERF_HOLD_S:
                    pct = 100 * (1 - powers[sid] / med)
                    _raise("underperf", sid, "WARNING",
                           f"String underperforming: -{pct:.0f}% vs peers")
            else:
                _clear("underperf", sid)

            # Règle 4 : donnée invalide (WARNING)
            if v.get("quality") == "BAD":
                _raise("badqual", sid, "WARNING", "Sensor quality BAD")
            else:
                _clear("badqual", sid)

    # Règle 3 : surchauffe onduleur
    for topic, v in list(historian.LATEST.items()):
        parts = topic.split("/")
        if len(parts) == 3 and parts[1].startswith("INV"):
            t_int = v.get("t_internal") or 0
            if t_int > 85:
                _raise("overheat", parts[1], "CRITICAL", f"Inverter {t_int:.0f} C")
            elif t_int > 75:
                _raise("overheat", parts[1], "WARNING", f"Inverter {t_int:.0f} C")
            else:
                _clear("overheat", parts[1])

    # Règle 5 : perte de communication (> 30 s réelles sans message)
    for topic, seen in list(historian.LAST_SEEN.items()):
        parts = topic.split("/")
        equip = parts[2] if len(parts) == 4 else parts[1]
        if (datetime.now() - seen).total_seconds() > 30:
            _raise("comm", equip, "CRITICAL", "Communication lost")
        else:
            _clear("comm", equip)


# --- API consommée par api.py ---
def count_active():
    with LOCK:
        return sum(1 for a in ALARMS.values() if a["active"])


def active_list():
    with LOCK:
        return [a for a in ALARMS.values() if a["active"]]


def status_of(sid):
    """OK | WARN | CRIT | STALE pour colorer les tables 3D."""
    with LOCK:
        crit = any(ALARMS.get((r, sid), {}).get("active") for r in ("dead",))
        if ALARMS.get(("comm", sid), {}).get("active"):
            return "STALE"
        if crit:
            return "CRIT"
        warn = any(ALARMS.get((r, sid), {}).get("active")
                   for r in ("underperf", "badqual"))
        return "WARN" if warn else "OK"


def start():
    def loop():
        while True:
            try:
                check()
            except Exception as e:
                print("alerts error:", e)
            time.sleep(5)
    threading.Thread(target=loop, daemon=True).start()


if __name__ == "__main__":
    historian.start()
    start()
    print("Moteur d'alertes démarré — Ctrl+C pour arrêter.")
    while True:
        time.sleep(10)
        print(f"Alarmes actives: {count_active()}")