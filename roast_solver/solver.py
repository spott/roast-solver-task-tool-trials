"""Conservative 3-D explicit finite-volume reference solver."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable
import numpy as np

from .boundary import BoundaryConditions, FluxResult, SurfaceState, surface_flux
from .geometry import Geometry, make_geometry
from .properties import meat_properties, thermal_diffusivity


@dataclass(frozen=True)
class SolverConfig:
    initial_c: float = 5.0
    target_c: float = 57.0
    oven: BoundaryConditions = field(default_factory=lambda: BoundaryConditions.oven(180.0))
    rest: BoundaryConditions = field(default_factory=BoundaryConditions.rest)
    max_cook_s: float = 4.0 * 3600.0
    rest_s: float = 30.0 * 60.0
    sample_interval_s: float = 30.0
    safety: float = 0.72
    pasteurization_reference_c: float = 70.0
    pasteurization_z_c: float = 10.0
    denaturation_bump: bool = False


@dataclass(frozen=True)
class HistoryPoint:
    time_s: float
    phase: str
    coldest_c: float
    probe_c: float
    hottest_c: float
    pasteurization_minutes: float
    surface_moisture_fraction: float


@dataclass
class EnergyAccount:
    boundary_j: float = 0.0
    convective_j: float = 0.0
    radiative_j: float = 0.0
    evaporative_j: float = 0.0
    sensible_j: float = 0.0

    @property
    def residual_j(self) -> float:
        return self.sensible_j - self.boundary_j


@dataclass
class SimulationResult:
    geometry: Geometry
    config: SolverConfig
    history: list[HistoryPoint]
    final_temperature_c: np.ndarray
    pull_field_c: np.ndarray | None
    pull_time_s: float | None
    peak_probe_c: float
    peak_time_after_pull_s: float
    pasteurization_minutes: float
    evaporated_kg: float
    energy: EnergyAccount

    @property
    def carryover_c(self) -> float:
        if self.pull_time_s is None or not self.history:
            return 0.0
        pull_probe = min(self.history, key=lambda p: abs(p.time_s - self.pull_time_s)).probe_c
        return self.peak_probe_c - pull_probe


class ExplicitSolver:
    """Stateful solver suitable for batch use or progressive stepping."""

    def __init__(self, geometry: Geometry, config: SolverConfig):
        self.geometry = geometry
        self.config = config
        self.temperature = np.full(geometry.grid.shape, config.initial_c, dtype=np.float32)
        self.temperature[~geometry.inside] = np.nan
        self.surface = SurfaceState.initialize(
            geometry.area, config.initial_c, config.oven.moisture_reservoir_kg_m2
        )
        alpha_bound = float(np.max(thermal_diffusivity(np.asarray([0.0, 100.0]))))
        self.dt = config.safety * geometry.grid.spacing**2 / (6.0 * alpha_bound)
        self.phase = "cook"
        self.time_s = 0.0
        self.phase_time_s = 0.0
        self.pull_time_s: float | None = None
        self.pull_field: np.ndarray | None = None
        self.pasteurization_minutes = 0.0
        self.energy = EnergyAccount()
        self.history: list[HistoryPoint] = []
        self._next_sample = 0.0
        self._initial_moisture = float(np.sum(self.surface.moisture_kg_m2 * geometry.area))
        self._probe_index = np.unravel_index(np.argmin(geometry.phi), geometry.phi.shape)
        self.peak_probe_c = config.initial_c
        self.peak_time_after_pull_s = 0.0
        self._record()

    @property
    def done(self) -> bool:
        return self.phase == "done"

    @property
    def current_bc(self) -> BoundaryConditions:
        return self.config.oven if self.phase == "cook" else self.config.rest

    def _conduction_power(self, conductivity: np.ndarray) -> np.ndarray:
        """Pairwise face fluxes; each internal contribution is exactly antisymmetric."""
        t = self.temperature
        inside = self.geometry.inside
        h = self.geometry.grid.spacing
        power = np.zeros(t.shape, dtype=np.float64)
        for axis in range(3):
            lo = [slice(None)] * 3
            hi = [slice(None)] * 3
            lo[axis] = slice(0, -1)
            hi[axis] = slice(1, None)
            lo_t, hi_t = tuple(lo), tuple(hi)
            face = inside[lo_t] & inside[hi_t]
            k0, k1 = conductivity[lo_t], conductivity[hi_t]
            k_face = 2.0 * k0 * k1 / np.maximum(k0 + k1, 1e-12)
            q_w = np.where(face, k_face * (t[hi_t] - t[lo_t]) * h, 0.0)
            power[lo_t] += q_w
            power[hi_t] -= q_w
        return power

    def step(self, requested_dt_s: float | None = None) -> FluxResult | None:
        if self.done:
            return None
        remaining = (
            self.config.max_cook_s - self.phase_time_s
            if self.phase == "cook"
            else self.config.rest_s - self.phase_time_s
        )
        dt = min(self.dt if requested_dt_s is None else requested_dt_s, remaining)
        if dt <= 1e-12:
            self._finish_or_rest()
            return None

        inside = self.geometry.inside
        old = self.temperature.copy()
        rho, cp, conductivity = meat_properties(old, denaturation_bump=self.config.denaturation_bump)
        # Exterior NaNs never participate in a face, but finite values avoid
        # warning propagation in vectorized harmonic averages.
        rho = np.where(inside, rho, 1.0)
        cp = np.where(inside, cp, 1.0)
        conductivity = np.where(inside, conductivity, 0.0)
        power = self._conduction_power(conductivity)
        flux = surface_flux(
            old,
            conductivity,
            self.geometry.phi,
            self.geometry.grid.spacing,
            self.geometry.area,
            self.geometry.pan_contact,
            self.surface,
            self.current_bc,
            dt,
        )
        surface_power = flux.net_w_m2.astype(np.float64) * self.geometry.area
        power += surface_power
        capacity = rho * cp * self.geometry.grid.spacing**3
        updated = old.astype(np.float64)
        updated[inside] += dt * power[inside] / capacity[inside]
        self.temperature[inside] = updated[inside].astype(np.float32)

        boundary_j = float(np.sum(surface_power)) * dt
        self.energy.boundary_j += boundary_j
        self.energy.convective_j += float(np.sum(flux.convective_w_m2 * self.geometry.area)) * dt
        self.energy.radiative_j += float(np.sum(flux.radiative_w_m2 * self.geometry.area)) * dt
        self.energy.evaporative_j += float(np.sum(flux.evaporative_w_m2 * self.geometry.area)) * dt
        self.energy.sensible_j += float(np.sum(capacity[inside] * (self.temperature[inside] - old[inside])))

        coldest = float(np.min(self.temperature[inside]))
        self.pasteurization_minutes += (
            dt / 60.0
            * 10.0
            ** np.clip(
                (coldest - self.config.pasteurization_reference_c) / self.config.pasteurization_z_c,
                -12.0,
                4.0,
            )
        )
        self.time_s += dt
        self.phase_time_s += dt
        probe = float(self.temperature[self._probe_index])
        if self.pull_time_s is None:
            self.peak_probe_c = max(self.peak_probe_c, probe)
        elif probe >= self.peak_probe_c:
            self.peak_probe_c = probe
            self.peak_time_after_pull_s = self.time_s - self.pull_time_s

        if self.phase == "cook" and coldest >= self.config.target_c:
            self.pull_time_s = self.time_s
            self.pull_field = self.temperature.copy()
            self.peak_probe_c = probe
            self.peak_time_after_pull_s = 0.0
            self.phase = "rest"
            self.phase_time_s = 0.0
            self._record(force=True)
        elif self.phase == "cook" and self.phase_time_s >= self.config.max_cook_s - 1e-9:
            self.phase = "done"
            self._record(force=True)
        elif self.phase == "rest" and self.phase_time_s >= self.config.rest_s - 1e-9:
            self.phase = "done"
            self._record(force=True)
        elif self.time_s >= self._next_sample - 1e-9:
            self._record()
        return flux

    def _finish_or_rest(self) -> None:
        if self.phase == "cook":
            self.phase = "done"
        else:
            self.phase = "done"
        self._record(force=True)

    def _record(self, force: bool = False) -> None:
        inside_t = self.temperature[self.geometry.inside]
        moisture = float(np.sum(self.surface.moisture_kg_m2 * self.geometry.area))
        fraction = moisture / self._initial_moisture if self._initial_moisture > 0 else 0.0
        point = HistoryPoint(
            self.time_s,
            self.phase,
            float(np.min(inside_t)),
            float(self.temperature[self._probe_index]),
            float(np.max(inside_t)),
            float(self.pasteurization_minutes),
            fraction,
        )
        if force and self.history and abs(self.history[-1].time_s - point.time_s) < 1e-7:
            self.history[-1] = point
        else:
            self.history.append(point)
        self._next_sample = self.time_s + self.config.sample_interval_s

    def run(self, progress: Callable[["ExplicitSolver"], None] | None = None, chunk_steps: int = 100) -> SimulationResult:
        steps = 0
        while not self.done:
            self.step()
            steps += 1
            if progress is not None and steps % chunk_steps == 0:
                progress(self)
        return SimulationResult(
            self.geometry,
            self.config,
            self.history,
            self.temperature.copy(),
            None if self.pull_field is None else self.pull_field.copy(),
            self.pull_time_s,
            self.peak_probe_c,
            self.peak_time_after_pull_s,
            self.pasteurization_minutes,
            self.surface.evaporated_kg,
            self.energy,
        )


def simulate_preset(
    preset: str = "roast",
    mass_kg: float = 1.5,
    grid_size: int = 41,
    config: SolverConfig | None = None,
) -> SimulationResult:
    geometry = make_geometry(preset, mass_kg, grid_size=grid_size)
    return ExplicitSolver(geometry, config or SolverConfig()).run()


def explicit_dirichlet_box(
    initial: np.ndarray,
    spacing_m: float,
    diffusivity_m2_s: float,
    boundary_c: float,
    dt_s: float,
    steps: int,
) -> np.ndarray:
    """Constant-property 7-point kernel used by the M2 convergence tests."""
    t = np.asarray(initial, dtype=np.float64).copy()
    r = diffusivity_m2_s * dt_s / spacing_m**2
    if r > 1.0 / 6.0:
        raise ValueError("unstable explicit time step")
    for _ in range(steps):
        t[[0, -1], :, :] = boundary_c
        t[:, [0, -1], :] = boundary_c
        t[:, :, [0, -1]] = boundary_c
        old = t.copy()
        t[1:-1, 1:-1, 1:-1] = old[1:-1, 1:-1, 1:-1] + r * (
            old[2:, 1:-1, 1:-1] + old[:-2, 1:-1, 1:-1]
            + old[1:-1, 2:, 1:-1] + old[1:-1, :-2, 1:-1]
            + old[1:-1, 1:-1, 2:] + old[1:-1, 1:-1, :-2]
            - 6.0 * old[1:-1, 1:-1, 1:-1]
        )
    return t
