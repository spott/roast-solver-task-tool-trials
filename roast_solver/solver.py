"""NumPy 3-D finite-volume/finite-difference reference solver.

Interior links are a conservative 7-point stencil. Embedded boundary power is
``q'' * geometry.surface_area`` on the one-cell SDF shell; it is never inferred
from exposed voxel faces. Consequently the same boundary power used to update
enthalpy is also used for the reported energy budget.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional
import math
import numpy as np

from .geometry import GridGeometry
from .properties import conductivity, density, diffusivity, heat_capacity

SIGMA = 5.670374419e-8
H_FG = 2.256e6


@dataclass(frozen=True)
class BoundaryConfig:
    oven_c: float = 180.0
    convection_h: float = 10.0
    emissivity: float = 0.90
    wall_c: Optional[float] = None
    covered: bool = False
    ambient_vapor_density: float = 0.010  # kg/m3, deliberately explicit assumption
    lewis_number: float = 0.90
    surface_water_kg_m2: float = 0.25
    pan_insulated: bool = True


@dataclass(frozen=True)
class SimulationConfig:
    initial_c: float = 5.0
    target_c: float = 55.0
    max_cook_s: float = 5 * 3600.0
    rest_s: float = 30 * 60.0
    sample_interval_s: float = 30.0
    requested_dt_s: float = 30.0
    rest_ambient_c: float = 22.0
    rest_h: float = 7.0
    foil_tent: bool = False
    pasteurization_ref_c: float = 70.0
    pasteurization_z_c: float = 10.0
    denaturation_bump: bool = False


@dataclass
class SimulationResult:
    time_s: np.ndarray
    coldest_c: np.ndarray
    probe_c: np.ndarray
    surface_mean_c: np.ndarray
    pasteurization_equivalent_min: np.ndarray
    phase: list[str]
    pull_time_s: Optional[float]
    pull_reached: bool
    peak_core_c: float
    peak_time_s: float
    carryover_c: float
    final_temperature_c: np.ndarray
    wet_fraction: np.ndarray
    energy: dict[str, float]
    dt_s: float
    probe_index_zyx: tuple[int, int, int]


def saturation_vapor_density(t_c):
    """Tetens saturation pressure converted to vapor density (kg/m3)."""
    t = np.clip(np.asarray(t_c, dtype=np.float64), -20.0, 100.0)
    pressure = 610.94 * np.exp(17.625 * t / (t + 243.04))
    return pressure / (461.5 * (t + 273.15))


def stable_timestep(geometry: GridGeometry, maximum_temperature_c=220.0) -> float:
    temps = np.linspace(-5.0, maximum_temperature_c, 128)
    alpha_max = float(np.max(diffusivity(temps)))
    return geometry.spacing_m**2 / (6.0 * alpha_max)


def _interior_power(t, k, inside, h):
    power = np.zeros(t.shape, dtype=np.float64)
    for axis in range(3):
        lo = [slice(None)] * 3
        hi = [slice(None)] * 3
        lo[axis] = slice(None, -1)
        hi[axis] = slice(1, None)
        lo, hi = tuple(lo), tuple(hi)
        linked = inside[lo] & inside[hi]
        k_face = 2.0 * k[lo] * k[hi] / np.maximum(k[lo] + k[hi], 1e-12)
        flux = np.where(linked, k_face * h * (t[hi] - t[lo]), 0.0)
        power[lo] += flux
        power[hi] -= flux
    return power


def _surface_flux(t_surface, boundary: BoundaryConfig, wet, dt, cooking=True, rest_ambient_c=22.0, rest_h=7.0, foil=False):
    """Return net, convection, radiation, latent W/m2 and updated reservoir."""
    if cooking:
        air_c = boundary.oven_c
        wall_c = boundary.oven_c if boundary.wall_c is None else boundary.wall_c
        h_conv = boundary.convection_h
        emissivity = boundary.emissivity
        evaporation_enabled = not boundary.covered
    else:
        air_c = wall_c = rest_ambient_c
        h_conv = rest_h * (0.55 if foil else 1.0)
        emissivity = boundary.emissivity * (0.35 if foil else 1.0)
        evaporation_enabled = False

    q_conv = h_conv * (air_c - t_surface)
    tk, wk = t_surface + 273.15, wall_c + 273.15
    # Algebraically exact secant linearization, evaluated on previous-step Ts.
    h_rad = emissivity * SIGMA * (wk + tk) * (wk * wk + tk * tk)
    q_rad = h_rad * (wall_c - t_surface)

    mdot = np.zeros_like(t_surface, dtype=np.float64)
    if evaporation_enabled:
        rho_air, cp_air = 1.0, 1010.0
        h_mass = h_conv / (rho_air * cp_air * boundary.lewis_number ** (2.0 / 3.0))
        drive = np.maximum(saturation_vapor_density(t_surface) - boundary.ambient_vapor_density, 0.0)
        mdot = h_mass * drive
        mdot = np.minimum(mdot, wet / max(dt, 1e-12))
    q_latent = H_FG * mdot
    new_wet = np.maximum(wet - mdot * dt, 0.0)
    return q_conv + q_rad - q_latent, q_conv, q_rad, q_latent, new_wet


def _probe_index(geometry):
    indices = np.argwhere(geometry.inside)
    center = indices.mean(axis=0)
    return tuple(int(v) for v in indices[np.argmin(np.sum((indices - center) ** 2, axis=1))])


def simulate(
    geometry: GridGeometry,
    boundary: BoundaryConfig = BoundaryConfig(),
    config: SimulationConfig = SimulationConfig(),
    progress: Optional[Callable[[dict], None]] = None,
) -> SimulationResult:
    """Cook until target (or time limit), then integrate the requested rest.

    ``progress`` receives sampled scalar records and is the Python analogue of
    worker streaming. Fields outside the body remain NaN in the returned grid.
    """
    if not np.any(geometry.inside):
        raise ValueError("geometry is empty")
    stability = stable_timestep(geometry, max(boundary.oven_c, config.initial_c) + 20)
    dt = min(config.requested_dt_s, 0.90 * stability)
    if dt <= 0 or config.sample_interval_s <= 0:
        raise ValueError("time steps and sample interval must be positive")

    inside = geometry.inside
    surface = geometry.surface_area > 0
    exposed = surface & (~geometry.pan_contact if boundary.pan_insulated else np.ones(surface.shape, bool))
    t = np.full(inside.shape, config.initial_c, dtype=np.float32)
    wet = np.zeros(inside.shape, dtype=np.float64)
    wet[surface] = boundary.surface_water_kg_m2
    initial_wet = wet.copy()
    probe_idx = _probe_index(geometry)
    cell_volume = geometry.spacing_m**3

    history = {"time": [], "cold": [], "probe": [], "surface": [], "pasteur": [], "phase": []}
    budget = {"convection_j": 0.0, "radiation_j": 0.0, "evaporation_j": 0.0, "net_surface_j": 0.0, "enthalpy_change_j": 0.0}
    pasteur_seconds = 0.0
    elapsed = 0.0
    next_sample = 0.0
    pull_time = None
    pull_temp = None

    def sample(phase):
        vals = t[inside]
        cold = float(vals.min())
        smean = float(np.average(t[surface], weights=geometry.surface_area[surface]))
        record = {
            "time_s": elapsed,
            "coldest_c": cold,
            "probe_c": float(t[probe_idx]),
            "surface_mean_c": smean,
            "pasteurization_equivalent_min": pasteur_seconds / 60.0,
            "phase": phase,
        }
        history["time"].append(elapsed)
        history["cold"].append(cold)
        history["probe"].append(record["probe_c"])
        history["surface"].append(smean)
        history["pasteur"].append(record["pasteurization_equivalent_min"])
        history["phase"].append(phase)
        if progress is not None:
            progress(record)

    def step(step_dt, cooking):
        nonlocal t, wet, pasteur_seconds
        old = t.astype(np.float64)
        rho = density(old)
        cp = heat_capacity(old, denaturation_bump=config.denaturation_bump)
        k = conductivity(old)
        power = _interior_power(old, k, inside, geometry.spacing_m)
        ts = old[surface]
        qnet, qconv, qrad, qlatent, wet_new = _surface_flux(
            ts, boundary, wet[surface], step_dt, cooking,
            config.rest_ambient_c, config.rest_h, config.foil_tent,
        )
        active = exposed[surface]
        qnet = np.where(active, qnet, 0.0)
        qconv = np.where(active, qconv, 0.0)
        qrad = np.where(active, qrad, 0.0)
        qlatent = np.where(active, qlatent, 0.0)
        wet[surface] = np.where(active, wet_new, wet[surface])
        area = geometry.surface_area[surface]
        power[surface] += qnet * area
        delta = np.zeros_like(old)
        delta[inside] = step_dt * power[inside] / (rho[inside] * cp[inside] * cell_volume)
        t[inside] = (old[inside] + delta[inside]).astype(np.float32)
        budget["convection_j"] += float(np.sum(qconv * area) * step_dt)
        budget["radiation_j"] += float(np.sum(qrad * area) * step_dt)
        budget["evaporation_j"] += float(np.sum(qlatent * area) * step_dt)
        budget["net_surface_j"] += float(np.sum(qnet * area) * step_dt)
        budget["enthalpy_change_j"] += float(np.sum(rho[inside] * cp[inside] * cell_volume * (t[inside] - old[inside])))
        cold = float(t[inside].min())
        pasteur_seconds += 10.0 ** ((cold - config.pasteurization_ref_c) / config.pasteurization_z_c) * step_dt

    sample("cook")
    while elapsed < config.max_cook_s - 1e-9:
        step_dt = min(dt, config.max_cook_s - elapsed)
        step(step_dt, True)
        elapsed += step_dt
        if elapsed + 1e-9 >= next_sample + config.sample_interval_s:
            next_sample = elapsed
            sample("cook")
        if float(t[inside].min()) >= config.target_c:
            pull_time = elapsed
            pull_temp = float(t[inside].min())
            if history["time"][-1] < elapsed - 1e-9:
                sample("cook")
            break

    if pull_time is None:
        pull_time = elapsed
        pull_temp = float(t[inside].min())
        pull_reached = False
    else:
        pull_reached = True

    rest_end = elapsed + config.rest_s
    next_sample = elapsed
    while elapsed < rest_end - 1e-9:
        step_dt = min(dt, rest_end - elapsed)
        step(step_dt, False)
        elapsed += step_dt
        if elapsed + 1e-9 >= next_sample + config.sample_interval_s:
            next_sample = elapsed
            sample("rest")
    if history["time"][-1] < elapsed - 1e-9:
        sample("rest")

    after_pull = np.asarray(history["time"]) >= pull_time - 1e-9
    cold_after = np.asarray(history["cold"])[after_pull]
    times_after = np.asarray(history["time"])[after_pull]
    peak_i = int(np.argmax(cold_after))
    peak = float(cold_after[peak_i])
    result_grid = np.full(t.shape, np.nan, dtype=np.float32)
    result_grid[inside] = t[inside]
    wet_fraction = np.zeros(t.shape, dtype=np.float32)
    positive_initial = initial_wet > 0
    wet_fraction[positive_initial] = (wet[positive_initial] / initial_wet[positive_initial]).astype(np.float32)
    budget["relative_balance_error"] = abs(budget["enthalpy_change_j"] - budget["net_surface_j"]) / max(abs(budget["net_surface_j"]), 1.0)

    return SimulationResult(
        np.asarray(history["time"]), np.asarray(history["cold"]), np.asarray(history["probe"]),
        np.asarray(history["surface"]), np.asarray(history["pasteur"]), history["phase"],
        pull_time, pull_reached, peak, float(times_after[peak_i]), peak - float(pull_temp),
        result_grid, wet_fraction, budget, dt, probe_idx,
    )
