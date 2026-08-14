"""Conservative explicit 3-D solver with embedded SDF boundary fluxes."""
from __future__ import annotations
from dataclasses import dataclass, field
import math
import numpy as np
from .geometry import Geometry
from .properties import (H_FG, food_properties, radiation_coefficient,
                         vapor_mass_fraction)


@dataclass
class BoundaryConfig:
    oven_c: float = 180.0
    convection: bool = False
    covered: bool = False
    emissivity: float = .90
    h_still: float = 10.0
    h_fan: float = 20.0
    moisture_capacity: float = .30  # kg/m2, synthetic baseline
    dry_evaporation_factor: float = .06
    air_relative_humidity: float = .20
    wet_bulb_c: float = 55.0
    pan_insulated: bool = True

    @property
    def h_conv(self):
        return self.h_fan if self.convection else self.h_still


@dataclass
class SimulationConfig:
    initial_c: float = 5.0
    target_c: float = 60.0
    max_cook_s: float = 5*3600
    rest_s: float = 30*60
    ambient_c: float = 22.0
    foil_tent: bool = False
    output_interval_s: float = 30.0
    safety: float = .72
    pasteurization_ref_c: float = 70.0
    pasteurization_z_c: float = 10.0


@dataclass
class EnergyBudget:
    boundary_j: float = 0.0
    sensible_j: float = 0.0
    convective_j: float = 0.0
    radiative_j: float = 0.0
    evaporative_j: float = 0.0

    @property
    def residual_j(self):
        return self.boundary_j - self.sensible_j


@dataclass
class SimulationResult:
    times_s: np.ndarray
    coldest_c: np.ndarray
    probe_c: np.ndarray
    phase: list[str]
    pull_time_s: float | None
    pull_probe_c: float | None
    peak_probe_c: float
    peak_time_s: float
    carryover_c: float
    pasteurization_equivalent_s: float
    probe_index: tuple[int, int, int]
    carryover_probe_index: tuple[int, int, int]
    final_temperature: np.ndarray
    pull_temperature: np.ndarray | None
    moisture_remaining: np.ndarray
    energy: EnergyBudget
    dt_s: float

    def summary(self):
        return {
            "pull_time_s": self.pull_time_s,
            "pull_probe_c": self.pull_probe_c,
            "peak_probe_c": self.peak_probe_c,
            "peak_time_s": self.peak_time_s,
            "carryover_c": self.carryover_c,
            "pasteurization_equivalent_s": self.pasteurization_equivalent_s,
            "probe_index": tuple(int(i) for i in self.probe_index),
            "carryover_probe_index": tuple(int(i) for i in self.carryover_probe_index),
            "dt_s": self.dt_s,
            "energy_residual_fraction": abs(self.energy.residual_j) / max(abs(self.energy.boundary_j), 1.),
        }


def stable_timestep(geometry: Geometry, temp_c, safety=.72):
    _, _, _, alpha = food_properties(temp_c)
    return safety * geometry.grid.spacing**2 / (6.0 * float(np.max(alpha)))


def dirichlet_box_step(temp, alpha, spacing, dt, boundary_c=0.):
    """M2 interior-only seven-point step with fixed box faces.

    This deliberately small constant-property kernel is retained for
    manufactured-solution/convergence tests. The production SDF solver below
    uses the same pairwise stencil but conservative power units.
    """
    t = np.asarray(temp, dtype=np.float64)
    out = t.copy()
    r = alpha*dt/(spacing*spacing)
    if r > 1/6 + 1e-12:
        raise ValueError("explicit 3-D stability limit exceeded")
    out[1:-1,1:-1,1:-1] = t[1:-1,1:-1,1:-1] + r*(
        t[2:,1:-1,1:-1] + t[:-2,1:-1,1:-1] +
        t[1:-1,2:,1:-1] + t[1:-1,:-2,1:-1] +
        t[1:-1,1:-1,2:] + t[1:-1,1:-1,:-2] -
        6*t[1:-1,1:-1,1:-1])
    out[[0,-1],:,:]=boundary_c; out[:,[0,-1],:]=boundary_c; out[:,:,[0,-1]]=boundary_c
    return out.astype(np.float32)


def _internal_energy_rate(temp, geom, conductivity):
    """Net conductive power [W] per cell; pair fluxes cancel exactly."""
    power = np.zeros(temp.shape, dtype=np.float64)
    inside = geom.inside
    h = geom.grid.spacing
    for axis in range(3):
        s0 = [slice(None)]*3; s1 = [slice(None)]*3
        s0[axis] = slice(None,-1); s1[axis] = slice(1,None)
        a, b = tuple(s0), tuple(s1)
        pair = inside[a] & inside[b]
        ka, kb = conductivity[a], conductivity[b]
        kface = 2*ka*kb / np.maximum(ka+kb, 1e-12)
        # k A/h = k*h for a cubic cell.
        flux = kface*h*(temp[b]-temp[a]) * pair
        power[a] += flux
        power[b] -= flux
    return power


def _surface_flux(temp, geom, bc, moisture, dt, rest=False,
                  ambient_c=22., foil_tent=False):
    area = geom.boundary_area.astype(np.float64)
    exposed = (area > 0)
    if bc.pan_insulated and not rest:
        exposed &= ~geom.pan_mask
    cell_t = temp.astype(np.float64)
    _, _, k, _ = food_properties(cell_t)
    if rest:
        env = ambient_c
        hconv = 5.0 if foil_tent else 8.0
        emissivity = .30 if foil_tent else bc.emissivity
        evaporation_scale = .15 if foil_tent else .35
        wall = ambient_c
    else:
        env = bc.oven_c
        hconv = bc.h_conv
        emissivity = bc.emissivity
        evaporation_scale = .02 if bc.covered else 1.0
        wall = bc.oven_c
    hrad = radiation_coefficient(cell_t, wall, emissivity)
    H = hconv + hrad
    teq = (hconv*env + hrad*wall) / np.maximum(H, 1e-12)

    # Lewis analogy mass transfer. A heat-availability cap expresses the wet
    # surface plateau and prevents impossible latent draw from a cold surface.
    rho_air, cp_air, le = 1.15, 1007., .90
    hm = hconv/(rho_air*cp_air*le**(2/3))
    y_surface = vapor_mass_fraction(np.minimum(cell_t, 99.0), 1.0)
    y_air = vapor_mass_fraction(22.0, bc.air_relative_humidity)
    mass_potential = rho_air*hm*np.maximum(y_surface-y_air, 0.)
    available = H*np.maximum(teq-np.maximum(cell_t, bc.wet_bulb_c), 0.)
    latent_potential = np.minimum(H_FG*mass_potential, available)
    wet = moisture > 1e-12
    evap_factor = np.where(wet, 1.0, bc.dry_evaporation_factor)
    latent = evaporation_scale * evap_factor * latent_potential
    # Reservoir limits only the wet-stage component. Once exhausted, the
    # low-rate dry-crust term remains (water diffusing from the interior).
    wet_cap = moisture*H_FG/max(dt, 1e-12)
    latent = np.where(wet, np.minimum(latent, wet_cap), latent)
    latent *= exposed

    # Cell-center-to-interface resistance: solve the lagged linear Robin law
    # and q=k(Ts-Tcell)/d. SDF gives the center/interface distance, bounded to
    # avoid pathological near-zero cut distances.
    d = np.clip(-geom.phi.astype(np.float64), .12*geom.grid.spacing, .85*geom.grid.spacing)
    kd = k/d
    surface_t = (H*teq + kd*cell_t - latent) / np.maximum(H+kd, 1e-12)
    qnet = kd*(surface_t-cell_t) * exposed
    qconv = hconv*(env-surface_t) * exposed
    qrad = hrad*(wall-surface_t) * exposed
    # Reconcile component rounding/linearization exactly with net flux.
    qlatent = qconv + qrad - qnet
    evap_mass = np.where(wet, np.maximum(qlatent, 0.)*dt/H_FG, 0.)
    moisture[:] = np.maximum(moisture - evap_mass, 0.)
    moisture[moisture < 1e-12] = 0.
    return qnet, qconv, qrad, np.maximum(qlatent, 0.), surface_t


def step(temp, geometry, bc, moisture, dt, *, rest=False, ambient_c=22., foil_tent=False):
    """Advance one step; return new field and boundary energy components."""
    # Outside cells are stored as NaN for consumers. Replace them locally so
    # masked vector arithmetic never suffers from NaN*False propagation.
    work_temp = np.where(geometry.inside, temp, 0.).astype(np.float64)
    rho, cp, k, _ = food_properties(work_temp)
    power = _internal_energy_rate(work_temp, geometry, k)
    qnet, qconv, qrad, qevap, _ = _surface_flux(
        work_temp, geometry, bc, moisture, dt, rest, ambient_c, foil_tent)
    area = geometry.boundary_area.astype(np.float64)
    boundary_power = qnet*area
    power += boundary_power
    capacity = rho*cp*geometry.grid.cell_volume
    delta = np.zeros_like(temp, dtype=np.float64)
    delta[geometry.inside] = dt*power[geometry.inside]/capacity[geometry.inside]
    out = work_temp + delta
    out[~geometry.inside] = np.nan
    components = {
        "boundary_j": float(boundary_power.sum()*dt),
        "sensible_j": float((capacity[geometry.inside]*delta[geometry.inside]).sum()),
        "convective_j": float((qconv*area).sum()*dt),
        "radiative_j": float((qrad*area).sum()*dt),
        "evaporative_j": float((qevap*area).sum()*dt),
    }
    return out.astype(np.float32), components


def _center_index(geometry):
    # Uniform Cartesian coordinates are affine in array indices, so this is
    # equivalent to a coordinate-space centroid without three full 3-D meshes.
    indices = np.argwhere(geometry.inside)
    center = indices.mean(axis=0)
    return tuple(indices[np.argmin(((indices-center)**2).sum(axis=1))])


def simulate(geometry: Geometry, boundary=None, config=None, callback=None):
    """Cook until coldest-cell target (or max time), then integrate rest.

    ``callback(dict)`` is invoked at output intervals, making this same API
    suitable for progressive worker execution.
    """
    bc = boundary or BoundaryConfig()
    cfg = config or SimulationConfig()
    temp = np.full(geometry.inside.shape, np.nan, dtype=np.float32)
    temp[geometry.inside] = cfg.initial_c
    moisture = np.zeros_like(temp, dtype=np.float32)
    boundary_cells = geometry.boundary_area > 0
    moisture[boundary_cells] = bc.moisture_capacity
    dt = stable_timestep(geometry, cfg.initial_c, cfg.safety)
    # The geometric-center curve is stable for the entire run. Carryover is
    # separately tracked at the pull-time coldest cell (the conservative
    # stable location requested by the product plan).
    probe = _center_index(geometry)
    carry_probe = probe
    times=[]; colds=[]; probes=[]; phases=[]
    budget = EnergyBudget()
    t=0.; next_output=0.; pulled=False; pull_time=None; pull_temp=None; pull_probe=None
    peak_probe=float(temp[probe]); peak_time=0.
    pasteurization = 0.

    def record(phase):
        times.append(t); colds.append(float(np.nanmin(temp))); probes.append(float(temp[probe])); phases.append(phase)
        if callback:
            callback({"type":"progress", "time_s":t, "phase":phase,
                      "coldest_c":colds[-1], "probe_c":probes[-1]})

    record("cook")
    max_total = cfg.max_cook_s + cfg.rest_s
    while t < max_total - 1e-9:
        rest = pulled
        limit = (pull_time + cfg.rest_s) if pulled else cfg.max_cook_s
        if t >= limit - 1e-9:
            break
        this_dt = min(dt, limit-t)
        temp, e = step(temp, geometry, bc, moisture, this_dt, rest=rest,
                       ambient_c=cfg.ambient_c, foil_tent=cfg.foil_tent)
        t += this_dt
        for key, value in e.items():
            setattr(budget, key, getattr(budget, key)+value)
        cold_now=float(np.nanmin(temp))
        pasteurization += float(10**((cold_now-cfg.pasteurization_ref_c)/cfg.pasteurization_z_c) * this_dt)
        if not pulled and cold_now >= cfg.target_c:
            pulled=True; pull_time=t; pull_temp=temp.copy()
            carry_probe = tuple(np.unravel_index(np.nanargmin(temp), temp.shape))
            pull_probe=float(temp[carry_probe]); peak_probe=pull_probe; peak_time=t
            next_output=t
        if pulled and float(temp[carry_probe]) > peak_probe:
            peak_probe=float(temp[carry_probe]); peak_time=t
        if t+1e-9 >= next_output:
            record("rest" if pulled else "cook")
            next_output += cfg.output_interval_s
    if not times or times[-1] < t-1e-6:
        record("rest" if pulled else "cook")
    p = np.asarray(probes)
    if pulled:
        peak=float(peak_probe); peak_t=float(peak_time); carry=peak-float(pull_probe)
    else:
        peak=float(p[-1]); peak_t=float(times[-1]); carry=0.
    result = SimulationResult(np.asarray(times), np.asarray(colds), p, phases,
                              pull_time, pull_probe, peak, peak_t, carry,
                              pasteurization, probe, carry_probe, temp, pull_temp, moisture,
                              budget, dt)
    if callback:
        callback({"type":"complete", **result.summary()})
    return result
