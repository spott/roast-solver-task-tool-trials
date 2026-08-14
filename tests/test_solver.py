import numpy as np
from roast_solver.sdf import voxelize
from roast_solver.solver import RoastSolver, SolverConfig, diffuse_dirichlet_box
from roast_solver.validation import sphere_center_ratio, sphere_eigenvalues, embedded_sphere_check


def test_dirichlet_box_symmetry_monotonic_and_stable():
    t = diffuse_dirichlet_box(n=15, steps=80)
    assert np.isfinite(t).all() and 0 <= t.min() <= t.max() <= 1
    assert np.allclose(t, t[::-1,:,:])
    assert t[7,7,7] < t[6,7,7] < t[1,7,7]


def test_energy_exchange_is_conservative_with_full_boundary_physics():
    cfg = SolverConfig(preset="sphere", mass_kg=.35, resolution=26,
                       initial_c=20, oven_c=150, moisture_kg_m2=.04)
    s = RoastSolver(cfg)
    for _ in range(25): s.step()
    assert s.ledger.boundary_input_j > 0
    assert abs(s.ledger.residual_j)/s.ledger.boundary_input_j < 2e-6
    assert s.ledger.radiation_j > 0
    assert s.ledger.evaporation_j < 0
    assert np.any(s.moisture[s.geometry.surface_mask] < cfg.moisture_kg_m2)


def test_per_cell_evaporation_depletes_and_pan_is_insulated():
    cfg = SolverConfig(preset="roast", mass_kg=.5, resolution=24,
                       initial_c=30, oven_c=200, moisture_kg_m2=1e-5)
    s = RoastSolver(cfg)
    initial_pan = s.moisture[s.geometry.pan_contact].copy()
    for _ in range(5): s.step()
    assert np.all(s.moisture[s.geometry.pan_contact] == initial_pan)
    assert np.any(s.moisture[s.geometry.surface_mask & ~s.geometry.pan_contact] == 0)


def test_robin_sphere_series_limits_and_roots():
    roots = sphere_eigenvalues(2.0, 12)
    assert len(roots) == 12 and np.all(np.diff(roots) > 0)
    assert abs(sphere_center_ratio(0.0, 2.0, 100)-1) < 2e-3
    assert 0 < sphere_center_ratio(0.5, 2.0) < 1


def test_embedded_robin_sphere_production_acceptance_anchor():
    report = embedded_sphere_check(resolution=32, elapsed_s=1800)
    assert report["relative_reduced_error"] < 0.01
    assert 0.90 < report["area_ratio"] < 1.10
