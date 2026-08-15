"""Embedded-surface Robin boundary physics and per-cell moisture state."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

SIGMA = 5.670374419e-8
H_FG = 2_257_000.0
R_VAPOR = 461.5


@dataclass(frozen=True)
class BoundaryConditions:
    ambient_c: float
    wall_c: float | None = None
    h_conv: float = 10.0
    emissivity: float = 0.90
    relative_humidity: float = 0.15
    covered: bool = False
    moisture_reservoir_kg_m2: float = 0.25
    lewis_number: float = 0.90

    @property
    def wall_temperature_c(self) -> float:
        return self.ambient_c if self.wall_c is None else self.wall_c

    @classmethod
    def oven(cls, temperature_c: float, convection: bool = False, covered: bool = False, moisture_reservoir_kg_m2: float = 0.25) -> "BoundaryConditions":
        return cls(
            ambient_c=temperature_c,
            wall_c=temperature_c,
            h_conv=20.0 if convection else 10.0,
            relative_humidity=0.98 if covered else 0.15,
            covered=covered,
            moisture_reservoir_kg_m2=moisture_reservoir_kg_m2,
        )

    @classmethod
    def rest(cls, room_c: float = 22.0, foil_tent: bool = False) -> "BoundaryConditions":
        return cls(
            ambient_c=room_c,
            wall_c=room_c,
            h_conv=4.5 if foil_tent else 7.0,
            emissivity=0.35 if foil_tent else 0.90,
            relative_humidity=0.45,
            covered=foil_tent,
            moisture_reservoir_kg_m2=0.0,
        )


@dataclass
class SurfaceState:
    moisture_kg_m2: np.ndarray
    surface_temperature_c: np.ndarray
    evaporated_kg: float = 0.0

    @classmethod
    def initialize(cls, area: np.ndarray, temperature_c: float, reservoir_kg_m2: float) -> "SurfaceState":
        moisture = np.where(area > 0, reservoir_kg_m2, 0.0).astype(np.float32)
        surface = np.full(area.shape, temperature_c, dtype=np.float32)
        return cls(moisture, surface)

    @property
    def crust(self) -> np.ndarray:
        return self.moisture_kg_m2 <= 1e-8


@dataclass(frozen=True)
class FluxResult:
    net_w_m2: np.ndarray
    convective_w_m2: np.ndarray
    radiative_w_m2: np.ndarray
    evaporative_w_m2: np.ndarray
    mass_flux_kg_m2_s: np.ndarray
    surface_temperature_c: np.ndarray


def saturation_vapor_density(temperature_c: np.ndarray | float) -> np.ndarray:
    """Saturated water-vapor density using an Antoine correlation (0--100 C)."""
    t = np.clip(np.asarray(temperature_c, dtype=float), -20.0, 99.5)
    pressure_pa = 133.322368 * 10.0 ** (8.07131 - 1730.63 / (233.426 + t))
    return pressure_pa / (R_VAPOR * (t + 273.15))


def surface_flux(
    cell_temperature_c: np.ndarray,
    conductivity_w_mk: np.ndarray,
    phi_m: np.ndarray,
    spacing_m: float,
    area_m2: np.ndarray,
    pan_contact: np.ndarray,
    state: SurfaceState,
    bc: BoundaryConditions,
    dt_s: float,
) -> FluxResult:
    """Evaluate the lagged nonlinear Robin condition on each surface cell.

    The cell-to-surface conductive resistance gives a local ghost-surface
    temperature.  Radiation is linearized around the previous surface value;
    evaporation is evaluated once, then the surface balance is corrected.  The
    finite reservoir is debited independently in every embedded surface cell.
    """
    active = (area_m2 > 0) & ~pan_contact
    tc = np.asarray(cell_temperature_c, dtype=float)
    k = np.asarray(conductivity_w_mk, dtype=float)
    previous_ts = np.asarray(state.surface_temperature_c, dtype=float)
    ta = bc.ambient_c
    tw = bc.wall_temperature_c
    ts_k = np.clip(previous_ts + 273.15, 200.0, 500.0)
    tw_k = tw + 273.15
    h_rad = bc.emissivity * SIGMA * (tw_k + ts_k) * (tw_k**2 + ts_k**2)
    h_conv = bc.h_conv * np.where(state.crust, 1.15, 1.0)
    distance = np.maximum(-np.asarray(phi_m, dtype=float), 0.25 * spacing_m)
    conductance = k / distance

    total_h = h_conv + h_rad
    dry_ts = (conductance * tc + h_conv * ta + h_rad * tw) / np.maximum(conductance + total_h, 1e-12)
    hm = h_conv / (1.18 * 1006.0 * bc.lewis_number ** (2.0 / 3.0))
    vapor_surface = saturation_vapor_density(dry_ts)
    # ``relative_humidity`` describes the make-up room air, not a fictitious
    # 180 C saturation state.  Covered mode is separately driven toward zero.
    vapor_air = bc.relative_humidity * saturation_vapor_density(min(ta, 30.0))
    mass_flux = hm * np.maximum(vapor_surface - vapor_air, 0.0)
    if bc.covered:
        mass_flux *= 0.03
    mass_flux = np.where(state.moisture_kg_m2 > 0, mass_flux, 0.0)
    mass_flux = np.minimum(mass_flux, state.moisture_kg_m2 / max(dt_s, 1e-12))
    mass_flux = np.where(active, mass_flux, 0.0)

    latent = H_FG * mass_flux
    surface_t = (conductance * tc + h_conv * ta + h_rad * tw - latent) / np.maximum(conductance + total_h, 1e-12)
    surface_t = np.clip(surface_t, min(ta, tw, float(np.nanmin(tc))) - 25.0, max(ta, tw, float(np.nanmax(tc))) + 5.0)
    conv = h_conv * (ta - surface_t)
    rad = bc.emissivity * SIGMA * ((tw + 273.15) ** 4 - (surface_t + 273.15) ** 4)
    evap = H_FG * mass_flux
    net = conv + rad - evap
    net = np.where(active, net, 0.0)

    removed = np.minimum(state.moisture_kg_m2, mass_flux * dt_s)
    state.moisture_kg_m2[...] = np.maximum(state.moisture_kg_m2 - removed, 0.0)
    state.surface_temperature_c[...] = np.where(area_m2 > 0, surface_t, state.surface_temperature_c)
    state.evaporated_kg += float(np.sum(removed * area_m2))
    return FluxResult(
        net.astype(np.float32),
        np.where(active, conv, 0.0).astype(np.float32),
        np.where(active, rad, 0.0).astype(np.float32),
        np.where(active, evap, 0.0).astype(np.float32),
        mass_flux.astype(np.float32),
        surface_t.astype(np.float32),
    )
