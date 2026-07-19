"""sensors.py — Capteur virtuel : transforme une valeur physique "vraie"
en mesure réaliste (bruit, quantification, saturation, pannes, quality flag)."""

import numpy as np
import time


class VirtualSensor:
    def __init__(self, sensor_id, unit, noise_pct=1.0, resolution=0.1,
                 range_min=0, range_max=1e9, sample_period_s=1.0):
        self.id = sensor_id
        self.unit = unit
        self.noise_pct = noise_pct          # bruit gaussien en % de la lecture
        self.resolution = resolution        # pas de quantification (ex: 0.1 W/m²)
        self.range = (range_min, range_max)
        self.sample_period = sample_period_s
        self.drift = 0.0                    # dérive lente de calibration
        self.failed_mode = None             # None | "stuck" | "nan"
        self.stuck_value = None
        self._last_sample_time = 0
        self._last_value = None

    def read(self, true_value, now=None):
        """Retourne (valeur_mesurée, quality). Respecte la fréquence d'échantillonnage."""
        now = time.time() if now is None else now
        # Un capteur 5 s ne donne pas de nouvelle valeur chaque seconde :
        if now - self._last_sample_time < self.sample_period and self._last_value is not None:
            return self._last_value  # renvoie la dernière mesure (comme un registre Modbus)
        self._last_sample_time = now

        if self.failed_mode == "nan":
            self._last_value = (None, "BAD")
            return self._last_value
        if self.failed_mode == "stuck":
            self._last_value = (self.stuck_value, "UNCERTAIN")
            return self._last_value

        # dérive lente de calibration (ex: encrassement du pyranomètre)
        self.drift += 1e-9
        noisy = true_value * (1 + self.drift) \
                + np.random.normal(0, abs(true_value) * self.noise_pct / 100 + 1e-6)
        # quantification (résolution de l'ADC)
        quantized = round(noisy / self.resolution) * self.resolution
        # saturation aux bornes de la plage
        clamped = min(max(quantized, self.range[0]), self.range[1])
        quality = "GOOD" if clamped == quantized else "UNCERTAIN"
        self._last_value = (round(clamped, 3), quality)
        return self._last_value

    def fail(self, mode, stuck_value=None):
        """mode: 'stuck' (valeur figée) ou 'nan' (plus de donnée)."""
        self.failed_mode = mode
        self.stuck_value = stuck_value

    def repair(self):
        self.failed_mode = None