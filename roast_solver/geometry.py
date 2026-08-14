"""Analytic SDF presets and their source-agnostic voxel representation.

`GridGeometry` is the contract consumed by the solver.  Boundary area uses a
Crofton cut-face estimate: each sign-changing Cartesian face is corrected by
the local normal's L1 norm.  Unlike raw stair stepping this converges to true
oblique surface area and associates one area with each embedded-boundary cell.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import gamma, pi
import numpy as np


@dataclass
class GridGeometry:
    phi: np.ndarray
    inside: np.ndarray
    normals: np.ndarray          # (..., 3), outward
    boundary_area: np.ndarray    # m2 assigned to inside cell
    wetted_fraction: np.ndarray  # boundary_area / dx2 (not clipped)
    pan_mask: np.ndarray
    dx: float
    origin: tuple[float, float, float]

    @property
    def volume(self) -> float:
        return float(self.inside.sum()) * self.dx**3

    @property
    def surface_area(self) -> float:
        return float(self.boundary_area.sum())


def _smooth_min(a, b, r):
    h = np.clip(0.5 + 0.5*(b-a)/r, 0.0, 1.0)
    return (1-h)*b + h*a - r*h*(1-h)


def _ellipsoid_sdf(x, y, z, axes, power=2.0):
    a, b, c = axes
    q = (np.abs(x/a)**power + np.abs(y/b)**power + np.abs(z/c)**power)**(1/power)
    # This radial approximation has the right zero set and sign.
    return (q - 1.0) * min(axes)


def _capsule_sdf(x, y, z, p0, p1, radius):
    px, py, pz = p0; qx, qy, qz = p1
    vx, vy, vz = qx-px, qy-py, qz-pz
    t = np.clip(((x-px)*vx + (y-py)*vy + (z-pz)*vz)/(vx*vx+vy*vy+vz*vz), 0, 1)
    return np.sqrt((x-(px+t*vx))**2 + (y-(py+t*vy))**2 + (z-(pz+t*vz))**2)-radius


def _rounded_box_sdf(x, y, z, half, radius):
    qx, qy, qz = np.abs(x)-half[0]+radius, np.abs(y)-half[1]+radius, np.abs(z)-half[2]+radius
    outside = np.sqrt(np.maximum(qx, 0)**2 + np.maximum(qy, 0)**2 + np.maximum(qz, 0)**2)
    return outside + np.minimum(np.maximum(qx, np.maximum(qy, qz)), 0) - radius


def _unit_sdf(kind, x, y, z):
    if kind == "roast":
        return _ellipsoid_sdf(x, y, z, (1.0, .68, .58), 2.5)
    if kind == "slab":
        return _rounded_box_sdf(x, y, z, (1.0, .68, .27), .12)
    if kind == "ham":
        sphere = _ellipsoid_sdf(x+.12, y, z, (.88, .73, .72), 2.0)
        nose = _ellipsoid_sdf(x-.56, y, z, (.65, .52, .53), 2.0)
        return _smooth_min(sphere, nose, .18)
    if kind == "bird":
        body = _ellipsoid_sdf(x, y, z, (.92, .63, .58), 2.0)
        thigh1 = _capsule_sdf(x,y,z,(-.25,.42,-.12),(.68,.63,-.25),.23)
        thigh2 = _capsule_sdf(x,y,z,(-.25,-.42,-.12),(.68,-.63,-.25),.23)
        wing1 = _capsule_sdf(x,y,z,(-.18,.48,.18),(.30,.84,.10),.13)
        wing2 = _capsule_sdf(x,y,z,(-.18,-.48,.18),(.30,-.84,.10),.13)
        outer = _smooth_min(_smooth_min(_smooth_min(_smooth_min(body, thigh1,.10),thigh2,.10),wing1,.06),wing2,.06)
        cavity = _ellipsoid_sdf(x-.12,y,z,(.43,.30,.30),2.0)
        return np.maximum(outer, -cavity)
    raise ValueError(f"unknown preset {kind!r}")


def _unit_volume(kind: str) -> float:
    # Deterministic midpoint integration; cached by the tiny preset count.
    n = 96
    a = np.linspace(-1.35, 1.35, n, endpoint=False) + 1.35/n
    x,y,z = np.meshgrid(a,a,a,indexing="ij")
    return float((_unit_sdf(kind,x,y,z)<=0).sum()) * (2.7/n)**3

_VOLUME_CACHE = {}


def _grid_unit_volume(kind: str, n: int) -> float:
    """Volume represented by this exact binary grid (removes mass bias)."""
    key=(kind,n)
    if key not in _VOLUME_CACHE:
        axis=np.linspace(-1.38,1.38,n)
        x,y,z=np.meshgrid(axis,axis,axis,indexing="ij")
        _VOLUME_CACHE[key]=float((_unit_sdf(kind,x,y,z)<=0).sum())*(2.76/(n-1))**3
    return _VOLUME_CACHE[key]


def make_geometry(kind="roast", mass_kg=1.5, n=48, density_kg_m3=1060.0) -> GridGeometry:
    """Voxelize a preset, scaling its volume to ``mass_kg / density``.

    ``n`` is the longest grid dimension including a three-cell air margin.
    Typical interactive/reference runs use 40--80; validation can use more.
    """
    if kind not in ("roast", "bird", "slab", "ham"):
        raise ValueError("kind must be roast, bird, slab, or ham")
    if mass_kg <= 0 or n < 12:
        raise ValueError("positive mass and n >= 12 required")
    # Scale against the volume represented at this resolution, rather than
    # only the continuum volume, so input mass is conserved exactly.
    uv = _grid_unit_volume(kind,n)
    scale = (mass_kg/density_kg_m3/uv)**(1/3)
    extent = 1.38*scale
    dx = 2*extent/(n-1)
    axis = np.linspace(-extent, extent, n)
    x,y,z=np.meshgrid(axis,axis,axis,indexing="ij")
    phi = scale*_unit_sdf(kind,x/scale,y/scale,z/scale)
    inside = phi <= 0

    gx,gy,gz=np.gradient(phi,dx,edge_order=2)
    norm=np.sqrt(gx*gx+gy*gy+gz*gz)
    normals=np.stack((gx/(norm+1e-12),gy/(norm+1e-12),gz/(norm+1e-12)),axis=-1).astype(np.float32)

    # Sign-changing links represent projected area. Correct each by local
    # |nx|+|ny|+|nz| to recover an orientation-independent surface measure.
    area=np.zeros(phi.shape,dtype=np.float64)
    for ax in range(3):
        lo=[slice(None)]*3; hi=[slice(None)]*3
        lo[ax]=slice(0,-1); hi[ax]=slice(1,None)
        lo=tuple(lo); hi=tuple(hi)
        cross=inside[lo] != inside[hi]
        # Attach the face to whichever adjacent cell is inside.
        for idx, mine, other in ((lo,inside[lo],inside[hi]),(hi,inside[hi],inside[lo])):
            target=area[idx]
            nn=normals[idx]
            l1=np.abs(nn).sum(axis=-1)
            target += (mine & cross) * (dx*dx/np.maximum(l1, .35))
    boundary=inside & (area>0)
    pan = boundary & (normals[...,2] < -.55) & (z < (-.25*scale))
    return GridGeometry(phi.astype(np.float32),inside,normals,area.astype(np.float32),
                        (area/dx**2).astype(np.float32),pan,dx,(-extent,)*3)
