import math
import numpy as np
from roast_solver.geometry import SDFGeometry, make_preset, voxelize
from roast_solver.solver import Environment, Simulation, SolverConfig
from roast_solver.validation import (cylinder_center_ratio, dirichlet_box_mode,
                                     embedded_sphere_case, slab_center_ratio,
                                     sphere_center_ratio)


def small_sphere(spacing=0.006):
    r=0.03
    shape=SDFGeometry("sphere",lambda x,y,z:np.sqrt(x*x+y*y+z*z)-r,
                      ((-r,r),)*3,4*math.pi*r**3/3)
    return voxelize(shape,spacing)


def test_m2_dirichlet_box_converges():
    coarse=dirichlet_box_mode(11,30)
    fine=dirichlet_box_mode(21,120)
    assert fine["relative_l2_error"] < coarse["relative_l2_error"]
    assert fine["relative_l2_error"] < 0.007


def test_sphere_series_starts_at_one_and_decays():
    early=sphere_center_ratio(0.8,0.01)
    late=sphere_center_ratio(0.8,0.2)
    assert 0 < late < early <= 1.00001


def test_slab_and_cylinder_analytic_anchors_decay():
    for analytic in (slab_center_ratio,cylinder_center_ratio):
        early=analytic(1.0,0.02)
        late=analytic(1.0,0.2)
        assert 0 < late < early < 1.01


def test_embedded_boundary_energy_is_conservative():
    sim=Simulation(small_sphere(),SolverConfig(initial_temp_c=10,dtype="float64"))
    sim.run_for(900,Environment(120,120,12,0.9,0.1,False,True),"roast",300)
    assert sim.surface_energy_j > 0
    assert sim.energy_relative_error() < 2e-12
    assert np.min(sim.temperature_c[sim.geometry.inside]) > 10


def test_radiation_adds_heat_and_pan_is_insulated():
    grid=small_sphere()
    plain=Simulation(grid,SolverConfig(initial_temp_c=10))
    radiant=Simulation(grid,SolverConfig(initial_temp_c=10))
    plain.run_for(300,Environment(150,150,10,0,1,True,False),"roast",300)
    radiant.run_for(300,Environment(150,150,10,.9,1,True,False),"roast",300)
    assert radiant.surface_energy_j > plain.surface_energy_j
    assert np.all(radiant.geometry.surface_area_m2[radiant.geometry.pan_mask] > 0)


def test_per_cell_evaporation_depletes_into_crust_stage():
    sim=Simulation(small_sphere(),SolverConfig(initial_temp_c=20,
                   moisture_reservoir_kg_m2=1e-6))
    sim.run_for(300,Environment.oven(180,convection=True),"roast",300)
    exposed=sim.geometry.boundary & ~sim.geometry.pan_mask
    assert np.any(sim.surface_stage[exposed] == 1)
    assert np.all(sim.moisture_kg_m2 >= 0)


def test_rest_boundary_can_produce_carryover_then_cooling():
    grid=voxelize(make_preset("slab",0.5),0.008)
    sim=Simulation(grid,SolverConfig(initial_temp_c=10))
    sim.run_for(1200,Environment.oven(180),"roast",300)
    center_before=float(sim.temperature_c[sim._probe_index])
    sim.run_for(900,Environment.rest(22),"rest",60)
    rest=[s.probe_c for s in sim.samples if s.phase=="rest"]
    assert max(rest) >= center_before
    assert sim.samples[-1].hottest_c < 180


def test_high_h_water_bath_isolates_interior_model():
    # A high-h analytic sphere is the table-free sous-vide/water-bath anchor:
    # boundary resistance is small and the interior conduction model dominates.
    result=embedded_sphere_case(cells_per_radius=14,h_conv=500,fourier=0.08)
    assert result["biot"] > 30
    assert result["relative_error"] < 0.01


def test_embedded_sphere_has_practical_coarse_accuracy():
    result=embedded_sphere_case(cells_per_radius=14,fourier=0.08)
    # The plan's <1% center-temperature target is already met at this modest
    # resolution; production grids normally resolve a radius with more cells.
    assert result["relative_error"] < 0.01
    assert result["area_relative_error"] < 0.03
    assert result["energy_relative_error"] < 1e-10
