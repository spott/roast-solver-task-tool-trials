"""Analytic signed-distance presets and source-agnostic voxelization."""
from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True)
class Grid:
    shape: tuple[int, int, int]
    spacing: float
    origin: tuple[float, float, float]

    @property
    def cell_volume(self) -> float:
        return self.spacing ** 3

    def coordinates(self):
        nz, ny, nx = self.shape
        z = self.origin[2] + (np.arange(nz) + .5) * self.spacing
        y = self.origin[1] + (np.arange(ny) + .5) * self.spacing
        x = self.origin[0] + (np.arange(nx) + .5) * self.spacing
        return np.meshgrid(z, y, x, indexing="ij")


@dataclass
class Geometry:
    grid: Grid
    phi: np.ndarray
    inside: np.ndarray
    normals: np.ndarray
    boundary_area: np.ndarray
    pan_mask: np.ndarray
    preset: str
    target_volume: float

    @property
    def volume(self):
        return float(self.inside.sum()) * self.grid.cell_volume

    @property
    def surface_area(self):
        return float(self.boundary_area.sum())

    @property
    def wetted_area_fraction(self):
        """Embedded surface area per nominal cell-face area (dimensionless)."""
        return self.boundary_area / (self.grid.spacing ** 2)


def _ellipsoid_sdf(x, y, z, radii, power=2.0):
    a, b, c = radii
    q = ((np.abs(x)/a)**power + (np.abs(y)/b)**power + (np.abs(z)/c)**power) ** (1.0/power)
    # This radial approximation has the correct zero set and useful normals.
    return (q - 1.0) * min(radii)


def _capsule_sdf(x, y, z, a, b, radius):
    # capsule between endpoints a and b
    px = np.stack((x, y, z), axis=-1)
    av = np.asarray(a); bv = np.asarray(b); ba = bv-av
    h = np.clip(np.sum((px-av)*ba, axis=-1)/np.dot(ba, ba), 0., 1.)
    return np.linalg.norm(px-(av+h[..., None]*ba), axis=-1)-radius


def _rounded_box_sdf(x, y, z, half, radius):
    q = np.stack((np.abs(x), np.abs(y), np.abs(z)), axis=-1) - (np.asarray(half)-radius)
    return np.linalg.norm(np.maximum(q, 0.), axis=-1) + np.minimum(np.max(q, axis=-1), 0.) - radius


def _smooth_union(a, b, k):
    h = np.clip(.5 + .5*(b-a)/k, 0., 1.)
    return b*(1-h) + a*h - k*h*(1-h)


def _dimensionless_sdf(preset, x, y, z):
    if preset == "roast":
        return _ellipsoid_sdf(x, y, z, (1., .68, .62), 2.6)
    if preset == "slab":
        return _rounded_box_sdf(x, y, z, (1., .70, .30), .16)
    if preset == "ham":
        # Tapered, mildly asymmetric teardrop.
        xx = x + .13*z
        radial = _ellipsoid_sdf(xx, y, z, (1., .72, .72), 2.15)
        return radial + .10*x
    if preset == "bird":
        body = _ellipsoid_sdf(x, y, z, (1., .66, .63), 2.0)
        left_leg = _capsule_sdf(x, y, z, (-.35,-.42,-.18), (-.92,-.67,-.42), .20)
        right_leg = _capsule_sdf(x, y, z, (-.35,.42,-.18), (-.92,.67,-.42), .20)
        wing_l = _capsule_sdf(x, y, z, (.12,-.55,.08), (-.20,-.90,-.02), .12)
        wing_r = _capsule_sdf(x, y, z, (.12,.55,.08), (-.20,.90,-.02), .12)
        outer = _smooth_union(body, left_leg, .10)
        outer = _smooth_union(outer, right_leg, .10)
        outer = _smooth_union(outer, wing_l, .07)
        outer = _smooth_union(outer, wing_r, .07)
        cavity = _ellipsoid_sdf(x+.30, y, z+.03, (.48,.30,.31), 2.)
        return np.maximum(outer, -cavity)
    raise ValueError(f"unknown preset {preset!r}")


def _unit_volume(preset):
    # Deterministic integration; called only while constructing a geometry.
    n = 112
    lim = 1.35 if preset == "bird" else 1.15
    v = np.linspace(-lim, lim, n, endpoint=False) + lim/n
    z, y, x = np.meshgrid(v, v, v, indexing="ij")
    return float((_dimensionless_sdf(preset, x, y, z) <= 0).sum()) * (2*lim/n)**3


# Deterministic 112^3 integration of the dimensionless zero sets above.
# Hard-coding avoids allocating the integration mesh during every import.
_UNIT_VOLUMES = {
    "roast": 2.198797825938411,
    "bird": 1.757326654462008,
    "slab": 1.6338044027879008,
    "ham": 2.4224915739454262,
}


def make_geometry(preset="roast", mass_kg=1.5, density=1060., resolution=48, padding=3):
    """Voxelize an SDF preset at a requested longest-axis resolution.

    Boundary area uses Crofton-style projected sign crossings divided by the
    local L1 normal norm. Unlike exposed voxel-face counting, this converges to
    true oblique surface area and avoids systematic stair-step inflation.
    """
    if preset not in _UNIT_VOLUMES:
        raise ValueError(f"preset must be one of {tuple(_UNIT_VOLUMES)}")
    target_volume = mass_kg / density
    scale = (target_volume / _UNIT_VOLUMES[preset]) ** (1/3)
    half_extent = (1.38 if preset == "bird" else 1.18) * scale
    h = 2*half_extent/resolution
    n = resolution + 2*padding
    grid = Grid((n, n, n), h, (-n*h/2, -n*h/2, -n*h/2))
    z, y, x = grid.coordinates()
    phi = scale * _dimensionless_sdf(preset, x/scale, y/scale, z/scale)
    inside = phi <= 0
    # Uniformly correct the voxelized volume to mass/density. Because h and
    # the analytic shape scale together, this leaves the dimensionless cell
    # pattern unchanged while making the discrete thermal mass exact.
    correction = (target_volume / (float(inside.sum())*h**3)) ** (1/3)
    scale *= correction; h *= correction
    grid = Grid((n, n, n), h, (-n*h/2, -n*h/2, -n*h/2))
    z, y, x = grid.coordinates()
    phi = scale * _dimensionless_sdf(preset, x/scale, y/scale, z/scale)
    inside = phi <= 0
    # Normals point outward. np.gradient follows z,y,x storage order.
    gz, gy, gx = np.gradient(phi, h, edge_order=1)
    mag = np.sqrt(gx*gx + gy*gy + gz*gz) + 1e-15
    normals = np.stack((gx/mag, gy/mag, gz/mag), axis=-1).astype(np.float32)
    l1 = np.abs(normals).sum(axis=-1).clip(.25)
    crossings = np.zeros_like(phi, dtype=np.float64)
    # Attribute each inside/outside crossing to its inside cell.
    for axis in range(3):
        sl0 = [slice(None)]*3; sl1 = [slice(None)]*3
        sl0[axis] = slice(None,-1); sl1[axis] = slice(1,None)
        a, b = tuple(sl0), tuple(sl1)
        cross = inside[a] != inside[b]
        ca = cross & inside[a]; cb = cross & inside[b]
        tmp = crossings[a]; tmp[ca] += h*h/l1[a][ca]; crossings[a] = tmp
        tmp = crossings[b]; tmp[cb] += h*h/l1[b][cb]; crossings[b] = tmp
    boundary_area = crossings.astype(np.float32)
    occupied_z = np.where(inside)[0]
    bottom = int(occupied_z.min()) if occupied_z.size else 0
    # Only the lowest ~1.5 layers with strongly downward normals touch a pan.
    iz = np.indices(inside.shape)[0]
    pan_mask = inside & (boundary_area > 0) & (iz <= bottom+1) & (normals[...,2] < -.45)
    return Geometry(grid, phi.astype(np.float32), inside, normals, boundary_area,
                    pan_mask, preset, target_volume)
