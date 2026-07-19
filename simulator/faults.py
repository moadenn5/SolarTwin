"""faults.py — Catalogue de pannes (Phase 0) + générateur de nuages.
Retourne un facteur de derate par string + des événements."""

import random


class FaultEngine:
    def __init__(self, all_string_ids):
        self.soiling = {sid: 0.0 for sid in all_string_ids}   # % de perte
        self.dead_strings = set()
        self.events = []

    def tick(self, now, string_ids):
        """Appelé à chaque tick. Retourne {string_id: derate} (1.0 = sain)."""
        derates = {}
        for sid in string_ids:
            d = 1.0
            # 1. Encrassement progressif sur 3 strings choisis (~0.2 %/jour, max 15 %)
            if sid in ("INV02-STR014", "INV02-STR015", "INV03-STR077"):
                self.soiling[sid] = min(self.soiling[sid] + 0.002 / 86400, 0.15)
                d *= (1 - self.soiling[sid])
            # 2. Ombrage matinal rangée est (strings 001-020 de INV01)
            if sid.startswith("INV01-STR0") and int(sid[-3:]) <= 20:
                if 7 <= now.hour < 9:
                    d *= 0.7
            # 3. String mort
            if sid in self.dead_strings:
                d = 0.0
            derates[sid] = d
        return derates

    def kill_string(self, sid, now):
        self.dead_strings.add(sid)
        self.events.append({"time": now.isoformat(), "level": "CRITICAL",
                            "equipment": sid, "message": "String current dropped to 0 A"})

    def revive_string(self, sid):
        self.dead_strings.discard(sid)


class CloudEngine:
    """Passages nuageux aléatoires : montée en ~90 s, plateau 2-10 min, redescente.
    cloud_factor: 0 = ciel clair, ~0.7 = gros nuage."""

    RAMP_S = 90

    def __init__(self, events_per_day=4):
        self.p_start = events_per_day / 86400.0   # proba de départ par seconde simulée
        self.state = "clear"        # clear | ramp_up | hold | ramp_down
        self.factor = 0.0
        self.target = 0.0
        self.t_state = 0.0          # temps écoulé dans l'état courant (s)
        self.hold_duration = 0.0

    def tick(self, dt_s):
        """dt_s = secondes simulées écoulées depuis le dernier tick."""
        self.t_state += dt_s
        if self.state == "clear":
            if random.random() < self.p_start * dt_s:
                self.state, self.t_state = "ramp_up", 0.0
                self.target = random.uniform(0.6, 0.8)
                self.hold_duration = random.uniform(120, 600)
        elif self.state == "ramp_up":
            self.factor = self.target * min(self.t_state / self.RAMP_S, 1.0)
            if self.t_state >= self.RAMP_S:
                self.state, self.t_state = "hold", 0.0
        elif self.state == "hold":
            self.factor = self.target
            if self.t_state >= self.hold_duration:
                self.state, self.t_state = "ramp_down", 0.0
        elif self.state == "ramp_down":
            self.factor = self.target * max(1 - self.t_state / self.RAMP_S, 0.0)
            if self.t_state >= self.RAMP_S:
                self.state, self.t_state, self.factor = "clear", 0.0, 0.0
        return round(self.factor, 3)