"""Lean-meat thermophysical properties.

The component polynomials are the commonly used Choi--Okos food-property
correlations.  The composition is a deliberately simple lean-meat baseline,
not a fit to probe data. Temperatures supplied to this module are degrees C.
"""
from __future__ import annotations
import numpy as np

COMPOSITION = {"water": 0.75, "protein": 0.20, "fat": 0.03, "carbohydrate": 0.008, "ash": 0.012}

def _t(a, dtype=float):
    return np.asarray(a, dtype=dtype)

def heat_capacity(temp_c):
    """Mixture specific heat capacity in J kg-1 K-1."""
    t = np.clip(_t(temp_c), -20.0, 150.0)
    cp = {
        "water": 4.1762 - 9.0864e-5*t + 5.4731e-6*t*t,
        "protein": 2.0082 + 1.2089e-3*t - 1.3129e-6*t*t,
        "fat": 1.9842 + 1.4733e-3*t - 4.8008e-6*t*t,
        "carbohydrate": 1.5488 + 1.9625e-3*t - 5.9399e-6*t*t,
        "ash": 1.0926 + 1.8896e-3*t - 3.6817e-6*t*t,
    }
    return 1000.0 * sum(COMPOSITION[name] * value for name, value in cp.items())

def conductivity(temp_c):
    """Mixture thermal conductivity in W m-1 K-1."""
    t = np.clip(_t(temp_c), -20.0, 150.0)
    k = {
        "water": .57109 + 1.7625e-3*t - 6.7036e-6*t*t,
        "protein": .17881 + 1.1958e-3*t - 2.7178e-6*t*t,
        "fat": .18071 - 2.7604e-4*t - 1.7749e-7*t*t,
        "carbohydrate": .20141 + 1.3874e-3*t - 4.3312e-6*t*t,
        "ash": .32962 + 1.4011e-3*t - 2.9069e-6*t*t,
    }
    return sum(COMPOSITION[name] * value for name, value in k.items())

def density(temp_c):
    """Mixture density in kg m-3 using reciprocal-volume mixing."""
    t = np.clip(_t(temp_c), -20.0, 150.0)
    rho = {
        "water": 997.18 + 3.1439e-3*t - 3.7574e-3*t*t,
        "protein": 1329.9 - .5184*t,
        "fat": 925.59 - .41757*t,
        "carbohydrate": 1599.1 - .31046*t,
        "ash": 2423.8 - .28063*t,
    }
    # Cooking shrinkage is outside v1; retain the plan's lean-meat bulk range.
    return np.clip(1.0 / sum(COMPOSITION[name] / value for name, value in rho.items()), 1050.0, 1080.0)

def diffusivity(temp_c):
    return conductivity(temp_c) / (density(temp_c) * heat_capacity(temp_c))

def enthalpy(temp_c, reference_c=0.0):
    """Specific sensible enthalpy (J/kg) from analytic cp integrals."""
    t = _t(temp_c)
    r = float(reference_c)
    coeff = {
        "water": (4.1762, -9.0864e-5, 5.4731e-6),
        "protein": (2.0082, 1.2089e-3, -1.3129e-6),
        "fat": (1.9842, 1.4733e-3, -4.8008e-6),
        "carbohydrate": (1.5488, 1.9625e-3, -5.9399e-6),
        "ash": (1.0926, 1.8896e-3, -3.6817e-6),
    }
    out = 0.0
    for name, (a, b, c) in coeff.items():
        out = out + COMPOSITION[name] * (a*(t-r) + .5*b*(t*t-r*r) + c/3*(t**3-r**3))
    return 1000.0*out
