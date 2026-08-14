"""Finite-volume 3-D reference solver with embedded Robin boundaries.

Temperatures are cell-centred.  Interior links use harmonic conductivity;
cut-surface flux is applied as ``q'' * reconstructed_area`` to the owning cell.
Consequently the reported surface energy and discrete body enthalpy change are
identical to floating-point roundoff for every step (including evaporation).
Properties and radiation are lagged one explicit step (Picard linearization).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable
import numpy as np

from .geometry import GridGeometry
from .properties import (H_FG, density, heat_capacity, conductivity,
                         diffusivity, linearized_radiation,
                         saturation_vapor_density)


@dataclass
class Boundary:
    air_c: float = 180.0
    wall_c: float | None = None
    h_conv: float = 10.0
    emissivity: float = .90
    covered: bool = False
    relative_humidity: float = .10
    moisture_kg_m2: float = .25
    pan_insulated: bool = True
    crust_h_factor: float = .72

    def __post_init__(self):
        if self.wall_c is None:
            self.wall_c = self.air_c


@dataclass
class StepAccounting:
    surface_j: float
    enthalpy_j: float
    convective_j: float
    radiative_j: float
    evaporative_j: float


@dataclass
class SimulationResult:
    time_s: np.ndarray
    coldest_c: np.ndarray
    probe_c: np.ndarray
    pasteurization_minutes: np.ndarray
    pull_time_s: float | None
    carryover_c: float
    peak_c: float
    peak_time_after_pull_s: float
    final_field_c: np.ndarray
    center_slice_c: np.ndarray
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "time_s": self.time_s.tolist(), "coldest_c": self.coldest_c.tolist(),
            "probe_c": self.probe_c.tolist(),
            "pasteurization_minutes": self.pasteurization_minutes.tolist(),
            "pull_time_s": self.pull_time_s, "carryover_c": self.carryover_c,
            "peak_c": self.peak_c, "peak_time_after_pull_s": self.peak_time_after_pull_s,
            "center_slice_c": np.nan_to_num(self.center_slice_c, nan=-999).tolist(),
            "metadata": self.metadata,
        }


class Solver:
    def __init__(self, geometry: GridGeometry, initial_c=5.0, boundary: Boundary | None=None):
        self.g = geometry
        self.boundary = boundary or Boundary()
        self.temperature = np.full(geometry.inside.shape, float(initial_c), dtype=np.float32)
        self.temperature[~geometry.inside] = np.nan
        self.surface_temperature = np.full(geometry.inside.shape, float(initial_c), dtype=np.float32)
        self.moisture = np.zeros(geometry.inside.shape, dtype=np.float32)
        self.moisture[geometry.boundary_area > 0] = self.boundary.moisture_kg_m2
        self.time_s = 0.0
        self.surface_energy_j = 0.0
        self.enthalpy_j = 0.0

    def stable_dt(self, safety=.82):
        a=float(np.max(diffusivity(self.temperature[self.g.inside])))
        return safety*self.g.dx*self.g.dx/(6*a)

    def _boundary_flux(self, dt, bc):
        mask=(self.g.boundary_area>0) & self.g.inside
        flux_mask=mask & (~self.g.pan_mask if bc.pan_insulated else True)
        tc=np.where(mask,self.temperature,0).astype(np.float64)
        old_ts=np.where(mask,self.surface_temperature,tc)
        wet=self.moisture>1e-9
        hconv=np.where(wet,bc.h_conv,bc.h_conv*bc.crust_h_factor)
        hrad=linearized_radiation(bc.emissivity,bc.wall_c,old_ts)
        # A foil/covered vessel suppresses evaporation but does not remove wall
        # radiation; users can reduce emissivity during the separate rest BC.
        htot=hconv+hrad
        source=hconv*bc.air_c+hrad*bc.wall_c

        evap=np.zeros(tc.shape,dtype=np.float64)
        if not bc.covered:
            # Lewis analogy. rho_air*cp_air ~= 1200 J m-3 K-1, Le=.90.
            hm=hconv/(1.20*1005.0*0.90**(2/3))
            drive=np.maximum(saturation_vapor_density(old_ts)-
                             bc.relative_humidity*saturation_vapor_density(min(bc.air_c,30.0)),0)
            mdot=hm*drive
            available=self.moisture/np.maximum(dt,1e-12)
            mdot=np.minimum(mdot,available)
            evap=np.where(wet & flux_mask,mdot*H_FG,0)
            self.moisture[flux_mask] -= (mdot[flux_mask]*dt).astype(np.float32)
            np.maximum(self.moisture,0,out=self.moisture)

        k=conductivity(tc)
        # Half-cell conduction resistance between centre and true surface.
        denom=1.0+htot*(.5*self.g.dx)/np.maximum(k,.05)
        q=(source-htot*tc-evap)/denom
        q=np.where(flux_mask,q,0)
        ts=tc+q*(.5*self.g.dx)/np.maximum(k,.05)
        self.surface_temperature[mask]=ts[mask].astype(np.float32)
        # Components below are diagnostic allocations at the reconstructed Ts.
        conv=np.where(mask,hconv*(bc.air_c-ts),0)
        rad=np.where(mask,hrad*(bc.wall_c-ts),0)
        latent=np.where(mask,-evap,0)
        if bc.pan_insulated:
            conv=np.where(self.g.pan_mask,0,conv)
            rad=np.where(self.g.pan_mask,0,rad)
            latent=np.where(self.g.pan_mask,0,latent)
        return q,conv,rad,latent

    def step(self, dt: float | None=None, boundary: Boundary | None=None) -> StepAccounting:
        bc=boundary or self.boundary
        limit=self.stable_dt()
        if dt is None: dt=limit
        if dt > limit*(1+1e-6):
            raise ValueError(f"dt={dt:g}s exceeds explicit stability limit {limit:g}s")
        t=self.temperature.astype(np.float64)
        inside=self.g.inside
        k=conductivity(t)
        power=np.zeros(t.shape,dtype=np.float64)
        # Every internal face is visited exactly once.
        for ax in range(3):
            lo=[slice(None)]*3; hi=[slice(None)]*3
            lo[ax]=slice(0,-1); hi[ax]=slice(1,None); lo=tuple(lo); hi=tuple(hi)
            both=inside[lo]&inside[hi]
            kl=k[lo]; kh=k[hi]
            conductance=(2*kl*kh/(kl+kh+1e-30))*self.g.dx
            p=np.where(both,conductance*(t[hi]-t[lo]),0)
            power[lo]+=p; power[hi]-=p
        q,conv,rad,evap=self._boundary_flux(dt,bc)
        boundary_power=q*self.g.boundary_area
        power+=boundary_power
        rho=density(t); cp=heat_capacity(t); cell_volume=self.g.dx**3
        dtemp=np.zeros(t.shape)
        dtemp[inside]=dt*power[inside]/(rho[inside]*cp[inside]*cell_volume)
        self.temperature[inside]=(t[inside]+dtemp[inside]).astype(np.float32)
        sj=float(dt*boundary_power.sum())
        hj=float(np.sum(rho[inside]*cp[inside]*cell_volume*dtemp[inside]))
        self.surface_energy_j+=sj; self.enthalpy_j+=hj; self.time_s+=dt
        a=self.g.boundary_area
        return StepAccounting(sj,hj,float(dt*np.sum(conv*a)),
                              float(dt*np.sum(rad*a)),float(dt*np.sum(evap*a)))


def simulate_roast(geometry: GridGeometry, initial_c=5.0, oven_c=180.0,
                   target_c=60.0, convection=False, covered=False,
                   rest_minutes=30.0, max_cook_hours=8.0, sample_seconds=60.0,
                   callback: Callable[[dict],None] | None=None) -> SimulationResult:
    """Cook to target, switch to room BC, and integrate carryover/rest.

    Pasteurization is the conservative model integral at the instantaneous
    coldest cell, using Tref=70 C and z=7 C. It is an engineering output, not a
    food-safety guarantee; handling and organism assumptions remain external.
    """
    cook=Boundary(air_c=oven_c,h_conv=20.0 if convection else 10.0,covered=covered)
    s=Solver(geometry,initial_c,cook)
    dt=min(s.stable_dt(),5.0)
    times=[]; cold=[]; probe=[]; dose=[]
    next_sample=0.; integral_min=0.; pulled=None; probe_index=None
    phase="cook"; rest=Boundary(air_c=22.,wall_c=22.,h_conv=7.,emissivity=.85,
                                covered=covered,relative_humidity=.45,
                                moisture_kg_m2=cook.moisture_kg_m2)
    max_end=max_cook_hours*3600
    end=None
    while s.time_s < (end if end is not None else max_end):
        active=cook if phase=="cook" else rest
        local_dt=min(dt,(end-s.time_s) if end is not None else dt)
        if local_dt<=1e-9: break
        s.step(local_dt,active)
        vals=s.temperature[geometry.inside]
        cmin=float(vals.min())
        integral_min += 10**((cmin-70.)/7.)*local_dt/60.
        if phase=="cook" and cmin>=target_c:
            pulled=s.time_s; phase="rest"; end=pulled+rest_minutes*60
            probe_index=np.unravel_index(np.nanargmin(s.temperature),s.temperature.shape)
        if s.time_s+1e-6>=next_sample or (end and s.time_s>=end-1e-6):
            p=cmin if probe_index is None else float(s.temperature[probe_index])
            times.append(s.time_s); cold.append(cmin); probe.append(p); dose.append(integral_min)
            payload={"time_s":s.time_s,"coldest_c":cmin,"probe_c":p,
                     "pasteurization_minutes":integral_min,"phase":phase}
            if callback: callback(payload)
            next_sample+=sample_seconds
    arrp=np.asarray(probe)
    if pulled is not None:
        post=np.asarray(times)>=pulled
        pp=arrp[post]; pt=np.asarray(times)[post]
        peak=float(pp.max()); peak_at=float(pt[np.argmax(pp)]-pulled)
        carry=peak-float(arrp[np.nonzero(post)[0][0]])
    else:
        peak=float(arrp[-1]); peak_at=0.; carry=0.
    center=geometry.inside.shape[2]//2
    sl=np.where(geometry.inside[:,:,center],s.temperature[:,:,center],np.nan)
    return SimulationResult(np.asarray(times),np.asarray(cold),arrp,np.asarray(dose),
                            pulled,carry,peak,peak_at,s.temperature.copy(),sl,
                            {"dx_m":geometry.dx,"cells":int(geometry.inside.sum()),
                             "preset_volume_m3":geometry.volume,
                             "surface_area_m2":geometry.surface_area,
                             "calibration":"synthetic/literature-model only",
                             "reached_target":pulled is not None})
