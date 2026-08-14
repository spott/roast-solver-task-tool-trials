"""Conservative 3-D explicit heat solver with embedded Robin boundaries.

The boundary is represented by an SDF-derived area in each cut-adjacent cell.
Flux uses the SDF distance from cell center to surface as a conduction resistance,
and is deposited as a cell energy source.  Consequently the recorded surface
energy and discrete body enthalpy change agree to floating-point roundoff.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Callable
import numpy as np

from .geometry import GridGeometry
from .properties import meat_properties, thermal_diffusivity

SIGMA = 5.670374419e-8
H_FG = 2.257e6
R_VAPOR = 461.5


@dataclass(frozen=True)
class Environment:
    air_temp_c: float
    wall_temp_c: float | None = None
    h_conv_w_m2k: float = 10.0
    emissivity: float = 0.90
    relative_humidity: float = 0.10
    covered: bool = False
    evaporation: bool = True

    @property
    def wall_c(self) -> float:
        return self.air_temp_c if self.wall_temp_c is None else self.wall_temp_c

    @classmethod
    def oven(cls, temperature_c: float, convection: bool = False,
             covered: bool = False) -> "Environment":
        return cls(temperature_c, temperature_c,
                   20.0 if convection else 10.0, 0.90,
                   1.0 if covered else 0.10, covered, not covered)

    @classmethod
    def rest(cls, ambient_c: float = 22.0, foil_tent: bool = False) -> "Environment":
        return cls(ambient_c, ambient_c, 4.0 if foil_tent else 7.0,
                   0.20 if foil_tent else 0.90, 0.45, foil_tent, False)


@dataclass(frozen=True)
class SolverConfig:
    initial_temp_c: float = 5.0
    moisture_reservoir_kg_m2: float = 0.24
    crust_evaporation_fraction: float = 0.08
    denaturation_bump: bool = False
    cfl_safety: float = 0.82
    pasteurization_reference_c: float = 70.0
    pasteurization_z_c: float = 7.0
    dtype: str = "float32"


@dataclass
class Sample:
    time_s: float
    phase: str
    coldest_c: float
    probe_c: float
    hottest_c: float
    pasteurization_p70_s: float
    surface_energy_j: float
    enthalpy_change_j: float


class Simulation:
    """Mutable explicit simulation. Material properties are lagged one step."""
    def __init__(self, geometry: GridGeometry, config: SolverConfig = SolverConfig()):
        self.geometry = geometry
        self.config = config
        dtype = np.dtype(config.dtype)
        self.temperature_c = np.full(geometry.phi.shape, config.initial_temp_c, dtype=dtype)
        self.temperature_c[~geometry.inside] = config.initial_temp_c
        self.moisture_kg_m2 = np.zeros(geometry.phi.shape, dtype=np.float32)
        self.moisture_kg_m2[geometry.boundary] = config.moisture_reservoir_kg_m2
        self.surface_stage = np.zeros(geometry.phi.shape, dtype=np.uint8)
        self.surface_stage[geometry.pan_mask] = 2
        self.time_s = 0.0
        self.surface_energy_j = 0.0
        self.enthalpy_change_j = 0.0
        self.pasteurization_p70_s = 0.0
        self.samples: list[Sample] = []
        self._probe_index = self._nearest_inside_to_center()
        self._last_surface_power_w = 0.0
        self._last_evaporation_kg = 0.0

    def _nearest_inside_to_center(self):
        indices = np.argwhere(self.geometry.inside)
        center = (np.asarray(self.geometry.inside.shape)-1)/2
        return tuple(indices[np.argmin(np.sum((indices-center)**2, axis=1))])

    @property
    def stable_dt_s(self) -> float:
        h = self.geometry.spacing_m
        # The mixture diffusivity has a shallow interior maximum, so sampling
        # the supported temperature range is safer than checking endpoints.
        temps = np.linspace(-5.0, 250.0, 65)
        alpha = float(np.max(thermal_diffusivity(temps,
                            denaturation_bump=self.config.denaturation_bump)))
        return self.config.cfl_safety*h*h/(6.0*alpha)

    def _saturation_vapor_density(self, temp_c):
        # Buck equation over liquid water, accurate enough for this model range.
        t = np.clip(temp_c, -20.0, 99.0)
        p_sat = 611.21*np.exp((18.678-t/234.5)*(t/(257.14+t)))
        return p_sat/(R_VAPOR*(t+273.15))

    def _boundary_flux(self, env: Environment, rho, cp, k, dt):
        g = self.geometry
        mask = g.boundary & ~g.pan_mask
        q_net = np.zeros(g.phi.shape, dtype=np.float64)
        evap_rate = np.zeros(g.phi.shape, dtype=np.float64)
        if not np.any(mask):
            return q_net, evap_rate
        tc = self.temperature_c.astype(np.float64, copy=False)
        tk = tc+273.15
        tw = env.wall_c+273.15
        hrad = env.emissivity*SIGMA*(tw*tw+tk*tk)*(tw+tk)
        htotal = env.h_conv_w_m2k+hrad
        drive = env.h_conv_w_m2k*(env.air_temp_c-tc)+hrad*(env.wall_c-tc)
        distance = np.clip(-g.phi.astype(np.float64), 0.08*g.spacing_m, 1.5*g.spacing_m)
        q_sensible = drive/(1.0+htotal*distance/np.maximum(k, 1e-6))

        if env.evaporation and not env.covered:
            # Lewis analogy: velocity-like mass transfer coefficient times a
            # vapor-density difference. Each cut cell owns its own reservoir.
            hm = env.h_conv_w_m2k/(1.15*1007.0*0.86**(2/3))
            rho_surface = self._saturation_vapor_density(tc)
            rho_air_sat = self._saturation_vapor_density(env.air_temp_c)
            raw = hm*np.maximum(rho_surface-env.relative_humidity*rho_air_sat, 0.0)
            wet_factor = np.where(self.surface_stage == 0, 1.0,
                                  self.config.crust_evaporation_fraction)
            raw *= wet_factor
            reservoir_cap = self.moisture_kg_m2/maximum_scalar(dt, 1e-12)
            # Prevent the simplified evaporation law from extracting more than
            # 88% of incoming heat during active oven heating.
            energy_cap = 0.88*np.maximum(q_sensible, 0.0)/H_FG
            evap_rate = np.minimum(raw, np.minimum(reservoir_cap, energy_cap))
            evap_rate *= mask
            consumed = evap_rate*dt
            self.moisture_kg_m2 -= consumed.astype(np.float32)
            np.maximum(self.moisture_kg_m2, 0, out=self.moisture_kg_m2)
            depleted = mask & (self.moisture_kg_m2 <= 1e-8)
            self.surface_stage[depleted] = 1
            self._last_evaporation_kg = float(np.sum(consumed*g.surface_area_m2))
        else:
            self._last_evaporation_kg = 0.0
        q_net[mask] = q_sensible[mask]-H_FG*evap_rate[mask]
        return q_net, evap_rate

    def step(self, environment: Environment, dt_s: float | None = None) -> float:
        """Advance one conservative explicit step and return the actual dt."""
        dt = self.stable_dt_s if dt_s is None else min(float(dt_s), self.stable_dt_s)
        if dt <= 0:
            raise ValueError("dt must be positive")
        g = self.geometry
        inside = g.inside
        t = self.temperature_c.astype(np.float64, copy=False)
        rho, cp, k = meat_properties(t, denaturation_bump=self.config.denaturation_bump)
        energy_rate = np.zeros(t.shape, dtype=np.float64)
        area = g.spacing_m**2
        distance = g.spacing_m

        # Each interior face is visited once and contributes equal/opposite power.
        for axis in range(3):
            left = [slice(None)]*3
            right = [slice(None)]*3
            left[axis] = slice(0,-1)
            right[axis] = slice(1,None)
            li, ri = tuple(left), tuple(right)
            links = inside[li] & inside[ri]
            kl, kr = k[li], k[ri]
            kface = 2*kl*kr/np.maximum(kl+kr, 1e-12)
            power = kface*area/distance*(t[ri]-t[li])*links
            energy_rate[li] += power
            energy_rate[ri] -= power

        q_surface, _ = self._boundary_flux(environment, rho, cp, k, dt)
        surface_power_cells = q_surface*g.surface_area_m2
        energy_rate += surface_power_cells
        capacity = rho*cp*g.cell_volume_m3
        delta = np.zeros(t.shape, dtype=np.float64)
        delta[inside] = dt*energy_rate[inside]/capacity[inside]
        self.temperature_c[inside] = (t[inside]+delta[inside]).astype(self.temperature_c.dtype)

        surface_e = float(dt*np.sum(surface_power_cells, dtype=np.float64))
        enthalpy_e = float(np.sum(capacity[inside]*delta[inside], dtype=np.float64))
        self.surface_energy_j += surface_e
        self.enthalpy_change_j += enthalpy_e
        self._last_surface_power_w = surface_e/dt
        cold = float(np.min(t[inside]))
        self.pasteurization_p70_s += dt*10.0**((cold-self.config.pasteurization_reference_c)/
                                             self.config.pasteurization_z_c)
        self.time_s += dt
        return dt

    def record(self, phase: str) -> Sample:
        values = self.temperature_c[self.geometry.inside]
        sample = Sample(self.time_s, phase, float(np.min(values)),
                        float(self.temperature_c[self._probe_index]), float(np.max(values)),
                        self.pasteurization_p70_s, self.surface_energy_j,
                        self.enthalpy_change_j)
        self.samples.append(sample)
        return sample

    def run_for(self, duration_s: float, environment: Environment, phase: str,
                sample_interval_s: float = 60.0,
                stop_when: Callable[["Simulation"], bool] | None = None) -> None:
        end = self.time_s+duration_s
        next_sample = self.time_s
        if not self.samples:
            self.record(phase)
        while self.time_s < end-1e-9:
            dt = min(self.stable_dt_s, end-self.time_s)
            self.step(environment, dt)
            if self.time_s+1e-7 >= next_sample+sample_interval_s:
                self.record(phase)
                next_sample = self.time_s
            if stop_when is not None and stop_when(self):
                break
        if not self.samples or abs(self.samples[-1].time_s-self.time_s) > 1e-6:
            self.record(phase)

    def energy_relative_error(self) -> float:
        scale = max(abs(self.surface_energy_j), abs(self.enthalpy_change_j), 1.0)
        return abs(self.surface_energy_j-self.enthalpy_change_j)/scale

    def middle_slice(self) -> np.ndarray:
        axis = int(np.argmax(self.temperature_c.shape))
        index = self.temperature_c.shape[axis]//2
        return np.take(self.temperature_c, index, axis=axis)


def maximum_scalar(a: float, b: float) -> float:
    return a if a > b else b


def run_roast_and_rest(geometry: GridGeometry, oven: Environment,
                       target_c: float, max_roast_s: float = 6*3600,
                       rest_s: float = 30*60, rest: Environment | None = None,
                       config: SolverConfig = SolverConfig(),
                       sample_interval_s: float = 60.0) -> dict:
    """Run to target coldest temperature, then continue with ambient rest BC."""
    sim = Simulation(geometry, config)
    sim.run_for(max_roast_s, oven, "roast", sample_interval_s,
                stop_when=lambda s: float(np.min(s.temperature_c[s.geometry.inside])) >= target_c)
    pull_time = sim.time_s
    pull_values = sim.temperature_c[geometry.inside]
    pull_core = float(np.min(pull_values))
    pull_index = tuple(np.argwhere(geometry.inside)[np.argmin(pull_values)])
    # Freeze the probe at the pull-time coldest point, as required by the output
    # contract; instantaneous coldest remains a separate curve.
    sim._probe_index = pull_index
    pull_probe = float(sim.temperature_c[pull_index])
    rest = Environment.rest() if rest is None else rest
    sim.run_for(rest_s, rest, "rest", sample_interval_s)
    rest_samples = [s for s in sim.samples if s.phase == "rest"]
    peak = max(rest_samples, key=lambda s: s.probe_c) if rest_samples else sim.samples[-1]
    return {
        "simulation": sim,
        "pull_time_s": pull_time,
        "pull_core_c": pull_core,
        "peak_core_c": peak.probe_c,
        "carryover_c": peak.probe_c-pull_probe,
        "peak_time_after_pull_s": peak.time_s-pull_time,
        "pasteurization_p70_s": sim.pasteurization_p70_s,
        "energy_relative_error": sim.energy_relative_error(),
        "samples": [asdict(s) for s in sim.samples],
    }
