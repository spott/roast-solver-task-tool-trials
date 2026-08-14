#!/usr/bin/env python3
"""Reproduce the embedded Robin-sphere resolution and energy check."""
import numpy as np
from roast_solver.geometry import Grid,voxelize,sphere_sdf
from roast_solver.solver import BoundaryConfig,RoastSolver,SolverConfig
from roast_solver.analytics import robin_sphere_center_ratio

def const(value): return lambda t: np.zeros_like(t)+value

radius=.03;rho=1060.;cp=3500.;k=.48;alpha=k/(rho*cp);bi=2.;fo=.10
duration=fo*radius**2/alpha; exact=robin_sphere_center_ratio(bi,fo)
print("n,center_ratio,absolute_error,relative_surface_area,energy_residual_J")
for n in (18,26,36):
    g=voxelize(sphere_sdf(radius),Grid.centered((n,)*3,2.4*radius/n),samples=3)
    s=RoastSolver(g,BoundaryConfig(oven_c=100,h_conv=bi*k/radius,emissivity=0,initial_moisture_kg_m2=0,pan_insulated=False),SolverConfig(initial_c=0,max_dt_s=2),(const(rho),const(cp),const(k)))
    s.run(duration,record_every_s=duration)
    ratio=(100-s.sample().center_c)/100
    print(f"{n},{ratio:.8f},{abs(ratio-exact):.8f},{g.embedded_area/(4*np.pi*radius**2):.8f},{s.ledger.residual_j:.3e}")
