"""Command-line entry point for the NumPy reference solver."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np

from .boundary import BoundaryConditions
from .solver import SolverConfig, simulate_preset


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Roast Solver NumPy reference model")
    parser.add_argument("--preset", choices=("roast", "bird", "slab", "ham"), default="roast")
    parser.add_argument("--mass", type=float, default=1.5, help="mass in kg")
    parser.add_argument("--oven", type=float, default=180.0, help="oven temperature in C")
    parser.add_argument("--initial", type=float, default=5.0)
    parser.add_argument("--target", type=float, default=57.0)
    parser.add_argument("--grid", type=int, default=41)
    parser.add_argument("--max-hours", type=float, default=4.0)
    parser.add_argument("--rest-minutes", type=float, default=30.0)
    parser.add_argument("--convection", action="store_true")
    parser.add_argument("--covered", action="store_true")
    parser.add_argument("--foil-rest", action="store_true")
    parser.add_argument("--output", type=Path, help="optional NPZ with history and fields")
    args = parser.parse_args()
    config = SolverConfig(
        initial_c=args.initial,
        target_c=args.target,
        oven=BoundaryConditions.oven(args.oven, args.convection, args.covered),
        rest=BoundaryConditions.rest(foil_tent=args.foil_rest),
        max_cook_s=args.max_hours * 3600,
        rest_s=args.rest_minutes * 60,
    )
    result = simulate_preset(args.preset, args.mass, args.grid, config)
    summary = {
        "model": "uncalibrated physics prediction",
        "pull_minutes": None if result.pull_time_s is None else result.pull_time_s / 60,
        "peak_probe_c": result.peak_probe_c,
        "carryover_c": result.carryover_c,
        "peak_minutes_after_pull": result.peak_time_after_pull_s / 60,
        "pasteurization_minutes_at_70C_z10C": result.pasteurization_minutes,
        "evaporated_kg": result.evaporated_kg,
        "energy_residual_fraction": result.energy.residual_j / max(abs(result.energy.boundary_j), 1.0),
    }
    print(json.dumps(summary, indent=2))
    if args.output:
        history = np.asarray([[p.time_s, p.coldest_c, p.probe_c, p.hottest_c, p.pasteurization_minutes] for p in result.history])
        np.savez_compressed(
            args.output,
            history=history,
            final_temperature_c=result.final_temperature_c,
            pull_temperature_c=result.pull_field_c,
            inside=result.geometry.inside,
            phi=result.geometry.phi,
        )


if __name__ == "__main__":
    main()
