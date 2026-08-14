import numpy as np
from roast_solver.properties import meat_properties, thermal_diffusivity
from roast_solver.geometry import make_preset, voxelize


def test_lean_meat_properties_are_physical_and_temperature_dependent():
    rho, cp, k = meat_properties(np.array([5.0, 60.0, 100.0]))
    assert np.all((rho > 1000) & (rho < 1150))
    assert np.all((cp > 3300) & (cp < 3900))
    assert np.all((k > 0.40) & (k < 0.60))
    assert np.all((thermal_diffusivity(np.array([5.0,100.0])) > 1.0e-7))
    assert meat_properties(60,denaturation_bump=True)[1] > meat_properties(60)[1]


def test_preset_sdf_contract_and_volume_scaling():
    for name in ("roast","slab","ham","bird"):
        shape = make_preset(name,1.4)
        grid = voxelize(shape,0.008)
        assert grid.phi.shape == grid.inside.shape
        assert grid.normals.shape == grid.phi.shape+(3,)
        assert grid.surface_area_total_m2 > 0
        assert np.all(grid.surface_area_m2[~grid.inside] == 0)
        # Coarse voxelization must still honor weight-to-volume reasonably.
        assert abs(grid.volume_m3-shape.target_volume_m3)/shape.target_volume_m3 < 0.18
        nmag = np.linalg.norm(grid.normals[grid.boundary],axis=1)
        assert np.max(np.abs(nmag-1)) < 2e-5


def test_bird_has_open_cavity_at_center():
    bird = make_preset("bird",1.8)
    assert float(bird.sdf(np.array(0.0),np.array(0.0),np.array(0.0))) > 0
