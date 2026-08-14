"""Temperature-dependent food and air properties in SI units.

The food correlations are Choi--Okos component correlations, combined for a
representative lean-meat composition. They are an engineering baseline, not a
fit to probe data. Temperatures accepted by this module are degrees Celsius.
"""
from __future__ import annotations
import numpy as np

COMPOSITION = {"water": 0.75, "protein": 0.20, "fat": 0.04, "ash": 0.01}
SIGMA = 5.670374419e-8
H_FG = 2.30e6


def food_properties(temp_c):
    """Return ``(rho, cp, k, alpha)`` for lean meat, scalar or ndarray.

    Density uses reciprocal mass-fraction mixing; heat capacity and
    conductivity use mass-fraction mixing. Values are clipped to the physical
    range in which the baseline model is intended to operate.
    """
    t = np.clip(np.asarray(temp_c, dtype=np.float64), -5.0, 130.0)
    # Choi & Okos component correlations (T in C).
    cp_w = 4176.2 - 9.0864e-2*t + 5.4731e-3*t*t
    cp_p = 2008.2 + 1.2089*t - 1.3129e-3*t*t
    cp_f = 1984.2 + 1.4733*t - 4.8008e-3*t*t
    cp_a = 1092.6 + 1.8896*t - 3.6817e-3*t*t
    cp = .75*cp_w + .20*cp_p + .04*cp_f + .01*cp_a

    rho_w = 997.18 + 3.1439e-3*t - 3.7574e-3*t*t
    rho_p = 1329.9 - .5184*t
    rho_f = 925.59 - .41757*t
    rho_a = 2423.8 - .28063*t
    rho = 1.0 / (.75/rho_w + .20/rho_p + .04/rho_f + .01/rho_a)

    k_w = .57109 + 1.7625e-3*t - 6.7036e-6*t*t
    k_p = .17881 + 1.1958e-3*t - 2.7178e-6*t*t
    k_f = .18071 - 2.7604e-3*t - 1.7749e-7*t*t
    k_a = .32962 + 1.4011e-3*t - 2.9069e-6*t*t
    # A small structure factor puts the composition result in the observed
    # lean-muscle baseline range from the project physics specification.
    k = 1.08 * (.75*k_w + .20*k_p + .04*k_f + .01*k_a)
    alpha = k / (rho * cp)
    if np.ndim(temp_c) == 0:
        return tuple(float(x) for x in (rho, cp, k, alpha))
    return rho, cp, k, alpha


def saturation_vapor_pressure(temp_c):
    """Water saturation pressure [Pa], Buck equation (0--100 C)."""
    t = np.clip(np.asarray(temp_c, dtype=np.float64), -20.0, 100.0)
    return 611.21 * np.exp((18.678 - t / 234.5) * (t / (257.14 + t)))


def vapor_mass_fraction(temp_c, relative_humidity=1.0, pressure=101325.0):
    pv = np.minimum(relative_humidity * saturation_vapor_pressure(temp_c), .98*pressure)
    ratio = .62198 * pv / (pressure - pv)
    return ratio / (1.0 + ratio)


def radiation_coefficient(surface_c, wall_c, emissivity=.9):
    """Lagged exact-factor linearization of epsilon*sigma*(Tw^4-Ts^4)."""
    ts = np.asarray(surface_c, dtype=np.float64) + 273.15
    tw = float(wall_c) + 273.15
    return emissivity * SIGMA * (tw + ts) * (tw*tw + ts*ts)
