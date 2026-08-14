"""Thermophysical properties used by both reference and web implementations.

The correlations are the Choi--Okos component polynomials (temperature in °C),
combined with fixed mass fractions representative of lean meat.  Composition is
an explicit modelling assumption, not a fitted product profile.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class Composition:
    water: float = 0.75
    protein: float = 0.20
    fat: float = 0.03
    ash: float = 0.02

    def __post_init__(self) -> None:
        if abs(self.water + self.protein + self.fat + self.ash - 1.0) > 1e-6:
            raise ValueError("composition mass fractions must sum to one")


LEAN_MEAT = Composition()


def _components(temp_c):
    t = np.asarray(temp_c, dtype=np.float64)
    # kg/m³
    rho = np.stack((
        997.18 + 3.1439e-3*t - 3.7574e-3*t*t,
        1329.9 - 0.5184*t,
        925.59 - 0.41757*t,
        2423.8 - 0.28063*t,
    ))
    # J/(kg K)
    cp = 1000.0*np.stack((
        4.1762 - 9.0864e-5*t + 5.4731e-6*t*t,
        2.0082 + 1.2089e-3*t - 1.3129e-6*t*t,
        1.9842 + 1.4733e-3*t - 4.8008e-6*t*t,
        1.0926 + 1.8896e-3*t - 3.6817e-6*t*t,
    ))
    # W/(m K)
    conductivity = np.stack((
        0.57109 + 1.7625e-3*t - 6.7036e-6*t*t,
        0.17881 + 1.1958e-3*t - 2.7178e-6*t*t,
        0.18071 - 2.7604e-3*t - 1.7749e-7*t*t,
        0.32962 + 1.4011e-3*t - 2.9069e-6*t*t,
    ))
    return rho, cp, conductivity


def meat_properties(temp_c, composition: Composition = LEAN_MEAT,
                    denaturation_bump: bool = False):
    """Return ``(rho, cp, k)`` arrays/scalars for lean meat.

    Density uses reciprocal-volume mixing; heat capacity and conductivity use
    mass-fraction mixing.  An optional broad 50--70 °C effective-cp bump is
    provided for controlled experiments and is disabled by default because no
    probe logs exist to calibrate its magnitude.
    """
    rho_i, cp_i, k_i = _components(temp_c)
    fractions = np.asarray((composition.water, composition.protein,
                            composition.fat, composition.ash), dtype=np.float64)
    shape = (4,) + (1,) * (rho_i.ndim - 1)
    x = fractions.reshape(shape)
    rho = 1.0 / np.sum(x / rho_i, axis=0)
    cp = np.sum(x * cp_i, axis=0)
    k = np.sum(x * k_i, axis=0)
    if denaturation_bump:
        t = np.asarray(temp_c, dtype=np.float64)
        cp = cp + 180.0*np.exp(-0.5*((t - 60.0)/6.0)**2)
    if np.ndim(temp_c) == 0:
        return float(rho), float(cp), float(k)
    return rho, cp, k


def thermal_diffusivity(temp_c, **kwargs):
    rho, cp, k = meat_properties(temp_c, **kwargs)
    return k/(rho*cp)
