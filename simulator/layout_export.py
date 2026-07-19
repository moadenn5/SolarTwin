"""layout_export.py — Génère plant_layout.csv : position 3D des 480 tables.
Grille 24 rangées x 20 tables. Unités Unreal : centimètres."""
import json
import csv

CFG = json.load(open("plant_config.json"))
pitch = CFG["layout"]["row_pitch_m"]                              # 7 m entre rangées
table_w = CFG["layout"]["table_cols"] * CFG["module"]["width_m"] + 0.4  # ~14 m

strings_per_inv = CFG["inverters"][0]["strings"]

def string_id_from_index(i):
    inv = i // strings_per_inv + 1          # 0-119 -> INV01, 120-239 -> INV02...
    num = i % strings_per_inv + 1
    return f"INV{inv:02d}-STR{num:03d}"

ROWS, COLS = 24, 20                          # 480 tables
with open("plant_layout.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Name", "StringID", "X", "Y", "Tilt", "Azimuth"])
    i = 0
    for r in range(ROWS):
        for c in range(COLS):
            w.writerow([f"Table_{i:03d}", string_id_from_index(i),
                        r * pitch * 100, c * (table_w + 2) * 100,
                        CFG["layout"]["tilt_deg"], CFG["layout"]["azimuth_deg"]])
            i += 1
print(f"{i} tables exportées dans plant_layout.csv")