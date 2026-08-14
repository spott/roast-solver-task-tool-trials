import csv
from pathlib import Path
import numpy as np
from roast_solver.properties import food_properties, radiation_coefficient
from roast_solver.solver import dirichlet_box_step, BoundaryConfig, SimulationConfig, simulate
from roast_solver.geometry import make_geometry


def test_cross_language_fixture_is_current_python_output():
    rows=list(csv.reader(line for line in Path('fixtures/core_golden_v1.csv').read_text().splitlines() if not line.startswith('#')))
    for row in rows:
        values=list(map(float,row[1:]))
        if row[0]=='PROP':
            assert np.allclose(food_properties(values[0]),values[1:],rtol=1e-14,atol=1e-15)
        elif row[0]=='RAD':
            assert np.isclose(radiation_coefficient(*values[:3]),values[3],rtol=1e-14)
        elif row[0]=='STENCIL':
            n=int(values[0]);t=(np.arange(n**3,dtype=np.float32)%7).reshape((n,n,n))
            t[[0,-1],:,:]=0;t[:,[0,-1],:]=0;t[:,:,[0,-1]]=0
            for _ in range(int(values[4])):t=dirichlet_box_step(t,*values[1:4])
            assert np.isclose(t.ravel()[62],values[5]) and np.isclose(t.sum(),values[6])
        elif row[0]=='INTEGRATION':
            g=make_geometry('roast',values[2],resolution=int(values[1]))
            r=simulate(g,BoundaryConfig(oven_c=values[3]),SimulationConfig(
                initial_c=values[4],target_c=values[5],max_cook_s=values[6],
                rest_s=values[7],output_interval_s=30))
            assert np.allclose((r.pull_time_s,r.carryover_c,r.pasteurization_equivalent_s),values[8:],rtol=1e-12)
