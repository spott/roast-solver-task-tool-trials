import math
import numpy as np
import pytest
from roast_solver.sdf import voxelize


@pytest.mark.parametrize("preset", ["roast", "bird", "slab", "ham", "sphere"])
def test_geometry_contract_and_mass(preset):
    g = voxelize(preset, 1.2, 34)
    assert g.phi.shape == g.inside.shape
    assert g.normals.shape == (3,) + g.phi.shape
    assert np.all(g.surface_area[~g.inside] == 0)
    assert g.surface_area.sum() > 0
    assert abs(g.volume*1060 - 1.2)/1.2 < 0.12
    n = np.sqrt(np.sum(g.normals[:,g.surface_mask]**2, axis=0))
    assert np.max(abs(n-1)) < 2e-5


def test_embedded_sphere_area_is_not_staircase_area():
    g = voxelize("sphere", 1.0, 56)
    radius = (3*g.volume/(4*math.pi))**(1/3)
    ratio = g.surface_area.sum()/(4*math.pi*radius**2)
    assert 0.90 < ratio < 1.10
    # Pan patch is geometrically selected and remains distinct.
    assert 0 < g.surface_area[g.pan_contact].sum() < g.surface_area.sum()/2
