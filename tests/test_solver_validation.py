import numpy as np
from roast_solver.validation import diffuse_dirichlet_box, make_sphere_geometry, sphere_center_ratio
from roast_solver.solver import Solver, Boundary
from roast_solver.properties import conductivity


def test_dirichlet_box_converges_second_order():
    e1=diffuse_dirichlet_box(14)
    e2=diffuse_dirichlet_box(26)
    assert e2 < e1/3


def test_embedded_energy_accounting():
    g=make_sphere_geometry(.025,24)
    s=Solver(g,10.,Boundary(air_c=120.,wall_c=120.,h_conv=12.,emissivity=.9,
                            covered=False,moisture_kg_m2=.02,pan_insulated=False))
    errors=[]
    for _ in range(20):
        a=s.step(min(1.,s.stable_dt()))
        errors.append(abs(a.surface_j-a.enthalpy_j)/max(abs(a.surface_j),1))
        components=a.convective_j+a.radiative_j+a.evaporative_j
        assert abs(a.surface_j-components)/max(abs(a.surface_j),1)<2e-9
    assert max(errors)<2e-9
    assert s.moisture[g.boundary_area>0].min()<.02


def test_embedded_sphere_robin_series_anchor():
    # Radiation/evaporation off gives the classical Robin problem. Variable
    # properties move slightly over this small 10 K interval.
    radius=.025; g=make_sphere_geometry(radius,42)
    initial=20.; ambient=30.; h=20.
    s=Solver(g,initial,Boundary(air_c=ambient,wall_c=ambient,h_conv=h,
                               emissivity=0,covered=True,pan_insulated=False))
    target_fo=.08
    alpha=float(conductivity(20)/(1060*3550))
    end=target_fo*radius**2/alpha
    while s.time_s<end:
        s.step(min(s.stable_dt(),end-s.time_s))
    center=s.temperature[tuple(v//2 for v in s.temperature.shape)]
    numerical=(center-ambient)/(initial-ambient)
    bi=h*radius/float(conductivity(20))
    exact=float(sphere_center_ratio(target_fo,bi,60))
    # Production-style cut-face resolution is comfortably within the plan's
    # 1% centre-temperature target for this anchor.
    assert abs(numerical-exact)/abs(exact)<.01


def test_staged_evaporation_depletes_to_crust():
    g=make_sphere_geometry(.02,20)
    bc=Boundary(air_c=180.,h_conv=20.,moisture_kg_m2=1e-5,covered=False,pan_insulated=False)
    s=Solver(g,20.,bc)
    s.step(min(1.,s.stable_dt()))
    b=g.boundary_area>0
    assert np.all(s.moisture[b]==0)
    # Next stage remains finite under dry-crust h.
    s.step(min(1.,s.stable_dt()))
    assert np.isfinite(s.temperature[g.inside]).all()
