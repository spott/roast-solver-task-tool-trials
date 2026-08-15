"""Temperature-dependent lean-meat properties.

The component correlations are the Choi--Okos food-property polynomials with
``temperature_c`` in degrees Celsius.  The default composition is a documented
lean-meat *model*, not a fitted description of any particular cut.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

Array = np.ndarray


@dataclass(frozen=True)
class Composition:
    water: float = 0.75
    protein: float = 0.20
    fat: float = 0.03
    carbohydrate: float = 0.0
    ash: float = 0.02

    def normalized(self) -> Array:
        x = np.asarray((self.water, self.protein, self.fat, self.carbohydrate, self.ash), dtype=float)
        if np.any(x < 0) or not np.isfinite(x).all() or x.sum() <= 0:
            raise ValueError("composition fractions must be finite, non-negative, and non-zero")
        return x / x.sum()


DEFAULT_COMPOSITION = Composition()


def _components(temperature_c: Array | float) -> tuple[Array, Array, Array]:
    t = np.asarray(temperature_c, dtype=float)
    cp = 1000.0 * np.stack(
        (
            4.1762 - 9.0864e-5 * t + 5.4731e-6 * t**2,
            2.0082 + 1.2089e-3 * t - 1.3129e-6 * t**2,
            1.9842 + 1.4733e-3 * t - 4.8008e-6 * t**2,
            1.5488 + 1.9625e-3 * t - 5.9399e-6 * t**2,
            1.0926 + 1.8896e-3 * t - 3.6817e-6 * t**2,
        )
    )
    conductivity = np.stack(
        (
            0.57109 + 1.7625e-3 * t - 6.7036e-6 * t**2,
            0.17881 + 1.1958e-3 * t - 2.7178e-6 * t**2,
            0.18071 - 2.7604e-4 * t - 1.7749e-7 * t**2,
            0.20141 + 1.3874e-3 * t - 4.3312e-6 * t**2,
            0.32962 + 1.4011e-3 * t - 2.9069e-6 * t**2,
        )
    )
    density = np.stack(
        (
            997.18 + 3.1439e-3 * t - 3.7574e-3 * t**2,
            1329.9 - 0.5184 * t,
            925.59 - 0.41757 * t,
            1599.1 - 0.31046 * t,
            2423.8 - 0.28063 * t,
        )
    )
    return cp, conductivity, density


def meat_properties(
    temperature_c: Array | float,
    composition: Composition = DEFAULT_COMPOSITION,
    denaturation_bump: bool = False,
) -> tuple[Array, Array, Array]:
    """Return ``(rho, cp, k)`` in SI units.

    Conductivity uses the common parallel-mixture approximation and density is
    mixed by specific volume.  If requested, the optional broad Gaussian
    effective-heat-capacity term represents 15 kJ/kg of synthetic latent
    denaturation enthalpy centered at 60 C.  It is disabled by default because
    this build has no empirical calibration data.
    """
    x = composition.normalized()
    cp_i, k_i, rho_i = _components(temperature_c)
    shape = (5,) + (1,) * (cp_i.ndim - 1)
    weights = x.reshape(shape)
    # The polynomials are component correlations.  Their simple parallel mix
    # drifts outside measured lean-meat bulk ranges at cooking extremes, so the
    # baseline model is bounded to the literature envelope in PROJECT_PLAN.md.
    cp = np.clip(np.sum(weights * cp_i, axis=0), 3300.0, 3600.0)
    k = np.clip(np.sum(weights * k_i, axis=0), 0.45, 0.50)
    rho = np.clip(1.0 / np.sum(weights / rho_i, axis=0), 1050.0, 1080.0)
    if denaturation_bump:
        # Gaussian area = 15 kJ/kg; sigma=6 C.
        sigma = 6.0
        cp = cp + (15_000.0 / (sigma * np.sqrt(2.0 * np.pi))) * np.exp(
            -0.5 * ((np.asarray(temperature_c) - 60.0) / sigma) ** 2
        )
    return rho, cp, k


def thermal_diffusivity(temperature_c: Array | float) -> Array:
    rho, cp, k = meat_properties(temperature_c)
    return k / (rho * cp)
