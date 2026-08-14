import json
import math
from pathlib import Path
import unittest

import numpy as np

from roast_solver.geometry import make_geometry
from roast_solver.properties import conductivity, density, diffusivity, heat_capacity
from roast_solver.solver import BoundaryConfig, SimulationConfig, simulate
from roast_solver.validation import (
    dirichlet_cube_mode_error, embedded_sphere_constant, resolution_center_temperatures,
    robin_sphere_center_ratio, slab_1d_constant,
)


class PropertyTests(unittest.TestCase):
    def test_lean_meat_ranges_and_temperature_dependence(self):
        temperatures = np.array([5.0, 60.0, 100.0])
        # Choi--Okos water density falls at high temperature; this is wider
        # than the room-temperature 1050--1080 kg/m3 design anchor.
        self.assertTrue(np.all((density(temperatures) > 1000) & (density(temperatures) < 1100)))
        self.assertTrue(np.all((heat_capacity(temperatures) > 3300) & (heat_capacity(temperatures) < 3800)))
        self.assertTrue(np.all((conductivity(temperatures) > 0.40) & (conductivity(temperatures) < 0.60)))
        self.assertTrue(np.all((diffusivity(temperatures) > 1.0e-7) & (diffusivity(temperatures) < 1.7e-7)))


class GeometryTests(unittest.TestCase):
    def test_presets_obey_grid_contract(self):
        for preset in ("roast", "bird", "slab"):
            with self.subTest(preset=preset):
                geom = make_geometry(preset, 1.2, 22)
                self.assertGreater(geom.inside.sum(), 100)
                self.assertGreater(geom.surface_area.sum(), 0)
                self.assertTrue(np.allclose(np.linalg.norm(geom.normals[geom.surface_area > 0], axis=1), 1, atol=2e-3))
                self.assertTrue(np.all(geom.surface_area[~geom.inside] == 0))
        bird = make_geometry("bird", 1.2, 24)
        center = tuple(np.asarray(bird.shape) // 2)
        self.assertFalse(bool(bird.inside[center]), "composed bird must retain its cavity")

    def test_embedded_sphere_area_converges(self):
        errors = []
        for n in (24, 40):
            g = make_geometry("sphere", 1.0, n)
            radius = (3 * (1.0 / 1060.0) / (4 * math.pi)) ** (1 / 3)
            errors.append(abs(g.surface_area.sum() / (4 * math.pi * radius**2) - 1))
        self.assertLess(errors[-1], 0.08)


class ValidationTests(unittest.TestCase):
    def test_dirichlet_second_order_trend(self):
        coarse = dirichlet_cube_mode_error(13)
        fine = dirichlet_cube_mode_error(25)
        self.assertLess(fine, coarse / 2.5)
        self.assertLess(fine, 0.005)

    def test_robin_series_limits(self):
        value = robin_sphere_center_ratio(2.0, 0.15)
        self.assertGreater(value, 0)
        self.assertLess(value, 1)

    def test_high_transfer_slab_robin_anchor(self):
        # Bi=10 approximates a high-h water-bath boundary and isolates the
        # interior conduction update from radiation/evaporation complexity.
        self.assertLess(slab_1d_constant(80, biot=10.0, fourier=0.2)["relative_error"], 0.015)

    def test_preset_resolution_convergence(self):
        coarse, medium, fine = resolution_center_temperatures((16, 24, 32), duration_s=1800)
        self.assertLess(abs(fine - medium), abs(medium - coarse))

    def test_embedded_robin_sphere(self):
        check = embedded_sphere_constant(36, biot=2.0, fourier=0.15)
        self.assertLess(check["relative_error"], 0.08)
        self.assertLess(abs(check["surface_area_m2"] / check["exact_area_m2"] - 1), 0.08)


class FullPhysicsTests(unittest.TestCase):
    def test_energy_balance_evaporation_and_rest(self):
        geom = make_geometry("sphere", 0.5, 20)
        boundary = BoundaryConfig(oven_c=170, convection_h=18, surface_water_kg_m2=0.002)
        config = SimulationConfig(initial_c=8, target_c=200, max_cook_s=300, rest_s=120, sample_interval_s=60)
        result = simulate(geom, boundary, config)
        self.assertLess(result.energy["relative_balance_error"], 3e-5)
        self.assertGreater(result.energy["radiation_j"], 0)
        self.assertGreater(result.energy["evaporation_j"], 0)
        surface = geom.surface_area > 0
        self.assertTrue(np.any(result.wet_fraction[surface] == 0), "small reservoirs should enter dry-crust stage")
        self.assertIn("rest", result.phase)
        self.assertGreaterEqual(result.peak_core_c + 1e-5, result.coldest_c[result.time_s >= result.pull_time_s][0])

    def test_pan_patch_is_insulated(self):
        geom = make_geometry("roast", 0.7, 18)
        self.assertGreater(np.count_nonzero(geom.pan_contact), 0)
        result = simulate(geom, BoundaryConfig(oven_c=140, covered=True), SimulationConfig(target_c=200, max_cook_s=60, rest_s=0, sample_interval_s=60))
        self.assertLess(result.energy["relative_balance_error"], 3e-5)

    def test_synthetic_fixture_is_labeled(self):
        fixture = json.loads(Path("fixtures/synthetic_calibration.json").read_text())
        self.assertEqual(fixture["provenance"], "synthetic; not measured probe data")
        self.assertFalse(fixture["empirically_calibrated"])


if __name__ == "__main__":
    unittest.main()
