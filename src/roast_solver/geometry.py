"""Analytic/composed SDF presets and their source-agnostic voxel contract."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import gamma
from typing import Callable
import numpy as np


Array = np.ndarray


@dataclass(frozen=True)
class SDFGeometry:
    name: str
    sdf: Callable[[Array, Array, Array], Array]
    bounds: tuple[tuple[float, float], tuple[float, float], tuple[float, float]]
    target_volume_m3: float


@dataclass
class GridGeometry:
    """Geometry contract consumed by every solver backend.

    ``phi`` is negative inside. Normals point outward. ``surface_area_m2`` is
    nonzero only for boundary cells and is corrected for the L1 projection of
    the SDF normal, avoiding the systematic area inflation of a staircase.
    """
    phi: Array
    inside: Array
    normals: Array
    surface_area_m2: Array
    wetted_area_fraction: Array
    pan_mask: Array
    spacing_m: float
    origin_m: tuple[float, float, float]
    coordinates_m: tuple[Array, Array, Array]
    preset: str
    target_volume_m3: float

    @property
    def cell_volume_m3(self) -> float:
        return self.spacing_m**3

    @property
    def volume_m3(self) -> float:
        return float(np.count_nonzero(self.inside))*self.cell_volume_m3

    @property
    def surface_area_total_m2(self) -> float:
        return float(np.sum(self.surface_area_m2, dtype=np.float64))

    @property
    def boundary(self) -> Array:
        return self.surface_area_m2 > 0


def _smooth_min(a, b, radius):
    h = np.clip(0.5 + 0.5*(b-a)/radius, 0.0, 1.0)
    return b*(1-h) + a*h - radius*h*(1-h)


def _capsule(x, y, z, a, b, radius):
    # distance to segment a--b
    px = np.stack(np.broadcast_arrays(x, y, z), axis=0)
    aa = np.asarray(a).reshape((3,) + (1,)*x.ndim)
    ba = np.asarray(b) - np.asarray(a)
    ba_view = ba.reshape((3,) + (1,)*x.ndim)
    h = np.clip(np.sum((px-aa)*ba_view, axis=0)/np.dot(ba, ba), 0.0, 1.0)
    return np.sqrt(np.sum((px-aa-ba_view*h)**2, axis=0)) - radius


def _ellipsoid_approx(x, y, z, axes):
    a, b, c = axes
    q = np.sqrt((x/a)**2 + (y/b)**2 + (z/c)**2)
    return (q-1.0)*min(axes)


def _rounded_box(x, y, z, half_size, radius):
    qx = np.abs(x)-half_size[0]+radius
    qy = np.abs(y)-half_size[1]+radius
    qz = np.abs(z)-half_size[2]+radius
    outside = np.sqrt(np.maximum(qx, 0)**2 + np.maximum(qy, 0)**2 + np.maximum(qz, 0)**2)
    inside = np.minimum(np.maximum(qx, np.maximum(qy, qz)), 0)
    return outside + inside - radius


@lru_cache(maxsize=None)
def _unit_volume(preset: str) -> float:
    """Deterministic integration of composed unit shapes, only used to scale."""
    f, bounds = _unit_shape(preset)
    n = 112
    axes = [np.linspace(lo, hi, n, dtype=np.float32) for lo, hi in bounds]
    dx = [(hi-lo)/(n-1) for lo, hi in bounds]
    x, y, z = np.meshgrid(*axes, indexing="ij", sparse=True)
    return float(np.count_nonzero(f(x, y, z) <= 0))*dx[0]*dx[1]*dx[2]


def _unit_shape(preset: str):
    if preset == "roast":
        axes, exponent = (1.0, 0.62, 0.52), 2.6
        def f(x, y, z):
            return ((np.abs(x/axes[0])**exponent + np.abs(y/axes[1])**exponent +
                     np.abs(z/axes[2])**exponent)**(1/exponent)-1)*min(axes)
        bounds = tuple((-1.05*a, 1.05*a) for a in axes)
        return f, bounds
    if preset == "slab":
        hs, r = (1.0, 0.72, 0.22), 0.12
        return (lambda x,y,z: _rounded_box(x,y,z,hs,r)), tuple((-1.05*a,1.05*a) for a in hs)
    if preset == "ham":
        def f(x,y,z):
            # Union gives a mild teardrop rather than pretending to model bone.
            return _smooth_min(_ellipsoid_approx(x,y,z,(0.9,0.68,0.65)),
                               _ellipsoid_approx(x-0.42,y,z,(0.68,0.52,0.50)), 0.12)
        return f, ((-0.98,1.15),(-0.75,0.75),(-0.72,0.72))
    if preset == "bird":
        def f(x,y,z):
            body = _ellipsoid_approx(x,y,z,(0.86,0.62,0.56))
            breast = _ellipsoid_approx(x+0.22,y,z+0.16,(0.72,0.58,0.46))
            union = _smooth_min(body, breast, 0.10)
            for side in (-1.0, 1.0):
                leg = _capsule(x,y,z,(0.34,side*0.40,-0.20),(0.92,side*0.62,-0.42),0.18)
                wing = _capsule(x,y,z,(-0.18,side*0.48,0.10),(0.30,side*0.83,-0.02),0.11)
                union = _smooth_min(union, leg, 0.07)
                union = _smooth_min(union, wing, 0.05)
            cavity = _ellipsoid_approx(x-0.06,y,z-0.05,(0.42,0.30,0.30))
            return np.maximum(union, -cavity)
        return f, ((-0.95,1.18),(-0.94,0.94),(-0.68,0.68))
    raise ValueError(f"unknown preset {preset!r}")


def make_preset(preset: str, mass_kg: float = 1.8, density_kg_m3: float = 1060.0) -> SDFGeometry:
    """Create a volume-scaled preset. Weight-to-volume uses the stated density."""
    if mass_kg <= 0 or density_kg_m3 <= 0:
        raise ValueError("mass and density must be positive")
    preset = preset.lower()
    unit_f, unit_bounds = _unit_shape(preset)
    volume = mass_kg/density_kg_m3
    if preset == "roast":
        n = 2.6
        unit_volume = 8*1.0*0.62*0.52*gamma(1+1/n)**3/gamma(1+3/n)
    else:
        unit_volume = _unit_volume(preset)
    scale = (volume/unit_volume)**(1/3)

    def scaled_sdf(x, y, z):
        return scale*unit_f(x/scale, y/scale, z/scale)
    bounds = tuple((lo*scale, hi*scale) for lo, hi in unit_bounds)
    return SDFGeometry(preset, scaled_sdf, bounds, volume)


def voxelize(shape: SDFGeometry, spacing_m: float = 0.004, padding_cells: int = 2) -> GridGeometry:
    if spacing_m <= 0:
        raise ValueError("spacing must be positive")
    axes = []
    for lo, hi in shape.bounds:
        lo -= padding_cells*spacing_m
        hi += padding_cells*spacing_m
        count = int(np.ceil((hi-lo)/spacing_m))+1
        center = (lo+hi)/2
        axes.append((np.arange(count, dtype=np.float64)-(count-1)/2)*spacing_m+center)
    x, y, z = np.meshgrid(*axes, indexing="ij", sparse=True)
    phi = np.asarray(shape.sdf(x,y,z), dtype=np.float32)
    inside = phi <= 0

    gx, gy, gz = np.gradient(phi.astype(np.float64), spacing_m, edge_order=2)
    mag = np.sqrt(gx*gx+gy*gy+gz*gz)
    mag = np.maximum(mag, 1e-12)
    normals = np.stack((gx/mag, gy/mag, gz/mag), axis=-1).astype(np.float32)

    padded = np.pad(inside, 1, constant_values=False)
    exposed = np.zeros(phi.shape, dtype=np.uint8)
    for axis in range(3):
        before = [slice(1,-1)]*3
        after = [slice(1,-1)]*3
        before[axis] = slice(0,-2)
        after[axis] = slice(2,None)
        exposed += (~padded[tuple(before)]).astype(np.uint8)
        exposed += (~padded[tuple(after)]).astype(np.uint8)
    exposed *= inside
    l1 = np.maximum(np.sum(np.abs(normals), axis=-1), 1.0)
    area = exposed.astype(np.float64)*spacing_m**2/l1
    area *= inside
    area = area.astype(np.float32)
    fraction = np.clip(area/(np.sqrt(3)*spacing_m**2), 0, 1).astype(np.float32)

    zz = np.broadcast_to(z, phi.shape)
    min_inside_z = float(np.min(zz[inside]))
    pan = (area > 0) & (normals[...,2] < -0.45) & (zz < min_inside_z + 1.6*spacing_m)
    return GridGeometry(phi, inside, normals, area, fraction, pan,
                        spacing_m, tuple(float(a[0]) for a in axes),
                        tuple(np.asarray(a) for a in axes), shape.name,
                        shape.target_volume_m3)
