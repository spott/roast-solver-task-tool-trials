import numpy as np
from roast_solver.geometry import make_geometry
from roast_solver.solver import BoundaryConfig, SimulationConfig, simulate, step, stable_timestep


def test_per_cell_evaporation_depletes_then_uses_dry_crust_rate():
    g=make_geometry('slab',.2,resolution=16)
    t=np.full(g.inside.shape,np.nan,dtype='f4');t[g.inside]=70
    dt=stable_timestep(g,70)
    wet=np.zeros_like(t); wet[g.boundary_area>0]=1e-7
    bc=BoundaryConfig(oven_c=200,moisture_capacity=1e-7,dry_evaporation_factor=.03)
    _,first=step(t,g,bc,wet,dt)
    assert np.all(wet[g.boundary_area>0] >= 0)
    assert (wet[g.boundary_area>0] == 0).any()
    full=np.zeros_like(t); full[g.boundary_area>0]=.3
    dry_cells=np.zeros_like(t)
    _,wet_energy=step(t,g,bc,full,dt)
    _,dry_energy=step(t,g,bc,dry_cells,dt)
    assert wet_energy['evaporative_j'] > dry_energy['evaporative_j']
    assert first['evaporative_j'] >= 0


def test_covered_suppresses_evaporation_and_rest_has_carryover():
    g=make_geometry('roast',.25,resolution=16)
    cfg=SimulationConfig(initial_c=20,target_c=30,max_cook_s=3600,rest_s=600,output_interval_s=60)
    open_result=simulate(g,BoundaryConfig(oven_c=180),cfg)
    covered_result=simulate(g,BoundaryConfig(oven_c=180,covered=True),cfg)
    assert open_result.pull_time_s is not None
    assert open_result.carryover_c > 0
    assert open_result.peak_time_s >= open_result.pull_time_s
    assert covered_result.energy.evaporative_j < open_result.energy.evaporative_j*.2
    assert open_result.pasteurization_equivalent_s >= 0
    assert abs(open_result.energy.residual_j) < 1e-8*open_result.energy.boundary_j
