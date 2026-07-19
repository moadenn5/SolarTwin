"""test_faults.py — Valide le moteur de pannes et les nuages."""
from datetime import datetime
from faults import FaultEngine, CloudEngine

ids = ["INV01-STR005", "INV01-STR015", "INV02-STR014", "INV04-STR100"]
fe = FaultEngine(ids)

# 1. Ombrage matinal : à 8h, INV01-STR015 (<= 20) est à 0.7, INV04 non
d = fe.tick(datetime(2026, 7, 19, 8, 0), ids)
assert d["INV01-STR015"] == 0.7 and d["INV04-STR100"] == 1.0, d

# 2. À midi, plus d'ombrage
d = fe.tick(datetime(2026, 7, 19, 12, 0), ids)
assert d["INV01-STR015"] == 1.0, d

# 3. String tué -> derate 0 + événement CRITICAL
fe.kill_string("INV01-STR005", datetime(2026, 7, 19, 12, 0))
d = fe.tick(datetime(2026, 7, 19, 12, 0), ids)
assert d["INV01-STR005"] == 0.0
assert fe.events[-1]["level"] == "CRITICAL"

# 4. Encrassement : après 10 jours simulés, INV02-STR014 a perdu ~2 %
fe2 = FaultEngine(ids)
for _ in range(10):
    fe2.tick(datetime(2026, 7, 19, 12, 0), ids)   # 1 tick = on force 1 jour
    fe2.soiling["INV02-STR014"] += 0.002 - 0.002 / 86400  # simule 1 jour d'accumulation
d = fe2.tick(datetime(2026, 7, 19, 12, 0), ids)
assert 0.97 < d["INV02-STR014"] < 0.99, d["INV02-STR014"]

# 5. Nuages : forcer un événement et vérifier le cycle complet
ce = CloudEngine()
ce.state, ce.target, ce.hold_duration, ce.t_state = "ramp_up", 0.7, 120, 0.0
mid = ce.tick(45)                 # mi-montée
assert 0.30 < mid < 0.40, mid
ce.tick(45)                       # fin de montée
assert ce.state == "hold" and ce.factor == 0.7
ce.tick(120)                      # fin du plateau
assert ce.state == "ramp_down"
ce.tick(90)                       # fin de descente
assert ce.state == "clear" and ce.factor == 0.0

print("OK — FaultEngine et CloudEngine validés.")