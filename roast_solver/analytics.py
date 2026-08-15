"""Analytic regression anchors for the validation suite."""
from __future__ import annotations

import math
import numpy as np

from .geometry import Geometry, Grid


def _bisect(function, lo: float, hi: float, iterations: int = 70) -> float:
    flo = function(lo)
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        fm = function(mid)
        if flo * fm <= 0:
            hi = mid
        else:
            lo, flo = mid, fm
    return 0.5 * (lo + hi)


def sphere_robin_eigenvalues(biot: float, count: int = 40) -> np.ndarray:
    """Roots of ``1 - lambda*cot(lambda) = Bi``."""
    if biot <= 0:
        raise ValueError("Biot number must be positive")
    roots: list[float] = []
    eps = 1e-9
    f = lambda x: 1.0 - x / math.tan(x) - biot
    for n in range(count):
        if biot < 1.0:
            lo = n * math.pi + eps if n else eps
            hi = n * math.pi + math.pi / 2.0 - eps
        elif biot > 1.0:
            lo = n * math.pi + math.pi / 2.0 + eps
            hi = (n + 1) * math.pi - eps
        else:
            roots.append((n + 0.5) * math.pi)
            continue
        roots.append(_bisect(f, lo, hi))
    return np.asarray(roots)


def robin_sphere_center_ratio(fourier: float | np.ndarray, biot: float, terms: int = 60) -> np.ndarray:
    """Exact center reduced temperature for a uniform sphere in a fluid."""
    fo = np.asarray(fourier, dtype=float)
    lam = sphere_robin_eigenvalues(biot, terms)
    coefficient = 4.0 * (np.sin(lam) - lam * np.cos(lam)) / (2.0 * lam - np.sin(2.0 * lam))
    return np.sum(coefficient.reshape((-1,) + (1,) * fo.ndim) * np.exp(-lam.reshape((-1,) + (1,) * fo.ndim) ** 2 * fo), axis=0)


def slab_robin_center_ratio(fourier: float | np.ndarray, biot: float, terms: int = 60) -> np.ndarray:
    """Exact center reduced temperature for a plane wall of half-thickness L."""
    fo = np.asarray(fourier, dtype=float)
    roots = []
    f = lambda x: x * math.tan(x) - biot
    for n in range(terms):
        roots.append(_bisect(f, n * math.pi + 1e-9, n * math.pi + math.pi / 2 - 1e-9))
    lam = np.asarray(roots)
    coefficient = 4.0 * np.sin(lam) / (2.0 * lam + np.sin(2.0 * lam))
    return np.sum(coefficient.reshape((-1,) + (1,) * fo.ndim) * np.exp(-lam.reshape((-1,) + (1,) * fo.ndim) ** 2 * fo), axis=0)


def make_sphere_geometry(radius_m: float, grid_size: int = 49, padding_cells: float = 2.5) -> Geometry:
    """Create the analytic sphere fixture using the production SDF contract."""
    spacing = 2.0 * radius_m / (grid_size - 1 - 2.0 * padding_cells)
    extent = spacing * (grid_size - 1) / 2.0
    q = np.linspace(-extent, extent, grid_size)
    grid = Grid(q, q.copy(), q.copy(), spacing)
    x, y, z = grid.xyz
    radius = np.sqrt(x * x + y * y + z * z)
    phi = radius - radius_m
    inside = phi <= 0
    mag = np.maximum(radius, 1e-12)
    normal = np.stack((x / mag, y / mag, z / mag), axis=-1).astype(np.float32)
    epsilon = 1.5 * spacing
    delta = np.where((phi <= 0) & (phi >= -epsilon), 2.0 * (1.0 + phi / epsilon) / epsilon, 0.0)
    area = (delta * spacing**3).astype(np.float32)
    pan = np.zeros(phi.shape, dtype=bool)
    return Geometry(
        "analytic-sphere", grid, phi.astype(np.float32), inside, normal, area,
        (area > 0).astype(np.float32), pan, 4.0 / 3.0 * math.pi * radius_m**3
    )
