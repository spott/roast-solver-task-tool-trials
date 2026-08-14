"""Temperature-dependent lean-meat properties.

The equations are the commonly published Choi--Okos component correlations.
Temperatures passed to this module are degrees Celsius; returned values are SI.
The default composition is deliberately a simple lean-meat baseline rather than
an empirical fit to a particular roast.
"""

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class Composition:
    water: float = 0.75
    protein: float = 0.20
    fat: float = 0.03
    carbohydrate: float = 0.005
    ash: float = 0.015

    def fractions(self) -> np.ndarray:
        x = np.asarray([self.water, self.protein, self.fat, self.carbohydrate, self.ash])
        if np.any(x < 0) or not np.isclose(x.sum(), 1.0, atol=1e-8):
            raise ValueError("composition mass fractions must be non-negative and sum to one")
        return x


LEAN_MEAT = Composition()


def _temperature(t_c):
    return np.clip(np.asarray(t_c, dtype=np.float64), -20.0, 150.0)


def component_density(t_c) -> np.ndarray:
    """Component densities, final axis: water, protein, fat, carbohydrate, ash."""
    t = _temperature(t_c)[..., None]
    return np.concatenate(
        (
            997.18 + 3.1439e-3 * t - 3.7574e-3 * t * t,
            1329.9 - 0.5184 * t,
            925.59 - 0.41757 * t,
            1599.1 - 0.31046 * t,
            2423.8 - 0.28063 * t,
        ),
        axis=-1,
    )


def component_heat_capacity(t_c) -> np.ndarray:
    """Component specific heat capacities in J/(kg K)."""
    t = _temperature(t_c)[..., None]
    return np.concatenate(
        (
            4176.2 - 0.0909 * t + 5.4731e-3 * t * t,
            2008.2 + 1.2089 * t - 1.3129e-3 * t * t,
            1984.2 + 1.4733 * t - 4.8008e-3 * t * t,
            1548.8 + 1.9625 * t - 5.9399e-3 * t * t,
            1092.6 + 1.8896 * t - 3.6817e-3 * t * t,
        ),
        axis=-1,
    )


def component_conductivity(t_c) -> np.ndarray:
    """Component thermal conductivities in W/(m K)."""
    t = _temperature(t_c)[..., None]
    return np.concatenate(
        (
            0.57109 + 1.7625e-3 * t - 6.7036e-6 * t * t,
            0.17881 + 1.1958e-3 * t - 2.7178e-6 * t * t,
            0.18071 - 2.7604e-4 * t - 1.7749e-7 * t * t,
            0.20141 + 1.3874e-3 * t - 4.3312e-6 * t * t,
            0.32962 + 1.4011e-3 * t - 2.9069e-6 * t * t,
        ),
        axis=-1,
    )


def density(t_c, composition: Composition = LEAN_MEAT):
    """Mixture density using reciprocal volume additivity, kg/m^3."""
    x = composition.fractions()
    return 1.0 / np.sum(x / component_density(t_c), axis=-1)


def heat_capacity(t_c, composition: Composition = LEAN_MEAT, denaturation_bump=False):
    """Mass-weighted cp, optionally with a documented broad synthetic bump."""
    t = _temperature(t_c)
    cp = np.sum(component_heat_capacity(t) * composition.fractions(), axis=-1)
    if denaturation_bump:
        # Optional model knob, not calibrated: 120 J/(kg K) peak around 60 C.
        cp = cp + 120.0 * np.exp(-0.5 * ((t - 60.0) / 7.0) ** 2)
    return cp


def conductivity(t_c, composition: Composition = LEAN_MEAT):
    """Volume-fraction parallel mixing rule, W/(m K)."""
    x = composition.fractions()
    rho_i = component_density(t_c)
    volume = x / rho_i
    volume_fraction = volume / np.sum(volume, axis=-1, keepdims=True)
    return np.sum(volume_fraction * component_conductivity(t_c), axis=-1)


def diffusivity(t_c, composition: Composition = LEAN_MEAT):
    return conductivity(t_c, composition) / (density(t_c, composition) * heat_capacity(t_c, composition))
