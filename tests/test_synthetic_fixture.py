import json
from pathlib import Path
from roast_solver.geometry import make_geometry
from roast_solver.solver import BoundaryConfig, SimulationConfig, simulate


def test_documented_synthetic_fixture_is_regression_locked():
    f=json.loads(Path('fixtures/synthetic_roast_v1.json').read_text())
    assert f['kind']=='synthetic-model-output' and f['empirical'] is False
    s=f['scenario']; g=make_geometry(s['preset'],s['mass_kg'],resolution=s['resolution'])
    r=simulate(g,BoundaryConfig(oven_c=s['oven_c']),
               SimulationConfig(initial_c=s['initial_c'],target_c=s['target_c'],
                                max_cook_s=s['max_cook_s'],rest_s=s['rest_s'],output_interval_s=120))
    for key in ('pull_time_s','peak_probe_c','carryover_c','pasteurization_equivalent_s'):
        assert abs(r.summary()[key]-f['expected'][key]) < 1e-5*max(abs(f['expected'][key]),1)
