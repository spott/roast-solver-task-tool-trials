#!/usr/bin/env python3
"""Generate deterministic synthetic Python→Rust regression anchors.

These are numerical fixtures, not measurements and not calibration data.
Regenerate from repository root with PYTHONPATH=python python ...
"""
from pathlib import Path
import numpy as np
from roast_solver.geometry import make_geometry
from roast_solver.properties import density, heat_capacity, conductivity
from roast_solver.solver import RoastSolver, BoundaryConfig, SolverConfig

ROOT=Path(__file__).resolve().parents[2]
rows=[]
def add(key,value): rows.append((key,float(value)))
for temp in (0.0,20.0,70.0,120.0):
    add(f"property.{temp:g}.rho",density(temp))
    add(f"property.{temp:g}.cp",heat_capacity(temp))
    add(f"property.{temp:g}.k",conductivity(temp))

g=make_geometry("roast",mass_kg=1.5,resolution=10,samples=3)
add("geometry.volume",g.volume);add("geometry.area",g.embedded_area)
add("geometry.active",np.count_nonzero(g.active));add("geometry.pan",np.count_nonzero(g.pan_mask))
b=BoundaryConfig(oven_c=180.0,wall_c=180.0,h_conv=10.0,emissivity=.9,
                 covered=False,initial_moisture_kg_m2=.25)
s=RoastSolver(g,b,SolverConfig(initial_c=5.0,max_dt_s=5.0))
for step in range(121):
    if step in (0,30,120):
        q=s.sample()
        prefix=f"simulation.{step}"
        add(prefix+".coldest",q.coldest_c);add(prefix+".center",q.center_c)
        add(prefix+".mean",q.mean_c);add(prefix+".pasteurization",q.pasteurization)
        add(prefix+".moisture",np.sum(s.moisture*g.surface_area))
    if step<120:s.step(1.0,"roast")
add("ledger.convection",s.ledger.convection_j);add("ledger.radiation",s.ledger.radiation_j)
add("ledger.evaporation",s.ledger.evaporation_j);add("ledger.net",s.ledger.net_surface_j)
add("ledger.enthalpy",s.ledger.discrete_enthalpy_j);add("ledger.residual",s.ledger.residual_j)
out=ROOT/"fixtures"/"rust_golden.tsv"
out.write_text("# Synthetic deterministic NumPy regression fixture; not empirical calibration.\n"+
               "key\tvalue\n"+"".join(f"{k}\t{v:.17g}\n" for k,v in rows))
print(out)
