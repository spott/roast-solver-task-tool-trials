"""Generate demonstrative forward-model fixtures. There is no measured data."""
from dataclasses import asdict
from pathlib import Path
import json
from roast_solver.solver import SolverConfig, simulate

scenarios = [
    SolverConfig(preset="roast", mass_kg=0.40, resolution=22, initial_c=8,
                 oven_c=170, target_c=95, max_roast_hours=1.0,
                 rest_minutes=0, sample_seconds=300, h_still=9.5,
                 emissivity=.88, moisture_kg_m2=.18),
    SolverConfig(preset="slab", mass_kg=0.40, resolution=22, initial_c=8,
                 oven_c=150, target_c=95, max_roast_hours=1.0,
                 rest_minutes=0, sample_seconds=300, convection=True,
                 covered=True, h_fan=18, emissivity=.91, moisture_kg_m2=.30),
]
output={"kind":"SYNTHETIC_FORWARD_MODEL_NOT_PROBE_DATA","generator":"roast_solver 0.1.0",
        "purpose":"exercise fixture plumbing only; parameters are not fitted", "scenarios":[]}
for cfg in scenarios:
    result=simulate(cfg)
    output["scenarios"].append({"config":asdict(cfg),
        "observations":{"time_s":[round(float(x),3) for x in result.times_s],
                        "coldest_c":[round(float(x),5) for x in result.coldest_c],
                        "deep_probe_c":[round(float(x),5) for x in result.probe_c]}})
Path("fixtures/synthetic_roast_calibration.json").write_text(json.dumps(output,indent=2)+"\n")
