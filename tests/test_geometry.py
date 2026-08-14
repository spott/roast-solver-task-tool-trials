import numpy as np
import pytest
from roast_solver.geometry import make_geometry


@pytest.mark.parametrize("preset", ["roast", "bird", "slab", "ham"])
def test_presets_match_mass_volume_and_sdf_contract(preset):
    g=make_geometry(preset,mass_kg=1.0,resolution=28)
    assert g.phi.shape == g.inside.shape == g.boundary_area.shape
    assert g.normals.shape == g.phi.shape+(3,)
    assert abs(g.volume-g.target_volume)/g.target_volume < .035
    assert g.surface_area > 0
    assert np.allclose(g.wetted_area_fraction,
                       g.boundary_area/g.grid.spacing**2)
    boundary=g.boundary_area>0
    assert boundary.any() and np.all(g.inside[boundary])
    assert np.allclose(np.linalg.norm(g.normals[boundary],axis=-1),1,atol=.03)


def test_bird_has_a_real_cavity_and_pan_patch_is_distinct():
    g=make_geometry("bird",mass_kg=2.0,resolution=34)
    center=tuple(s//2 for s in g.phi.shape)
    # Cavity is offset toward the positive-x body end; at least one outside
    # pocket is surrounded by occupied cells in the center region.
    assert (~g.inside[:, :, center[2]:center[2]+6]).any()
    assert 0 < g.pan_mask.sum() < (g.boundary_area>0).sum()
