"""Regenerate deterministic Python golden outputs (never empirical data)."""
from __future__ import annotations
import json
from pathlib import Path
from roast_solver.geometry import make_preset, voxelize
from roast_solver.properties import meat_properties
from roast_solver.solver import Environment, Simulation, SolverConfig

ROOT = Path(__file__).resolve().parents[1]

def main():
    scenarios = []
    for preset, mass, initial, oven, covered in (
        ("roast",1.8,5.0,180.0,False), ("slab",1.2,8.0,160.0,True)):
        grid = voxelize(make_preset(preset,mass),0.008)
        sim = Simulation(grid,SolverConfig(initial_temp_c=initial))
        env = Environment.oven(oven,False,covered)
        sim.run_for(1800,env,"roast",300)
        scenarios.append({
            "preset":preset,"mass_kg":mass,"spacing_m":0.008,
            "initial_c":initial,"oven_c":oven,"covered":covered,
            "grid_shape":list(grid.phi.shape),
            "voxel_volume_m3":round(grid.volume_m3,10),
            "surface_area_m2":round(grid.surface_area_total_m2,8),
            "curve":[[round(s.time_s,5),round(s.coldest_c,5),round(s.probe_c,5),round(s.hottest_c,5)] for s in sim.samples],
            "energy_j":round(sim.surface_energy_j,4)
        })
    p = ROOT/"fixtures"/"python_golden.json"
    p.write_text(json.dumps({
        "fixture_kind":"synthetic-regression-oracle","empirical_data":False,
        "properties_20c":[round(x,8) for x in meat_properties(20.0)],
        "scenarios":scenarios},indent=2)+"\n")
    print(p)

if __name__ == "__main__": main()
