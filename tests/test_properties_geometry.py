import numpy as np
from roast_solver.properties import heat_capacity, conductivity, density, diffusivity
from roast_solver.geometry import make_geometry


def test_properties_in_physical_range():
    t=np.array([0.,40.,80.])
    assert np.all((heat_capacity(t)>3300)&(heat_capacity(t)<3900))
    assert np.all((conductivity(t)>.42)&(conductivity(t)<.60))
    assert np.all((density(t)>1000)&(density(t)<1100))
    assert np.all((diffusivity(t)>1e-7)&(diffusivity(t)<1.7e-7))


def test_presets_obey_sdf_contract_and_mass():
    for kind in ("roast","bird","slab","ham"):
        g=make_geometry(kind,1.5,n=28)
        assert g.inside.any() and g.boundary_area.sum()>0
        assert np.isfinite(g.normals).all()
        # Binary volume error is expected at coarse resolution.
        assert abs(g.volume-1.5/1060)/(1.5/1060)<.08
        assert np.all(g.boundary_area[~g.inside]==0)
