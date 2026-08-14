#!/usr/bin/env python3
"""Regenerate deterministic Python/Rust parity values.

This is a numerical regression fixture, not measured food data and not an
empirical calibration. Run from the repository root with NumPy installed.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from roast_solver.geometry import make_geometry
from roast_solver.properties import conductivity, density, diffusivity, heat_capacity
from roast_solver.solver import BoundaryConfig, SimulationConfig, simulate

TEMPERATURES = [-5.0, 20.0, 60.0, 100.0]
scenario = {
    "preset": "sphere",
    "mass_kg": 0.2,
    "resolution": 17,
    "material_density": 1060.0,
    "initial_c": 5.0,
    "target_c": 999.0,
    "oven_c": 160.0,
    "convection_h": 10.0,
    "emissivity": 0.0,
    "wall_c": None,
    "covered": True,
    "ambient_vapor_density": 0.01,
    "lewis_number": 0.9,
    "surface_water_kg_m2": 0.25,
    "pan_insulated": False,
    "max_cook_s": 120.0,
    "rest_s": 0.0,
    "sample_interval_s": 30.0,
    "requested_dt_s": 1.0,
    "rest_ambient_c": 22.0,
    "rest_h": 7.0,
    "foil_tent": False,
    "pasteurization_ref_c": 70.0,
    "pasteurization_z_c": 10.0,
    "denaturation_bump": False,
}
g = make_geometry("sphere", scenario["mass_kg"], scenario["resolution"], scenario["material_density"])
b = BoundaryConfig(
    oven_c=scenario["oven_c"], convection_h=scenario["convection_h"],
    emissivity=scenario["emissivity"], wall_c=scenario["wall_c"],
    covered=scenario["covered"], ambient_vapor_density=scenario["ambient_vapor_density"],
    lewis_number=scenario["lewis_number"], surface_water_kg_m2=scenario["surface_water_kg_m2"],
    pan_insulated=scenario["pan_insulated"],
)
c = SimulationConfig(
    initial_c=scenario["initial_c"], target_c=scenario["target_c"],
    max_cook_s=scenario["max_cook_s"], rest_s=scenario["rest_s"],
    sample_interval_s=scenario["sample_interval_s"], requested_dt_s=scenario["requested_dt_s"],
    rest_ambient_c=scenario["rest_ambient_c"], rest_h=scenario["rest_h"],
    foil_tent=scenario["foil_tent"], pasteurization_ref_c=scenario["pasteurization_ref_c"],
    pasteurization_z_c=scenario["pasteurization_z_c"], denaturation_bump=scenario["denaturation_bump"],
)
r = simulate(g, b, c)
data = {
    "schema_version": 1,
    "provenance": "deterministic Python reference output; synthetic numerical regression only",
    "empirically_calibrated": False,
    "property_samples": [
        {"temperature_c": t, "density": float(density(t)), "heat_capacity": float(heat_capacity(t)),
         "conductivity": float(conductivity(t)), "diffusivity": float(diffusivity(t))}
        for t in TEMPERATURES
    ],
    "scenario": scenario,
    "expected": {
        "dimensions_zyx": list(g.shape), "inside_cells": int(g.inside.sum()), "dt_s": r.dt_s,
        "records": [
            {"time_s": float(t), "coldest_c": float(co), "probe_c": float(pr),
             "surface_mean_c": float(su), "pasteurization_equivalent_min": float(pa)}
            for t, co, pr, su, pa in zip(r.time_s, r.coldest_c, r.probe_c, r.surface_mean_c, r.pasteurization_equivalent_min)
        ],
        "net_surface_j": r.energy["net_surface_j"],
    },
    "tolerances": {"property_relative": 2e-12, "temperature_c_absolute": 2e-4, "energy_relative": 2e-4},
}
Path("fixtures/python_rust_golden.json").write_text(json.dumps(data, indent=2) + "\n")
