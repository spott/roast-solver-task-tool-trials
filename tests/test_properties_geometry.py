import numpy as np

from roast_solver.geometry import make_geometry
from roast_solver.properties import meat_properties, thermal_diffusivity


def test_properties_stay_in_lean_meat_ranges():
    rho, cp, k = meat_properties(np.array([5.0, 60.0, 90.0]))
    assert np.all((rho >= 1050) & (rho <= 1080))
    assert np.all((cp >= 3300) & (cp <= 3600))
    assert np.all((k >= 0.45) & (k <= 0.50))
    assert np.all((thermal_diffusivity(np.array([5.0, 90.0])) > 1.1e-7))


def test_presets_obey_sdf_contract_and_mass_volume():
    for preset in ("roast", "bird", "slab", "ham"):
        geometry = make_geometry(preset, mass_kg=1.5, grid_size=35)
        assert geometry.inside.any() and (~geometry.inside).any()
        assert np.allclose(np.linalg.norm(geometry.normal[geometry.area > 0], axis=-1), 1.0, atol=2e-3)
        assert geometry.surface_area_m2 > 0
        # Center voxelization is deliberately simple; mass normalization should
        # nevertheless be within a few production voxels.
        assert abs(geometry.voxel_volume_m3 / geometry.requested_volume_m3 - 1.0) < 0.08


def test_pan_patch_is_distinct_from_exposed_crown():
    geometry = make_geometry("roast", grid_size=35)
    assert geometry.pan_contact.any()
    assert np.any((geometry.area > 0) & ~geometry.pan_contact)
    assert np.mean(geometry.normal[geometry.pan_contact, 2]) < -0.5
