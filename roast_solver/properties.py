"""Thermophysical properties used by the reference solver.

The composition is a documented lean-meat approximation, not a fitted product
model.  Equations are the Choi--Okos component correlations (temperature in °C)
combined by mass fraction.  Density uses reciprocal-volume mixing.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class Composition:
    water: float = 0.75
    protein: float = 0.20
    fat: float = 0.04
    ash: float = 0.01

    def __post_init__(self) -> None:
        if abs(self.water + self.protein + self.fat + self.ash - 1.0) > 1e-9:
            raise ValueError("composition mass fractions must sum to one")


def component_cp(temp_c):
    """Return component heat capacities in J kg⁻¹ K⁻¹."""
    t = np.asarray(temp_c, dtype=np.float64)
    return {
        "water": 1000.0 * (4.1762 - 9.0864e-5*t + 5.4731e-6*t*t),
        "protein": 1000.0 * (2.0082 + 1.2089e-3*t - 1.3129e-6*t*t),
        "fat": 1000.0 * (1.9842 + 1.4733e-3*t - 4.8008e-6*t*t),
        "ash": 1000.0 * (1.0926 + 1.8896e-3*t - 3.6817e-6*t*t),
    }


def component_k(temp_c):
    """Return component conductivities in W m⁻¹ K⁻¹."""
    t = np.asarray(temp_c, dtype=np.float64)
    return {
        "water": 0.57109 + 1.7625e-3*t - 6.7036e-6*t*t,
        "protein": 0.17881 + 1.1958e-3*t - 2.7178e-6*t*t,
        "fat": 0.18071 - 2.7604e-3*t + 1.7749e-5*t*t,
        "ash": 0.32962 + 1.4011e-3*t - 2.9069e-6*t*t,
    }


def component_rho(temp_c):
    """Return component densities in kg m⁻³."""
    t = np.asarray(temp_c, dtype=np.float64)
    return {
        "water": 997.18 + 3.1439e-3*t - 3.7574e-3*t*t,
        "protein": 1329.9 - 0.5184*t,
        "fat": 925.59 - 0.41757*t,
        "ash": np.zeros_like(t) + 2423.8,
    }


def meat_properties(temp_c, composition: Composition = Composition(), denaturation_bump: bool = False):
    """Return ``(rho, cp, k)`` arrays for the meat mixture.

    Thermal conductivity uses the parallel (mass-weighted) approximation.  The
    optional broad Gaussian cp feature is deliberately off by default because
    no empirical calibration data is available in this build.
    """
    fractions = composition.__dict__
    cps, ks, rhos = component_cp(temp_c), component_k(temp_c), component_rho(temp_c)
    cp = sum(fractions[n] * cps[n] for n in fractions)
    if denaturation_bump:
        cp = cp + 180.0 * np.exp(-0.5 * ((np.asarray(temp_c) - 60.0) / 7.0) ** 2)
    k = sum(fractions[n] * ks[n] for n in fractions)
    rho = 1.0 / sum(fractions[n] / rhos[n] for n in fractions)
    return rho.astype(np.float32), cp.astype(np.float32), k.astype(np.float32)


def thermal_diffusivity(temp_c):
    rho, cp, k = meat_properties(temp_c)
    return k / (rho * cp)
