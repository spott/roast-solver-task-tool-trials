import numpy as np

from roast_solver.analytics import make_sphere_geometry, robin_sphere_center_ratio
from roast_solver.boundary import BoundaryConditions, SurfaceState, surface_flux
from roast_solver.properties import meat_properties
from roast_solver.solver import ExplicitSolver, SolverConfig


def test_radiation_evaporation_and_per_cell_depletion():
    shape = (2, 1, 1)
    area = np.ones(shape, dtype=np.float32) * 1e-4
    state = SurfaceState.initialize(area, 20.0, 2e-5)
    state.moisture_kg_m2[1] = 0.0
    result = surface_flux(
        np.full(shape, 30.0), np.full(shape, 0.48), np.full(shape, -0.001), 0.002,
        area, np.zeros(shape, dtype=bool), state,
        BoundaryConditions.oven(180.0), 10.0,
    )
    assert np.all(result.radiative_w_m2 > 0)
    assert result.mass_flux_kg_m2_s[0, 0, 0] > 0
    assert result.mass_flux_kg_m2_s[1, 0, 0] == 0
    assert state.moisture_kg_m2[0, 0, 0] < 2e-5
    assert state.crust[1, 0, 0]


def test_pan_contact_is_insulated():
    area = np.ones((1, 1, 1), dtype=np.float32)
    state = SurfaceState.initialize(area, 20.0, 0.2)
    result = surface_flux(
        np.full(area.shape, 20.0), np.full(area.shape, 0.48), -np.ones(area.shape) * 0.001,
        0.002, area, np.ones(area.shape, dtype=bool), state,
        BoundaryConditions.oven(180.0), 1.0,
    )
    assert result.net_w_m2.item() == 0
    assert result.mass_flux_kg_m2_s.item() == 0


def test_embedded_energy_account_closes():
    geometry = make_sphere_geometry(0.022, grid_size=29)
    config = SolverConfig(
        initial_c=20.0,
        target_c=200.0,
        oven=BoundaryConditions(ambient_c=80.0, wall_c=80.0, h_conv=15.0, emissivity=0.0, moisture_reservoir_kg_m2=0.0),
        max_cook_s=180.0,
        rest_s=0.0,
        sample_interval_s=60.0,
    )
    result = ExplicitSolver(geometry, config).run()
    assert result.energy.boundary_j > 0
    assert abs(result.energy.residual_j) / result.energy.boundary_j < 3e-4


def test_embedded_sphere_center_tracks_exact_robin_series():
    radius = 0.02
    geometry = make_sphere_geometry(radius, grid_size=45)
    bc = BoundaryConditions(ambient_c=30.0, wall_c=30.0, h_conv=12.0, emissivity=0.0, moisture_reservoir_kg_m2=0.0)
    config = SolverConfig(initial_c=20.0, target_c=100.0, oven=bc, max_cook_s=900.0, rest_s=0.0, sample_interval_s=900.0)
    result = ExplicitSolver(geometry, config).run()
    center = result.history[-1].probe_c
    rho, cp, k = meat_properties(25.0)
    exact_ratio = float(robin_sphere_center_ratio(float(k / (rho * cp) * 900.0 / radius**2), float(bc.h_conv * radius / k)))
    exact_center = bc.ambient_c + (config.initial_c - bc.ambient_c) * exact_ratio
    # The 45³ browser/reference regression grid uses a 1.5-cell coarea band;
    # the stricter production-resolution result is recorded in VALIDATION.md.
    assert abs(center - exact_center) / (bc.ambient_c - config.initial_c) < 0.03


def test_rest_phase_reports_carryover():
    geometry = make_sphere_geometry(0.012, grid_size=23)
    config = SolverConfig(
        initial_c=10.0, target_c=12.0,
        oven=BoundaryConditions.oven(160.0, convection=True, moisture_reservoir_kg_m2=0.0),
        rest=BoundaryConditions.rest(22.0), max_cook_s=1800, rest_s=300, sample_interval_s=10,
    )
    result = ExplicitSolver(geometry, config).run()
    assert result.pull_time_s is not None
    assert result.peak_time_after_pull_s >= 0
    assert result.peak_probe_c >= 12.0
    assert result.carryover_c >= 0
