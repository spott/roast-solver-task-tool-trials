"""Parametric signed-distance geometry and voxelization.

All presets terminate in the same :class:`Geometry` contract.  Distances for
anisotropically transformed/composed shapes are first-order SDF approximations;
normals are always recomputed from the resulting physical grid field.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import gamma
import numpy as np


@dataclass(frozen=True)
class Grid:
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    spacing: float

    @property
    def shape(self) -> tuple[int, int, int]:
        return (self.x.size, self.y.size, self.z.size)

    @property
    def xyz(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return np.meshgrid(self.x, self.y, self.z, indexing="ij")


@dataclass
class Geometry:
    preset: str
    grid: Grid
    phi: np.ndarray
    inside: np.ndarray
    normal: np.ndarray
    area: np.ndarray
    wetted_fraction: np.ndarray
    pan_contact: np.ndarray
    requested_volume_m3: float

    @property
    def voxel_volume_m3(self) -> float:
        return float(self.inside.sum()) * self.grid.spacing**3

    @property
    def surface_area_m2(self) -> float:
        return float(self.area.sum())


def _smooth_min(a: np.ndarray, b: np.ndarray, radius: float) -> np.ndarray:
    h = np.clip(0.5 + 0.5 * (b - a) / radius, 0.0, 1.0)
    return b * (1.0 - h) + a * h - radius * h * (1.0 - h)


def _capsule(x: np.ndarray, y: np.ndarray, z: np.ndarray, a: tuple[float, float, float], b: tuple[float, float, float], radius: float) -> np.ndarray:
    pa = np.stack((x - a[0], y - a[1], z - a[2]), axis=-1)
    ba = np.asarray(b, dtype=float) - np.asarray(a, dtype=float)
    h = np.clip(np.sum(pa * ba, axis=-1) / np.dot(ba, ba), 0.0, 1.0)
    return np.linalg.norm(pa - h[..., None] * ba, axis=-1) - radius


def _ellipsoid(x: np.ndarray, y: np.ndarray, z: np.ndarray, axes: tuple[float, float, float]) -> np.ndarray:
    # Quilez's accurate distance approximation; exact on the surface.
    a = np.asarray(axes)
    p = np.stack((x, y, z), axis=-1)
    k0 = np.linalg.norm(p / a, axis=-1)
    k1 = np.linalg.norm(p / (a * a), axis=-1)
    distance = np.full_like(k0, -float(a.min()))
    np.divide(k0 * (k0 - 1.0), k1, out=distance, where=k1 > 1e-14)
    return distance


def _rounded_box(x: np.ndarray, y: np.ndarray, z: np.ndarray, half: tuple[float, float, float], radius: float) -> np.ndarray:
    q = np.abs(np.stack((x, y, z), axis=-1)) - (np.asarray(half) - radius)
    return np.linalg.norm(np.maximum(q, 0.0), axis=-1) + np.minimum(np.max(q, axis=-1), 0.0) - radius


def _base_sdf(preset: str, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    if preset == "roast":
        p = 2.5
        r = (np.abs(x / 1.45) ** p + np.abs(y) ** p + np.abs(z / 0.72) ** p) ** (1.0 / p)
        return (r - 1.0) * 0.72
    if preset == "slab":
        return _rounded_box(x, y, z, (1.45, 0.92, 0.42), 0.13)
    if preset == "ham":
        # A mildly tapered, rounded ham/teardrop.
        taper = np.clip(1.0 - 0.18 * (x + 0.2), 0.62, 1.2)
        return _ellipsoid(x, y / taper, z / taper, (1.25, 0.90, 0.88))
    if preset == "bird":
        body = _ellipsoid(x, y, z, (1.18, 0.78, 0.72))
        breast = _ellipsoid(x - 0.28, y, z - 0.12, (0.92, 0.73, 0.60))
        outer = _smooth_min(body, breast, 0.16)
        left_leg = _capsule(x, y, z, (-0.55, 0.45, -0.24), (-1.20, 0.66, -0.42), 0.22)
        right_leg = _capsule(x, y, z, (-0.55, -0.45, -0.24), (-1.20, -0.66, -0.42), 0.22)
        left_wing = _capsule(x, y, z, (0.20, 0.61, 0.05), (-0.45, 1.02, -0.08), 0.13)
        right_wing = _capsule(x, y, z, (0.20, -0.61, 0.05), (-0.45, -1.02, -0.08), 0.13)
        for part in (left_leg, right_leg, left_wing, right_wing):
            outer = _smooth_min(outer, part, 0.09)
        cavity = _ellipsoid(x + 0.22, y, z + 0.06, (0.56, 0.38, 0.34))
        return np.maximum(outer, -cavity)
    raise ValueError(f"unknown preset {preset!r}; choose roast, bird, slab, or ham")


@lru_cache(maxsize=None)
def _base_volume(preset: str) -> float:
    if preset == "roast":
        p = 2.5
        return 8.0 * 1.45 * 1.0 * 0.72 * gamma(1.0 + 1.0 / p) ** 3 / gamma(1.0 + 3.0 / p)
    # Deterministic midpoint integration is only used to choose the outer scale.
    n = 112
    extent = 1.65
    q = np.linspace(-extent, extent, n, endpoint=False) + extent / n
    x, y, z = np.meshgrid(q, q, q, indexing="ij")
    return float((_base_sdf(preset, x, y, z) <= 0).sum()) * (2.0 * extent / n) ** 3


def make_geometry(
    preset: str = "roast",
    mass_kg: float = 1.5,
    density_kg_m3: float = 1060.0,
    grid_size: int = 41,
    padding_cells: float = 2.5,
) -> Geometry:
    """Voxelize a mass-normalized preset on an isotropic Cartesian grid."""
    if mass_kg <= 0 or density_kg_m3 <= 0:
        raise ValueError("mass and density must be positive")
    if grid_size < 9:
        raise ValueError("grid_size must be at least 9")
    target_volume = mass_kg / density_kg_m3
    scale = (target_volume / _base_volume(preset)) ** (1.0 / 3.0)
    extent = 1.72 * scale
    spacing = 2.0 * extent / (grid_size - 1 - 2.0 * padding_cells)
    axis_extent = spacing * (grid_size - 1) / 2.0
    q = np.linspace(-axis_extent, axis_extent, grid_size)
    grid = Grid(q, q.copy(), q.copy(), spacing)
    x, y, z = grid.xyz
    phi = scale * _base_sdf(preset, x / scale, y / scale, z / scale)
    inside = phi <= 0.0

    derivatives = np.gradient(phi, spacing, edge_order=2)
    magnitude = np.sqrt(sum(d * d for d in derivatives))
    magnitude = np.maximum(magnitude, 1e-12)
    normal = np.stack(tuple(d / magnitude for d in derivatives), axis=-1).astype(np.float32)

    # One-sided triangular regularized delta.  Its integral over the inner
    # half-band is one, giving a rotation-independent coarea surface estimate.
    epsilon = 1.5 * spacing
    delta = np.where((phi <= 0.0) & (phi >= -epsilon), 2.0 * (1.0 + phi / epsilon) / epsilon, 0.0)
    area = (delta * magnitude * spacing**3).astype(np.float32)
    wetted = np.where(area > 0, 1.0, 0.0).astype(np.float32)
    surface_z_min = float(z[(area > 0) & inside].min(initial=0.0))
    pan = (area > 0) & (normal[..., 2] < -0.55) & (z <= surface_z_min + 1.75 * spacing)
    return Geometry(preset, grid, phi.astype(np.float32), inside, normal, area, wetted, pan, target_volume)
