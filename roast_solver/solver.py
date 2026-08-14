"""NumPy 3-D finite-volume reference implementation.

Interior face powers are applied in equal/opposite pairs.  Embedded surface
flux is multiplied by reconstructed physical area and applied once to the owning
cell, making the energy ledger an executable invariant rather than a posteriori
correction.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Callable
import numpy as np

from .properties import meat_properties
from .sdf import GridGeometry, voxelize

SIGMA = 5.670374419e-8
H_FG = 2.30e6
RHO_AIR = 1.10
CP_AIR = 1007.0
LEWIS = 0.90


@dataclass
class SolverConfig:
    preset: str = "roast"
    mass_kg: float = 1.5
    resolution: int = 48
    initial_c: float = 5.0
    oven_c: float = 180.0
    target_c: float = 57.0
    convection: bool = False
    covered: bool = False
    emissivity: float = 0.90
    h_still: float = 10.0
    h_fan: float = 20.0
    moisture_kg_m2: float = 0.25
    ambient_c: float = 22.0
    rest_minutes: float = 30.0
    foil_tent: bool = False
    max_roast_hours: float = 8.0
    sample_seconds: float = 60.0
    timestep_seconds: float | None = None
    denaturation_bump: bool = False
    pasteurization_ref_c: float = 70.0
    pasteurization_z_c: float = 7.0


@dataclass
class EnergyLedger:
    boundary_input_j: float = 0.0
    convection_j: float = 0.0
    radiation_j: float = 0.0
    evaporation_j: float = 0.0
    body_sensible_j: float = 0.0

    @property
    def residual_j(self):
        return self.boundary_input_j - self.body_sensible_j


@dataclass
class SimulationResult:
    config: SolverConfig
    geometry: GridGeometry
    times_s: np.ndarray
    coldest_c: np.ndarray
    probe_c: np.ndarray
    pasteurization_minutes: np.ndarray
    temperature_c: np.ndarray
    lethality_minutes: np.ndarray
    pull_time_s: float | None
    peak_core_c: float
    peak_time_after_pull_s: float
    probe_index: tuple[int, int, int]
    ledger: EnergyLedger
    moisture_kg_m2: np.ndarray

    def summary(self):
        return {
            "pull_minutes": None if self.pull_time_s is None else self.pull_time_s/60,
            "peak_core_c": self.peak_core_c,
            "carryover_c": self.peak_core_c - (float(np.interp(self.pull_time_s, self.times_s, self.probe_c)) if self.pull_time_s is not None else float(self.probe_c[-1])),
            "peak_minutes_after_pull": self.peak_time_after_pull_s/60,
            "pasteurization_minutes_conservative": float(self.pasteurization_minutes[-1]),
            "energy_residual_fraction": abs(self.ledger.residual_j)/max(abs(self.ledger.boundary_input_j), 1.0),
        }


class RoastSolver:
    def __init__(self, config: SolverConfig, geometry: GridGeometry | None = None):
        self.config = config
        self.geometry = geometry or voxelize(config.preset, config.mass_kg, config.resolution)
        g = self.geometry
        self.temperature = np.full(g.inside.shape, config.initial_c, dtype=np.float32)
        self.moisture = np.zeros_like(self.temperature)
        self.moisture[g.surface_mask] = config.moisture_kg_m2
        self.lethality_s = np.zeros_like(self.temperature, dtype=np.float64)
        self.time_s = 0.0
        self.ledger = EnergyLedger()

    @staticmethod
    def saturation_vapour_density(temp_c):
        """Water-vapour density (kg/m³), Buck saturation pressure correlation."""
        t = np.asarray(temp_c, dtype=np.float64)
        pressure = 611.21*np.exp((18.678-t/234.5)*(t/(257.14+t)))
        return pressure/(461.52*(t+273.15))

    def stable_timestep(self, phase: str = "roast") -> float:
        g, c = self.geometry, self.config
        ti = self.temperature[g.inside]
        rho, cp, k = meat_properties(ti, denaturation_bump=c.denaturation_bump)
        dt_diff = 0.82*g.spacing*g.spacing*float(np.min(rho*cp))/(6*float(np.max(k)))
        h = (c.h_fan if c.convection else c.h_still) if phase == "roast" else (4.0 if c.foil_tent else 7.0)
        env = c.oven_c if phase == "roast" else c.ambient_c
        hrad = 4*c.emissivity*SIGMA*(max(env, float(np.max(ti)))+273.15)**3
        surf = g.surface_mask & ~g.pan_contact
        if np.any(surf):
            cap = (rho*cp).min()*g.cell_volume
            dt_bc = 0.60*cap/((h+hrad)*float(np.max(g.surface_area[surf])))
        else:
            dt_bc = dt_diff
        dt = min(dt_diff, dt_bc)
        if c.timestep_seconds is not None:
            dt = min(dt, c.timestep_seconds)
        return max(0.02, dt)

    def _boundary_flux(self, dt: float, phase: str):
        """Return net and component heat fluxes in W/m² on all grid cells."""
        c, g = self.config, self.geometry
        exposed = g.surface_mask & ~g.pan_contact
        ts = self.temperature.astype(np.float64)
        if phase == "roast":
            env = c.oven_c
            h = c.h_fan if c.convection else c.h_still
            emissivity = c.emissivity
            rh = 0.98 if c.covered else 0.15
        else:
            env = c.ambient_c
            h = 4.0 if c.foil_tent else 7.0
            emissivity = c.emissivity*(0.35 if c.foil_tent else 1.0)
            rh = 0.80 if c.foil_tent else 0.50
        conv = h*(env-ts)
        # Evaluating the fourth-power difference at previous T is the standard
        # one-step-lag linearization, with h_rad = eps*sigma*sum of powers.
        rad = emissivity*SIGMA*((env+273.15)**4-(ts+273.15)**4)
        hm = h/(RHO_AIR*CP_AIR*LEWIS**(2/3))
        # ``rh`` is treated as local boundary-layer saturation (not oven RH at
        # 180 °C, where the liquid-water correlation is inapplicable).
        vapour_drive = np.maximum(self.saturation_vapour_density(ts)*(1.0-rh), 0.0)
        mflux = hm*vapour_drive
        # Covered mode is near saturated; this explicit factor also represents
        # poor vapour removal. Every cell depletes its own areal reservoir.
        if c.covered:
            mflux *= 0.05
        mflux = np.minimum(mflux, self.moisture/ max(dt, 1e-12))
        mflux[~exposed] = 0
        self.moisture -= (mflux*dt).astype(np.float32)
        np.maximum(self.moisture, 0, out=self.moisture)
        evap = -H_FG*mflux
        conv[~exposed] = 0; rad[~exposed] = 0; evap[~exposed] = 0
        return conv+rad+evap, conv, rad, evap

    def step(self, dt: float | None = None, phase: str = "roast") -> float:
        g, c = self.geometry, self.config
        dt_lim = self.stable_timestep(phase)
        dt = dt_lim if dt is None else min(dt, dt_lim)
        rho, cp, k = meat_properties(self.temperature, denaturation_bump=c.denaturation_bump)
        capacity = rho.astype(np.float64)*cp.astype(np.float64)*g.cell_volume
        power = np.zeros_like(self.temperature, dtype=np.float64)
        # Conservative interior face exchange (7-point stencil).
        for axis in range(3):
            lo = [slice(None)]*3; hi = [slice(None)]*3
            lo[axis] = slice(None, -1); hi[axis] = slice(1, None)
            lo, hi = tuple(lo), tuple(hi)
            linked = g.inside[lo] & g.inside[hi]
            kl, kh = k[lo].astype(np.float64), k[hi].astype(np.float64)
            kface = 2*kl*kh/np.maximum(kl+kh, 1e-20)
            q = kface*g.spacing*(self.temperature[hi]-self.temperature[lo])*linked
            power[lo] += q
            power[hi] -= q
        net, conv, rad, evap = self._boundary_flux(dt, phase)
        boundary_power = net*g.surface_area
        power += boundary_power
        delta = np.zeros_like(power)
        delta[g.inside] = dt*power[g.inside]/capacity[g.inside]
        self.temperature[g.inside] += delta[g.inside].astype(np.float32)
        self.time_s += dt
        self.lethality_s[g.inside] += dt*10.0**((self.temperature[g.inside]-c.pasteurization_ref_c)/c.pasteurization_z_c)

        area = g.surface_area
        self.ledger.convection_j += float(np.sum(conv*area)*dt)
        self.ledger.radiation_j += float(np.sum(rad*area)*dt)
        self.ledger.evaporation_j += float(np.sum(evap*area)*dt)
        self.ledger.boundary_input_j += float(np.sum(boundary_power)*dt)
        self.ledger.body_sensible_j += float(np.sum(capacity[g.inside]*delta[g.inside]))
        return dt

    def run(self, progress: Callable[[float, float, str], None] | None = None) -> SimulationResult:
        c, g = self.config, self.geometry
        records: list[tuple[float,float,float,float]] = []
        pull_time = None
        # The deepest-SDF cell is source-agnostic, reproducible, and fixed for
        # the entire curve (unlike an instantaneous coldest index).
        probe_idx = tuple(int(v) for v in np.unravel_index(np.argmin(np.where(g.inside, g.phi, np.inf)), self.temperature.shape))
        next_sample = 0.0

        def record():
            vals = np.where(g.inside, self.temperature, np.inf)
            cold_idx = np.unravel_index(np.argmin(vals), vals.shape)
            records.append((self.time_s, float(self.temperature[cold_idx]),
                            float(self.temperature[probe_idx]),
                            float(self.lethality_s[cold_idx]/60)))

        record()
        roast_end = c.max_roast_hours*3600
        while self.time_s < roast_end:
            self.step(min(self.stable_timestep("roast"), roast_end-self.time_s), "roast")
            cold = float(np.min(self.temperature[g.inside]))
            if self.time_s >= next_sample:
                record(); next_sample = self.time_s+c.sample_seconds
                if progress: progress(self.time_s, cold, "roast")
            if cold >= c.target_c:
                pull_time = self.time_s
                break

        pull_probe_temp = float(self.temperature[probe_idx])
        peak = pull_probe_temp
        peak_after = 0.0
        if pull_time is not None:
            rest_end = self.time_s + c.rest_minutes*60
            next_sample = self.time_s
            while self.time_s < rest_end:
                self.step(min(self.stable_timestep("rest"), rest_end-self.time_s), "rest")
                ptemp = float(self.temperature[probe_idx])
                if ptemp > peak:
                    peak, peak_after = ptemp, self.time_s-pull_time
                if self.time_s >= next_sample:
                    record(); next_sample = self.time_s+c.sample_seconds
                    if progress: progress(self.time_s, ptemp, "rest")
        record()
        times = np.asarray([r[0] for r in records])
        cold = np.asarray([r[1] for r in records])
        probe = np.asarray([r[2] for r in records])
        past = np.asarray([r[3] for r in records])
        return SimulationResult(c, g, times, cold, probe, past,
            self.temperature.copy(), self.lethality_s.astype(np.float32)/60,
            pull_time, peak, peak_after, probe_idx, self.ledger, self.moisture.copy())


def simulate(config: SolverConfig, progress=None):
    return RoastSolver(config).run(progress)


def diffuse_dirichlet_box(n=17, steps=100, dt=None, alpha=1.3e-7, spacing=0.005, initial=0.0, boundary=1.0):
    """M2 verification kernel: a cube with exact Dirichlet faces."""
    t = np.full((n,n,n), initial, dtype=np.float64)
    t[[0,-1],:,:] = boundary; t[:,[0,-1],:] = boundary; t[:,:,[0,-1]] = boundary
    dt = dt or 0.8*spacing**2/(6*alpha)
    r = alpha*dt/spacing**2
    for _ in range(steps):
        old = t.copy()
        t[1:-1,1:-1,1:-1] = old[1:-1,1:-1,1:-1] + r*(
            old[2:,1:-1,1:-1]+old[:-2,1:-1,1:-1]+old[1:-1,2:,1:-1]+old[1:-1,:-2,1:-1]+old[1:-1,1:-1,2:]+old[1:-1,1:-1,:-2]-6*old[1:-1,1:-1,1:-1])
    return t
