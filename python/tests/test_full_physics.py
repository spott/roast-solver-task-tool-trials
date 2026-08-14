import numpy as np
from roast_solver.geometry import make_geometry
from roast_solver.solver import RoastSolver,BoundaryConfig,SolverConfig
from roast_solver.calibration import load_synthetic_fixture
from roast_solver.outputs import pasteurization_equivalent_seconds,doneness_bands

def test_radiation_evaporation_depletion_and_crust_are_staged_per_cell():
    g=make_geometry("slab",.25,14,samples=2)
    b=BoundaryConfig(oven_c=200,h_conv=15,initial_moisture_kg_m2=2e-5,pan_insulated=True)
    s=RoastSolver(g,b,SolverConfig(initial_c=55,max_dt_s=2))
    s.run(180,"roast",60)
    surface=g.surface_area>0
    assert s.ledger.radiation_j>0 and s.ledger.evaporation_j>0
    assert np.any(s.crust[surface])
    assert np.all(s.moisture>=0)
    assert np.all(s.moisture[g.pan_mask]==b.initial_moisture_kg_m2)

def test_rest_reports_carryover_and_cools_surface():
    g=make_geometry("roast",.35,14,samples=2)
    s=RoastSolver(g,BoundaryConfig(oven_c=190,initial_moisture_kg_m2=.01),SolverConfig(initial_c=10,max_dt_s=3,record_every_s=30))
    s.run(900,"roast"); pull_center=s.sample().center_c; max_before=np.nanmax(s.temperature)
    rest=s.run(600,"rest")
    assert max(x.center_c for x in rest)>=pull_center
    assert np.nanmax(s.temperature)<max_before

def test_outputs_and_fixture_are_explicitly_synthetic():
    f=load_synthetic_fixture(); assert f["provenance"]=="synthetic" and not f["empirically_calibrated"]
    assert pasteurization_equivalent_seconds([70,70],[0,60])==60
    assert doneness_bands(np.array([40,50,60,66,75])).tolist()==[0,1,2,3,4]
