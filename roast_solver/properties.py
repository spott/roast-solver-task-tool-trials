"""Thermophysical properties used by both the oracle and web implementation.

The baseline is a transparent, lean-meat approximation to the Choi--Okos
composition correlations (75% water, 20% protein, 5% fat). Temperatures are
clamped to the range relevant to cooking. These are literature-model values,
not fitted measurements for any particular roast.
"""
from __future__ import annotations

import numpy as np

WATER, PROTEIN, FAT = 0.75, 0.20, 0.05
SIGMA = 5.670374419e-8
H_FG = 2.257e6


def _tc(t):
    return np.clip(np.asarray(t, dtype=np.float64), -10.0, 120.0)


def heat_capacity(t):
    """Mixture specific heat [J kg-1 K-1]."""
    x = _tc(t)
    # Choi-Okos component polynomials, temperature in Celsius.
    cw = 4176.2 - 0.0909*x + 0.005473*x*x
    cp = 2008.2 + 1.2089*x - 0.0013129*x*x
    cf = 1984.2 + 1.4733*x - 0.0048008*x*x
    return WATER*cw + PROTEIN*cp + FAT*cf


def conductivity(t):
    """Mixture thermal conductivity [W m-1 K-1]."""
    x = _tc(t)
    kw = 0.57109 + 0.0017625*x - 6.7036e-6*x*x
    kp = 0.17881 + 0.0011958*x - 2.7178e-6*x*x
    kf = 0.18071 - 0.00027604*x - 1.7749e-7*x*x
    # Parallel mixture is appropriate as a modest effective-k baseline.
    return WATER*kw + PROTEIN*kp + FAT*kf


def density(t):
    """Effective bulk density [kg m-3], including normal tissue porosity."""
    x = _tc(t)
    # A weak thermal expansion around the specified 1060 kg/m3 baseline.
    return 1060.0 / (1.0 + 3.0e-4*(x - 20.0))


def diffusivity(t):
    return conductivity(t) / (density(t) * heat_capacity(t))


def saturation_vapor_density(t_c):
    """Water-vapour saturation density [kg m-3] (Tetens + ideal gas)."""
    t = np.clip(np.asarray(t_c, dtype=np.float64), -20.0, 100.0)
    p = 610.94 * np.exp(17.625*t/(t + 243.04))
    return p / (461.5 * (t + 273.15))


def linearized_radiation(emissivity: float, wall_c: float, surface_c):
    """Return exact secant radiation coefficient [W m-2 K-1]."""
    tw = wall_c + 273.15
    ts = np.asarray(surface_c) + 273.15
    return emissivity * SIGMA * (tw + ts) * (tw*tw + ts*ts)
