"""Small local CLI for running the NumPy reference model."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .geometry import make_preset, voxelize
from .solver import Environment, SolverConfig, run_roast_and_rest


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--preset", choices=("roast","bird","slab","ham"), default="roast")
    p.add_argument("--weight-kg", type=float, default=1.8)
    p.add_argument("--spacing-mm", type=float, default=6.0)
    p.add_argument("--oven-c", type=float, default=180.0)
    p.add_argument("--initial-c", type=float, default=5.0)
    p.add_argument("--target-c", type=float, default=57.0)
    p.add_argument("--convection", action="store_true")
    p.add_argument("--covered", action="store_true")
    p.add_argument("--max-hours", type=float, default=6.0)
    p.add_argument("--rest-minutes", type=float, default=30.0)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    shape = make_preset(args.preset, args.weight_kg)
    grid = voxelize(shape, args.spacing_mm/1000)
    result = run_roast_and_rest(
        grid, Environment.oven(args.oven_c,args.convection,args.covered), args.target_c,
        args.max_hours*3600, args.rest_minutes*60,
        config=SolverConfig(initial_temp_c=args.initial_c))
    output = {k:v for k,v in result.items() if k != "simulation"}
    output["grid"] = {"shape":grid.phi.shape,"voxel_volume_m3":grid.volume_m3,
                      "surface_area_m2":grid.surface_area_total_m2}
    text = json.dumps(output, indent=2)
    if args.output:
        args.output.write_text(text+"\n")
    else:
        print(text)

if __name__ == "__main__":
    main()
