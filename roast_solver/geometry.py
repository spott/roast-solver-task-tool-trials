"""Analytic SDF presets and source-agnostic voxel-grid contract.

Array order is (z, y, x). SDF is negative inside. Surface area is assigned to
an interior one-cell-thick signed-distance shell (a level-set delta integral),
which avoids the orientation-dependent area inflation of exposed voxel faces.
"""

from dataclasses import dataclass
from functools import lru_cache
import math
from typing import Callable
import numpy as np


@dataclass
class GridGeometry:
    sdf: np.ndarray
    inside: np.ndarray
    normals: np.ndarray  # final coordinate axis is (x, y, z), outward
    surface_area: np.ndarray  # m2 represented by each interior boundary cell
    pan_contact: np.ndarray
    spacing_m: float
    origin_m: tuple[float, float, float]

    @property
    def shape(self):
        return self.sdf.shape

    @property
    def volume_m3(self) -> float:
        return float(np.count_nonzero(self.inside) * self.spacing_m**3)

    @property
    def exposed_area_m2(self) -> float:
        return float(self.surface_area[~self.pan_contact].sum())


def sphere_sdf(x, y, z, radius):
    return np.sqrt(x * x + y * y + z * z) - radius


def ellipsoid_sdf(x, y, z, axes):
    """Accurate-near-surface ellipsoid distance approximation."""
    a, b, c = axes
    q = np.sqrt((x / a) ** 2 + (y / b) ** 2 + (z / c) ** 2)
    # Scale algebraic distance by local radial metric.
    scale = np.sqrt(x * x + y * y + z * z) / np.maximum(q, 1e-12)
    return (q - 1.0) * scale


def superellipsoid_sdf(x, y, z, axes, exponent=2.5):
    a, b, c = axes
    q = (np.abs(x / a) ** exponent + np.abs(y / b) ** exponent + np.abs(z / c) ** exponent) ** (1.0 / exponent)
    # This has the right zero set and a close distance near it; gradient
    # correction in voxelize makes the level-set area integral consistent.
    return (q - 1.0) * min(axes)


def rounded_box_sdf(x, y, z, half_size, radius):
    hx, hy, hz = half_size
    qx, qy, qz = np.abs(x) - (hx - radius), np.abs(y) - (hy - radius), np.abs(z) - (hz - radius)
    outside = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2 + np.maximum(qz, 0) ** 2)
    return outside + np.minimum(np.maximum(qx, np.maximum(qy, qz)), 0) - radius


def capsule_sdf(x, y, z, a, b, radius):
    pa = np.stack((x - a[0], y - a[1], z - a[2]), axis=-1)
    ba = np.asarray(b, dtype=float) - np.asarray(a, dtype=float)
    t = np.clip(np.sum(pa * ba, axis=-1) / np.dot(ba, ba), 0.0, 1.0)
    d = pa - t[..., None] * ba
    return np.linalg.norm(d, axis=-1) - radius


def _bird_unit_sdf(x, y, z):
    body = ellipsoid_sdf(x, y, z, (1.0, 0.67, 0.62))
    leg1 = capsule_sdf(x, y, z, (-0.60, -0.40, -0.18), (-1.20, -0.50, -0.28), 0.20)
    leg2 = capsule_sdf(x, y, z, (-0.60, 0.40, -0.18), (-1.20, 0.50, -0.28), 0.20)
    wing1 = capsule_sdf(x, y, z, (0.20, -0.58, 0.08), (0.65, -0.83, -0.02), 0.12)
    wing2 = capsule_sdf(x, y, z, (0.20, 0.58, 0.08), (0.65, 0.83, -0.02), 0.12)
    outside = np.minimum.reduce((body, leg1, leg2, wing1, wing2))
    cavity = ellipsoid_sdf(x - 0.16, y, z + 0.01, (0.50, 0.35, 0.34))
    return np.maximum(outside, -cavity)


@lru_cache(maxsize=1)
def _bird_unit_volume() -> float:
    n = 112
    xs = np.linspace(-1.45, 1.2, n)
    ys = np.linspace(-1.0, 1.0, n)
    zs = np.linspace(-0.8, 0.8, n)
    z, y, x = np.meshgrid(zs, ys, xs, indexing="ij")
    return float(np.count_nonzero(_bird_unit_sdf(x, y, z) <= 0) * (xs[1] - xs[0]) * (ys[1] - ys[0]) * (zs[1] - zs[0]))


def voxelize(sdf_fn: Callable, bounds, spacing_m: float) -> GridGeometry:
    """Sample any SDF callable into the common grid contract."""
    lo, hi = np.asarray(bounds[0], float), np.asarray(bounds[1], float)
    counts = np.ceil((hi - lo) / spacing_m).astype(int)
    # Cell centers, with requested bounds treated as outer cell faces.
    xs = lo[0] + (np.arange(counts[0]) + 0.5) * spacing_m
    ys = lo[1] + (np.arange(counts[1]) + 0.5) * spacing_m
    zs = lo[2] + (np.arange(counts[2]) + 0.5) * spacing_m
    z, y, x = np.meshgrid(zs, ys, xs, indexing="ij")
    phi = np.asarray(sdf_fn(x, y, z), dtype=np.float64)
    inside = phi <= 0.0
    gz, gy, gx = np.gradient(phi, spacing_m, edge_order=1)
    grad_norm = np.sqrt(gx * gx + gy * gy + gz * gz)
    safe = np.maximum(grad_norm, 1e-12)
    normals = np.stack((gx / safe, gy / safe, gz / safe), axis=-1).astype(np.float32)

    # One-sided level-set delta: integral over the inner shell tends to area.
    shell = inside & (phi >= -spacing_m)
    area = np.where(shell, spacing_m**2 * grad_norm, 0.0)
    if not np.any(shell):
        raise ValueError("grid has no resolved boundary; reduce spacing")
    z_inside = z[inside]
    bottom = float(z_inside.min())
    height = float(z_inside.max() - bottom + spacing_m)
    pan = shell & (normals[..., 2] < -0.60) & (z < bottom + 0.22 * height)
    return GridGeometry(phi.astype(np.float32), inside, normals, area.astype(np.float64), pan, spacing_m, tuple(lo))


def make_geometry(preset: str, mass_kg: float, resolution: int = 40, material_density=1060.0) -> GridGeometry:
    """Create roast, bird, slab, ham, or sphere with volume mass/density.

    ``resolution`` is the number of cells across the longest body dimension.
    A small exterior margin is retained so the SDF's complete boundary exists.
    """
    if mass_kg <= 0 or resolution < 12:
        raise ValueError("mass must be positive and resolution at least 12")
    volume = mass_kg / material_density
    preset = preset.lower()

    if preset == "roast":
        ratios = np.array([1.0, 0.68, 0.58])
        n = 2.5
        unit_volume = 8 * np.prod(ratios) * math.gamma(1 + 1 / n) ** 3 / math.gamma(1 + 3 / n)
        scale = (volume / unit_volume) ** (1 / 3)
        axes = tuple(scale * ratios)
        longest = 2 * max(axes)
        fn = lambda x, y, z: superellipsoid_sdf(x, y, z, axes, n)
        ext = np.asarray(axes)
    elif preset == "bird":
        scale = (volume / _bird_unit_volume()) ** (1 / 3)
        longest = 2.65 * scale
        fn = lambda x, y, z: scale * _bird_unit_sdf(x / scale, y / scale, z / scale)
        ext = np.array([1.45, 1.0, 0.8]) * scale
    elif preset == "slab":
        ratios = np.array([1.0, 0.72, 0.28])
        # Scale is corrected from the sharp-box volume; rounded corners make
        # actual mass a few percent lower, which is exposed in geometry.volume.
        scale = (volume / (8 * np.prod(ratios))) ** (1 / 3)
        half = scale * ratios
        radius = 0.10 * (2 * half[2])
        longest = 2 * max(half)
        fn = lambda x, y, z: rounded_box_sdf(x, y, z, half, radius)
        ext = half
    elif preset in ("ham", "sphere"):
        radius = (3 * volume / (4 * math.pi)) ** (1 / 3)
        longest = 2 * radius
        fn = lambda x, y, z: sphere_sdf(x, y, z, radius)
        ext = np.array([radius] * 3)
    else:
        raise ValueError(f"unknown preset {preset!r}")

    h = longest / resolution
    margin = 2.5 * h
    return voxelize(fn, (-ext - margin, ext + margin), h)
