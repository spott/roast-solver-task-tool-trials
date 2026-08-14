from __future__ import annotations
import argparse, json
from dataclasses import asdict
import numpy as np
from .solver import SolverConfig, simulate
from .validation import embedded_sphere_check, energy_budget_check, resolution_convergence


def main():
    p = argparse.ArgumentParser(description="NumPy Roast Solver reference")
    p.add_argument("--preset", default="roast", choices=("roast","bird","slab","ham","sphere"))
    p.add_argument("--mass", type=float, default=1.5)
    p.add_argument("--resolution", type=int, default=40)
    p.add_argument("--oven", type=float, default=180)
    p.add_argument("--initial", type=float, default=5)
    p.add_argument("--target", type=float, default=57)
    p.add_argument("--fan", action="store_true")
    p.add_argument("--covered", action="store_true")
    p.add_argument("--validate", action="store_true")
    p.add_argument("--output", help="write final field and curves to .npz")
    args = p.parse_args()
    if args.validate:
        print(json.dumps({"sphere": embedded_sphere_check(args.resolution),
                          "energy": energy_budget_check(args.resolution),
                          "convergence": resolution_convergence()}, indent=2))
        return
    cfg = SolverConfig(preset=args.preset, mass_kg=args.mass, resolution=args.resolution,
        oven_c=args.oven, initial_c=args.initial, target_c=args.target,
        convection=args.fan, covered=args.covered)
    result = simulate(cfg, lambda t,temp,phase: print(f"\r{phase}: {t/60:6.1f} min, core {temp:5.1f} C", end=""))
    print("\n"+json.dumps(result.summary(), indent=2))
    if args.output:
        np.savez_compressed(args.output, temperature=result.temperature_c, times=result.times_s,
            coldest=result.coldest_c, lethality=result.lethality_minutes,
            inside=result.geometry.inside, phi=result.geometry.phi)

if __name__ == "__main__": main()
