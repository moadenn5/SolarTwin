"""test_physics.py — Trace une journée complète pour valider le modèle."""
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import physics

t0 = datetime(2026, 7, 19, 0, 0)

def simulate_day(cloud_factor):
    hours, power, poa_list = [], [], []
    for m in range(0, 24 * 60, 10):
        t = t0 + timedelta(minutes=m)
        cond = physics.compute_conditions(t, cloud_factor)
        pdc = physics.string_dc_power(cond["poa"], cond["t_cell"])
        hours.append(m / 60)
        power.append(pdc / 1000)
        poa_list.append(cond["poa"])
    return hours, power, poa_list

h, p_clear, poa = simulate_day(0.0)
_, p_cloud, _ = simulate_day(0.7)

fig, ax1 = plt.subplots(figsize=(10, 5))
ax1.plot(h, p_clear, "b-", label="Ciel clair")
ax1.plot(h, p_cloud, "b--", label="cloud_factor=0.7")
ax1.set_xlabel("Heure"); ax1.set_ylabel("P string (kW)")
ax1.legend(loc="upper left")
ax2 = ax1.twinx()
ax2.plot(h, poa, "orange", alpha=0.4)
ax2.set_ylabel("POA W/m² (ciel clair)", color="orange")
plt.title("Journée simulée — string 24 panneaux, Ouarzazate")
plt.tight_layout()
plt.show()

# Sanity checks
peak = max(p_clear)
print(f"Pic ciel clair : {peak:.2f} kW (attendu ~8.5-10)")
assert p_clear[0] < 0.01, "La nuit devrait être à 0 !"
assert 7 < peak < 11, "Pic hors plage attendue"
assert max(p_cloud) < peak * 0.6, "Les nuages devraient couper >40%"
print("OK — modèle validé.")