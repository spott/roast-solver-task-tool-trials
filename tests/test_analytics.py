import numpy as np

from roast_solver.analytics import (
    make_sphere_geometry,
    robin_sphere_center_ratio,
    slab_robin_center_ratio,
    sphere_robin_eigenvalues,
)


def test_robin_sphere_eigen_equation_and_monotonic_heating():
    biot = 0.47
    roots = sphere_robin_eigenvalues(biot, 12)
    residual = 1.0 - roots / np.tan(roots) - biot
    assert np.max(np.abs(residual)) < 1e-10
    ratio = robin_sphere_center_ratio(np.array([0.1, 0.2, 0.4]), biot)
    assert np.all(np.diff(ratio) < 0)
    assert np.all((ratio > 0) & (ratio < 1))


def test_slab_series_anchor_is_bounded_and_monotonic():
    ratio = slab_robin_center_ratio(np.array([0.05, 0.2, 0.5]), biot=2.0)
    assert np.all(np.diff(ratio) < 0)
    assert np.all((ratio > 0) & (ratio < 1.01))


def test_sphere_voxel_volume_converges_to_exact_geometry():
    coarse = make_sphere_geometry(0.02, 29)
    fine = make_sphere_geometry(0.02, 65)
    coarse_error = abs(coarse.voxel_volume_m3 / coarse.requested_volume_m3 - 1)
    fine_error = abs(fine.voxel_volume_m3 / fine.requested_volume_m3 - 1)
    assert fine_error < coarse_error
    assert fine_error < 0.003
