"""physics.py — Modèle physique de la centrale (pvlib).
Répond à : « à l'instant t, dans des conditions météo données,
combien produit chaque string ? »"""

import pvlib
import pandas as pd
import numpy as np
import json

with open("plant_config.json") as f:
    CFG = json.load(f)

LOC = pvlib.location.Location(
    latitude=CFG["plant"]["latitude"],
    longitude=CFG["plant"]["longitude"],
    tz=CFG["plant"]["timezone"],
    altitude=CFG["plant"]["altitude"],
)


def compute_conditions(timestamp, cloud_factor=0.0):
    """Retourne irradiance POA, GHI, temp cellule pour un instant donné.
    cloud_factor : 0 = ciel clair, 1 = totalement couvert."""
    if timestamp.tzinfo is None:
        times = pd.DatetimeIndex([timestamp]).tz_localize(LOC.tz)
    else:
        times = pd.DatetimeIndex([timestamp])

    solpos = LOC.get_solarposition(times)
    clearsky = LOC.get_clearsky(times, model="ineichen")  # GHI/DNI/DHI ciel clair

    # Atténuation nuageuse : les nuages coupent surtout le direct (DNI)
    dni = clearsky["dni"].iloc[0] * (1 - 0.95 * cloud_factor)
    dhi = clearsky["dhi"].iloc[0] * (1 + 0.4 * cloud_factor)  # le diffus augmente un peu
    ghi = dhi + dni * np.cos(np.radians(solpos["apparent_zenith"].iloc[0]))
    ghi = max(ghi, 0)

    # Transposition GHI -> plan des panneaux (POA)
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=CFG["layout"]["tilt_deg"],
        surface_azimuth=CFG["layout"]["azimuth_deg"],
        solar_zenith=solpos["apparent_zenith"],
        solar_azimuth=solpos["azimuth"],
        dni=dni, ghi=ghi, dhi=dhi,
    )["poa_global"].iloc[0]
    poa = max(float(poa), 0.0)

    # Température ambiante : sinusoïde journalière simple
    hour = timestamp.hour + timestamp.minute / 60
    t_amb = 18 + 10 * np.sin((hour - 9) * np.pi / 12)  # min ~8h, max ~15h

    wind = max(np.random.normal(3.0, 1.2), 0.1)

    # Température de cellule (modèle Faiman, standard IEC 61853)
    t_cell = pvlib.temperature.faiman(poa, t_amb, wind)

    return {
        "ghi": ghi, "poa": poa, "t_amb": t_amb,
        "t_cell": float(t_cell), "wind": wind,
        "sun_elevation": float(90 - solpos["apparent_zenith"].iloc[0]),
        "sun_azimuth": float(solpos["azimuth"].iloc[0]),
    }


def string_dc_power(poa, t_cell, derate=1.0):
    """Puissance DC d'un string (modèle PVWatts). derate = 1.0 = string sain."""
    n = CFG["layout"]["panels_per_string"]
    pdc0 = CFG["module"]["pdc0_w"] * n            # 24 x 435 = 10 440 W
    gamma = CFG["module"]["gamma_pdc"]            # -0.35 %/°C
    pdc = pdc0 * (poa / 1000.0) * (1 + gamma * (t_cell - 25.0))
    return max(pdc * derate, 0.0)


def string_iv(pdc, poa):
    """Décompose la puissance en tension/courant plausibles."""
    if pdc <= 1:
        return 0.0, 0.0
    vmp = 24 * 33.0 * (0.96 + 0.04 * min(poa / 1000, 1))  # ~760-790 V
    imp = pdc / vmp
    return round(vmp, 1), round(imp, 2)