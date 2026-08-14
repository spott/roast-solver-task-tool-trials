"""Conservative explicit 3-D heat solver with embedded surface fluxes.

Cut cells smaller than 25% of a voxel use a standard small-cell stabilization:
their thermal volume is merged up to 25% while all shared-face and embedded
areas remain geometric.  The same effective volume is used in updates and the
energy ledger, so conservation is exact for the discrete model.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable
import numpy as np
from .geometry import VoxelGeometry
from . import properties

SIGMA=5.670374419e-8
H_FG=2.30e6

@dataclass
class BoundaryConfig:
    oven_c: float=180.0
    wall_c: float|None=None
    h_conv: float=10.0
    emissivity: float=.90
    covered: bool=False
    initial_moisture_kg_m2: float=.25
    vapor_density_kg_m3: float=.008
    pan_insulated: bool=True
    ambient_c: float=22.0
    rest_h: float=7.0
    foil_tent: bool=False

@dataclass
class SolverConfig:
    initial_c: float=5.0
    safety: float=.35
    max_dt_s: float=5.0
    record_every_s: float=30.0

@dataclass
class EnergyLedger:
    convection_j: float=0.0
    radiation_j: float=0.0
    evaporation_j: float=0.0
    net_surface_j: float=0.0
    discrete_enthalpy_j: float=0.0
    residual_j: float=0.0

@dataclass
class Sample:
    time_s: float
    coldest_c: float
    center_c: float
    mean_c: float
    pasteurization: float

class RoastSolver:
    def __init__(self, geometry: VoxelGeometry, boundary: BoundaryConfig|None=None,
                 config: SolverConfig|None=None,
                 property_functions: tuple[Callable,Callable,Callable]|None=None):
        self.geometry=geometry
        self.boundary=boundary or BoundaryConfig()
        self.config=config or SolverConfig()
        self.temperature=np.full(geometry.grid.shape,self.config.initial_c,dtype=np.float64)
        self.temperature[~geometry.active]=np.nan
        self.moisture=np.where(geometry.surface_area>0,self.boundary.initial_moisture_kg_m2,0.0)
        self.crust=np.zeros(geometry.grid.shape,dtype=bool)
        self.time_s=0.0
        self.ledger=EnergyLedger()
        self.pasteurization=0.0
        self._rho,self._cp,self._k = property_functions or (properties.density,properties.heat_capacity,properties.conductivity)
        self._center_index=self._find_center()

    def _find_center(self):
        idx=np.argwhere(self.geometry.active)
        center=(np.asarray(self.geometry.grid.shape)-1)/2
        return tuple(idx[np.argmin(np.sum((idx-center)**2,axis=1))])

    def _face_conduction(self,k: np.ndarray) -> tuple[np.ndarray,np.ndarray]:
        g=self.geometry; h=g.grid.spacing
        power=np.zeros(g.grid.shape,dtype=np.float64)
        conductance_sum=np.zeros_like(power)
        for axis in range(3):
            lo=[slice(None)]*3; hi=[slice(None)]*3
            lo[axis]=slice(0,-1); hi[axis]=slice(1,None)
            lo=tuple(lo); hi=tuple(hi)
            valid=g.active[lo]&g.active[hi]
            # Average the independently sampled copies of the same geometric face.
            frac=.5*(g.face_fraction[2*axis+1][lo]+g.face_fraction[2*axis][hi])
            kk=2*k[lo]*k[hi]/np.maximum(k[lo]+k[hi],1e-12)
            conductance=kk*frac*h
            conductance=np.where(valid,conductance,0.0)
            delta=np.where(valid,self.temperature[hi],0.0)-np.where(valid,self.temperature[lo],0.0)
            q=conductance*delta
            power[lo]+=q; power[hi]-=q
            conductance_sum[lo]+=conductance; conductance_sum[hi]+=conductance
        return power,conductance_sum

    @staticmethod
    def _saturation_vapor_density(temp_c):
        # Antoine correlation is only used on the liquid-side 0--99 C range.
        t=np.clip(temp_c,0,99)
        p=133.322*10**(8.07131-1730.63/(233.426+t))
        return p/(461.5*(t+273.15))

    def _surface_flux(self, mode: str, dt: float|None) -> tuple[np.ndarray,dict[str,float],np.ndarray]:
        g=self.geometry; b=self.boundary; area=g.surface_area
        surf=area>1e-15; t=np.where(surf,self.temperature,0.0)
        if mode=="roast":
            air=b.oven_c; wall=b.oven_c if b.wall_c is None else b.wall_c
            h=b.h_conv; eps=b.emissivity
        elif mode=="rest":
            air=wall=b.ambient_c; h=b.rest_h*(.55 if b.foil_tent else 1.0)
            eps=b.emissivity*(.35 if b.foil_tent else 1.0)
        else: raise ValueError("mode must be 'roast' or 'rest'")
        qconv=h*(air-t)
        # This secant form is algebraically T^4 radiation evaluated at lagged T.
        tk=t+273.15; wk=wall+273.15
        hrad=eps*SIGMA*(wk+tk)*(wk*wk+tk*tk)
        qrad=hrad*(wall-t)
        evap=np.zeros_like(t)
        wet=surf&(self.moisture>0)&(~g.pan_mask)
        if np.any(wet):
            hm=h/(1.18*1007.0*.9**(2/3))
            potential=hm*np.maximum(self._saturation_vapor_density(t)-b.vapor_density_kg_m3,0.0)
            if b.covered: potential*=.02
            if mode=="rest": potential*=.35
            # Energy-limited wet-surface closure; 30 C is a synthetic wet-bulb anchor.
            available=np.maximum(qconv+qrad,0.0)+25.0*np.maximum(t-30.0,0.0)
            evap=np.where(wet,np.minimum(H_FG*potential,available),0.0)
            if dt is not None:
                evap=np.minimum(evap,self.moisture*H_FG/dt)
        qnet=qconv+qrad-evap
        if b.pan_insulated:
            qnet=np.where(g.pan_mask,0.0,qnet)
            qconv=np.where(g.pan_mask,0.0,qconv); qrad=np.where(g.pan_mask,0.0,qrad); evap=np.where(g.pan_mask,0.0,evap)
        if dt is not None:
            self.moisture=np.maximum(0.0,self.moisture-evap*dt/H_FG)
            self.crust |= surf&(self.moisture<=1e-12)
        totals={"convection":float(np.sum(qconv*area)),"radiation":float(np.sum(qrad*area)),
                "evaporation":float(np.sum(evap*area)),"net":float(np.sum(qnet*area))}
        return qnet,totals,hrad

    def stable_dt(self,mode: str="roast") -> float:
        active=self.geometry.active; t=np.where(active,self.temperature,self.config.initial_c)
        rho=self._rho(t); cp=self._cp(t); k=self._k(t)
        _,gsum=self._face_conduction(k)
        _,_,hrad=self._surface_flux(mode,None)
        b=self.boundary
        h=b.h_conv if mode=="roast" else b.rest_h
        # 25 W/m2K bounds the staged evaporation closure's local slope.
        gsum += self.geometry.surface_area*(h+hrad+25.0)
        cap=rho*cp*self.geometry.effective_volume_fraction*self.geometry.grid.spacing**3
        ratios=np.where(active,cap/np.maximum(gsum,1e-20),np.inf)
        return min(self.config.max_dt_s,self.config.safety*float(np.min(ratios)))

    def step(self,dt: float|None=None,mode: str="roast") -> float:
        if dt is None: dt=self.stable_dt(mode)
        active=self.geometry.active; old=self.temperature.copy()
        t=np.where(active,old,self.config.initial_c)
        rho=self._rho(t); cp=self._cp(t); k=self._k(t)
        power,_=self._face_conduction(k)
        qsurf,totals,_=self._surface_flux(mode,dt)
        power += qsurf*self.geometry.surface_area
        cap=rho*cp*self.geometry.effective_volume_fraction*self.geometry.grid.spacing**3
        self.temperature[active]=old[active]+dt*power[active]/cap[active]
        delta=float(np.sum(cap[active]*(self.temperature[active]-old[active])))
        expected=totals["net"]*dt
        self.ledger.convection_j+=totals["convection"]*dt
        self.ledger.radiation_j+=totals["radiation"]*dt
        self.ledger.evaporation_j+=totals["evaporation"]*dt
        self.ledger.net_surface_j+=expected
        self.ledger.discrete_enthalpy_j+=delta
        self.ledger.residual_j+=delta-expected
        cold=float(np.nanmin(self.temperature)); self.pasteurization += 10**((cold-70.0)/7.5)*dt
        self.time_s+=dt
        return dt

    def sample(self) -> Sample:
        a=self.geometry.active; t=self.temperature
        return Sample(self.time_s,float(np.nanmin(t)),float(t[self._center_index]),float(np.mean(t[a])),self.pasteurization)

    def run(self,duration_s: float,mode: str="roast",record_every_s: float|None=None) -> list[Sample]:
        interval=record_every_s or self.config.record_every_s
        end=self.time_s+duration_s; next_record=self.time_s
        out=[]
        while self.time_s<end-1e-9:
            if self.time_s>=next_record-1e-9:
                out.append(self.sample()); next_record+=interval
            self.step(min(self.stable_dt(mode),end-self.time_s),mode)
        out.append(self.sample())
        return out

    def run_to_target(self,target_c: float,max_roast_s: float=8*3600,rest_s: float=1800) -> dict:
        roast=[]; next_record=0.0
        while self.time_s<max_roast_s and self.sample().coldest_c<target_c:
            if self.time_s>=next_record:
                roast.append(self.sample()); next_record+=self.config.record_every_s
            self.step(mode="roast")
        roast.append(self.sample()); pull=self.sample(); pull_time=self.time_s
        rest=self.run(rest_s,"rest")
        peak=max(rest,key=lambda s:s.coldest_c)
        return {"roast":roast,"rest":rest,"pull":pull,"pull_time_s":pull_time,
                "peak":peak,"carryover_c":peak.coldest_c-pull.coldest_c,
                "pasteurization":self.pasteurization}

def solve_dirichlet_cube(initial: np.ndarray,alpha: float,spacing: float,dt: float,steps: int,
                         boundary_value: float=0.0) -> np.ndarray:
    """M2 interior-only 7-point reference kernel with fixed box boundaries."""
    u=np.asarray(initial,dtype=np.float64).copy()
    r=alpha*dt/(spacing*spacing)
    if r>1/6+1e-12: raise ValueError("unstable explicit timestep")
    for _ in range(steps):
        v=u.copy()
        v[1:-1,1:-1,1:-1]=u[1:-1,1:-1,1:-1]+r*(
            u[2:,1:-1,1:-1]+u[:-2,1:-1,1:-1]+u[1:-1,2:,1:-1]+u[1:-1,:-2,1:-1]+
            u[1:-1,1:-1,2:]+u[1:-1,1:-1,:-2]-6*u[1:-1,1:-1,1:-1])
        v[[0,-1],:,:]=boundary_value;v[:,[0,-1],:]=boundary_value;v[:,:,[0,-1]]=boundary_value
        u=v
    return u
