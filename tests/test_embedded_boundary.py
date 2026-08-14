import numpy as np
from roast_solver.validation import robin_sphere_check, robin_slab_check, sphere_geometry
from roast_solver.solver import BoundaryConfig, step, stable_timestep


def test_embedded_sphere_robin_center_and_area():
    check=robin_sphere_check(resolution=32,bi=.5,fourier=.2)
    assert check["relative_error"] < .01
    assert check["area_relative_error"] < .02
    assert check["energy_residual_fraction"] < 1e-10


def test_robin_slab_converges_and_high_h_bath_anchor():
    coarse=robin_slab_check(cells_through=8,bi=.5,fourier=.2)
    fine=robin_slab_check(cells_through=24,bi=.5,fourier=.2)
    bath=robin_slab_check(cells_through=24,bi=20.,fourier=.2)
    assert fine['relative_error'] < coarse['relative_error']/5
    assert fine['relative_error'] < .002
    # High-Bi water-bath limit isolates interior diffusion from oven fitting.
    assert bath['relative_error'] < .005


def test_every_step_accounts_for_boundary_energy():
    g=sphere_geometry(.02,20)
    t=np.full(g.inside.shape,np.nan,dtype='f4');t[g.inside]=20
    m=np.zeros_like(t)
    bc=BoundaryConfig(oven_c=100,emissivity=.9,moisture_capacity=0,pan_insulated=False)
    t,e=step(t,g,bc,m,stable_timestep(g,20),rest=False)
    assert e['boundary_j'] > 0
    assert abs(e['boundary_j']-e['sensible_j'])/e['boundary_j'] < 1e-10
    assert e['radiative_j'] > e['convective_j']*.5
