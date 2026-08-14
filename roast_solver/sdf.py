"""Analytic SDF presets and their source-agnostic voxel interface.

Negative distance is inside.  ``voxelize`` derives an embedded surface-area
vector from sign-changing Cartesian faces.  Its magnitude, rather than the
number of exposed voxel faces, is used by the finite-volume boundary source;
this projected-area reconstruction avoids the classic stair-step area excess.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import gamma
from typing import Callable
import numpy as np

Array = np.ndarray


def sphere_sdf(x, y, z, radius=0.5):
    return np.sqrt(x*x + y*y + z*z) - radius


def ellipsoid_sdf(x, y, z, axes):
    """Accurate-enough signed-distance approximation to an ellipsoid."""
    a, b, c = axes
    q = np.sqrt((x/a)**2 + (y/b)**2 + (z/c)**2)
    # radial implicit function divided by a bounded local gradient scale
    return (q - 1.0) * min(a, b, c)


def superellipsoid_sdf(x, y, z, axes=(0.65, 0.42, 0.38), exponent=2.6):
    a, b, c = axes
    q = (np.abs(x/a)**exponent + np.abs(y/b)**exponent + np.abs(z/c)**exponent) ** (1.0/exponent)
    return (q - 1.0) * min(a, b, c)


def rounded_box_sdf(x, y, z, half=(0.72, 0.48, 0.16), radius=0.10):
    qx, qy, qz = np.abs(x)-half[0]+radius, np.abs(y)-half[1]+radius, np.abs(z)-half[2]+radius
    outside = np.sqrt(np.maximum(qx, 0)**2 + np.maximum(qy, 0)**2 + np.maximum(qz, 0)**2)
    inside = np.minimum(np.maximum(qx, np.maximum(qy, qz)), 0)
    return outside + inside - radius


def capsule_sdf(x, y, z, a, b, radius):
    x, y, z = np.broadcast_arrays(x, y, z)
    pa = np.stack((x-a[0], y-a[1], z-a[2]), axis=0)
    ba = np.asarray(b, dtype=float) - np.asarray(a, dtype=float)
    h = np.clip((pa[0]*ba[0] + pa[1]*ba[1] + pa[2]*ba[2]) / np.dot(ba, ba), 0, 1)
    return np.sqrt(np.sum((pa - ba.reshape(3, *([1]*x.ndim))*h) ** 2, axis=0)) - radius


def smooth_min(a, b, k=0.08):
    h = np.clip(0.5 + 0.5*(b-a)/k, 0, 1)
    return b*(1-h) + a*h - k*h*(1-h)


def bird_sdf(x, y, z):
    """Composed body + limbs minus an open-ish internal cavity spheroid."""
    body = ellipsoid_sdf(x, y, z, (0.55, 0.39, 0.38))
    left_leg = capsule_sdf(x, y, z, (-0.28, 0.25, -0.12), (-0.66, 0.34, -0.20), 0.13)
    right_leg = capsule_sdf(x, y, z, (-0.28, -0.25, -0.12), (-0.66, -0.34, -0.20), 0.13)
    left_wing = capsule_sdf(x, y, z, (0.05, 0.32, 0.05), (0.30, 0.53, -0.02), 0.09)
    right_wing = capsule_sdf(x, y, z, (0.05, -0.32, 0.05), (0.30, -0.53, -0.02), 0.09)
    solid = smooth_min(smooth_min(smooth_min(smooth_min(body, left_leg), right_leg), left_wing), right_wing)
    cavity = ellipsoid_sdf(x+0.12, y, z-0.02, (0.29, 0.20, 0.20))
    return np.maximum(solid, -cavity)  # difference: body \\ cavity


def ham_sdf(x, y, z):
    # Smooth union creates a mild teardrop rather than pretending to be a scan.
    return smooth_min(ellipsoid_sdf(x+0.12, y, z, (0.48, 0.38, 0.37)),
                      sphere_sdf(x-0.30, y, z, 0.29), 0.10)


PRESETS: dict[str, tuple[Callable, tuple[float, float, float]]] = {
    "roast": (lambda x,y,z: superellipsoid_sdf(x,y,z), (0.72, 0.50, 0.46)),
    "bird": (bird_sdf, (0.85, 0.68, 0.52)),
    "slab": (lambda x,y,z: rounded_box_sdf(x,y,z), (0.85, 0.61, 0.29)),
    "ham": (ham_sdf, (0.70, 0.48, 0.46)),
    "sphere": (lambda x,y,z: sphere_sdf(x,y,z), (0.55, 0.55, 0.55)),
}


@lru_cache(None)
def _unit_volume(name: str) -> float:
    fn, half = PRESETS[name]
    # Deterministic numerical volume only establishes each preset's scale.
    n = 140
    axes = [np.linspace(-v, v, n, endpoint=False) + v/n for v in half]
    x, y, z = np.meshgrid(*axes, indexing="ij", sparse=True)
    return float(np.count_nonzero(fn(x, y, z) <= 0) * np.prod([2*v/n for v in half]))


@dataclass
class GridGeometry:
    phi: Array
    inside: Array
    normals: Array                 # shape (3,nx,ny,nz), outward
    surface_area: Array            # m² represented by each boundary cell
    pan_contact: Array
    spacing: float
    origin: tuple[float, float, float]
    cell_volume: float
    preset: str

    @property
    def volume(self) -> float:
        return float(np.count_nonzero(self.inside) * self.cell_volume)

    @property
    def surface_mask(self):
        return self.surface_area > 0


def _shift_inside(mask: Array, axis: int, direction: int) -> Array:
    out = np.zeros_like(mask)
    src = [slice(None)]*3
    dst = [slice(None)]*3
    if direction > 0:
        src[axis] = slice(1, None); dst[axis] = slice(None, -1)
    else:
        src[axis] = slice(None, -1); dst[axis] = slice(1, None)
    out[tuple(dst)] = mask[tuple(src)]
    return out


def voxelize(preset: str, mass_kg: float, resolution: int = 64, density: float = 1060.0, padding_cells: int = 3) -> GridGeometry:
    """Scale a preset to ``mass/density`` and sample an isotropic grid.

    ``resolution`` is the longest-domain cell count including padding.  This is
    intentionally independent of the solver and is the SDF contract envisaged
    for future geometry sources.
    """
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r}")
    if mass_kg <= 0 or resolution < 12:
        raise ValueError("mass must be positive and resolution >= 12")
    fn, half0 = PRESETS[preset]
    scale = ((mass_kg/density) / _unit_volume(preset)) ** (1/3)
    ext = np.asarray(half0)*scale
    spacing = 2*max(ext)/(resolution - 2*padding_cells)
    shape = tuple(int(np.ceil(2*e/spacing)) + 2*padding_cells for e in ext)
    shape = tuple(v + (v % 2 == 0) for v in shape)  # odd puts a cell at centre
    origin = tuple(-0.5*v*spacing for v in shape)
    coords = [origin[i] + (np.arange(shape[i])+0.5)*spacing for i in range(3)]
    x, y, z = np.meshgrid(*coords, indexing="ij", sparse=True)
    phi = (fn(x/scale, y/scale, z/scale)*scale).astype(np.float32)
    inside = phi <= 0

    # Reconstructed vector area from each inside-to-outside sign-changing face.
    area_vec = np.zeros((3,)+shape, dtype=np.float32)
    face_area = spacing*spacing
    for axis in range(3):
        plus = inside & ~_shift_inside(inside, axis, +1)
        minus = inside & ~_shift_inside(inside, axis, -1)
        area_vec[axis] = (plus.astype(np.float32) - minus.astype(np.float32))*face_area
    surface_area = np.sqrt(np.sum(area_vec*area_vec, axis=0))

    grad = np.stack(np.gradient(phi, spacing, edge_order=2))
    grad_norm = np.sqrt(np.sum(grad*grad, axis=0))
    normals = grad / np.maximum(grad_norm, 1e-12)
    # Area-vector normals are less noisy in cut cells; SDF normals remain the fallback.
    av_norm = np.maximum(surface_area, 1e-12)
    normals[:, surface_area > 0] = (area_vec/av_norm)[..., surface_area > 0]

    zz = np.broadcast_to(z, shape)
    pan_contact = (surface_area > 0) & (normals[2] < -0.45) & (zz < -0.72*ext[2])
    return GridGeometry(phi, inside, normals.astype(np.float32), surface_area,
                        pan_contact, spacing, origin, spacing**3, preset)
