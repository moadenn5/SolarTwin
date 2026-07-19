"""test_sensors.py — Valide le comportement du capteur virtuel."""
import statistics
from sensors import VirtualSensor

# 1. Bruit : 200 lectures d'une vraie valeur de 800 W/m²
s = VirtualSensor("WST01-POA", "W/m2", noise_pct=2.0, resolution=0.1,
                  range_max=1500, sample_period_s=0)
readings = [s.read(800.0, now=i)[0] for i in range(200)]
mean, std = statistics.mean(readings), statistics.stdev(readings)
print(f"Moyenne {mean:.1f} (attendu ~800), écart-type {std:.1f} (attendu ~16)")
assert 790 < mean < 810
assert 10 < std < 25

# 2. Qualité GOOD en fonctionnement normal
_, q = s.read(800.0, now=999)
assert q == "GOOD", q

# 3. Saturation : valeur hors plage -> UNCERTAIN
val, q = s.read(2000.0, now=1000)
assert val == 1500 and q == "UNCERTAIN", (val, q)

# 4. Panne "stuck"
s.fail("stuck", stuck_value=612.3)
val, q = s.read(450.0, now=1001)
assert val == 612.3 and q == "UNCERTAIN", (val, q)

# 5. Panne "nan"
s.fail("nan")
val, q = s.read(450.0, now=1002)
assert val is None and q == "BAD", (val, q)

# 6. Réparation
s.repair()
val, q = s.read(450.0, now=1003)
assert q == "GOOD" and 430 < val < 470, (val, q)

# 7. Fréquence d'échantillonnage : un capteur 5 s renvoie la même valeur entre deux ticks
slow = VirtualSensor("WST01-TAMB", "C", noise_pct=1.0, sample_period_s=5)
v1, _ = slow.read(25.0, now=100)
v2, _ = slow.read(30.0, now=102)   # 2 s plus tard -> pas de nouvel échantillon
v3, _ = slow.read(30.0, now=106)   # 6 s plus tard -> nouvel échantillon
assert v1 == v2 and v3 != v2, (v1, v2, v3)

print("OK — VirtualSensor validé.")