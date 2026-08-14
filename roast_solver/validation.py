"""Small analytic/regression anchors for the embedded solver.

These routines favor transparent formulas over test-framework machinery. They
are used at modest resolution in CI; higher-resolution commands are documented
for release validation.
"""

import math
import numpy as np

from .geometry import make_geometry


def dirichlet_cube_mode_error(n: int, alpha=1.3e-7, length=0.1, duration_s=600.0) -> float:
    """L2 error for the separable first mode in a zero-Dirichlet cube."""
    h = length / (n - 1)
    dt_stable = h * h / (6 * alpha)
    steps = max(1, math.ceil(duration_s / (0.8 * dt_stable)))
    dt = duration_s / steps
    x = np.linspace(0, length, n)
    z, y, x3 = np.meshgrid(x, x, x, indexing="ij")
    initial = np.sin(math.pi * x3 / length) * np.sin(math.pi * y / length) * np.sin(math.pi * z / length)
    u = initial.copy()
    coefficient = alpha * dt / (h * h)
    for _ in range(steps):
        new = u.copy()
        new[1:-1, 1:-1, 1:-1] += coefficient * (
            u[2:, 1:-1, 1:-1] + u[:-2, 1:-1, 1:-1]
            + u[1:-1, 2:, 1:-1] + u[1:-1, :-2, 1:-1]
            + u[1:-1, 1:-1, 2:] + u[1:-1, 1:-1, :-2]
            - 6 * u[1:-1, 1:-1, 1:-1]
        )
        u = new
    exact = initial * math.exp(-3 * math.pi**2 * alpha * duration_s / length**2)
    return float(np.sqrt(np.mean((u - exact) ** 2)) / np.sqrt(np.mean(exact**2)))


def sphere_eigenvalues(biot: float, count=20) -> np.ndarray:
    """Roots of 1 - lambda*cot(lambda) = Bi for a sphere."""
    if biot <= 0:
        raise ValueError("Biot number must be positive")

    def f(x):
        return 1.0 - x / math.tan(x) - biot

    roots = []
    # A sign scan handles roots moving across pi/2 as Bi changes.
    x_prev = 1e-8
    f_prev = f(x_prev)
    step = math.pi / 500
    x = x_prev + step
    while len(roots) < count and x < (count + 4) * math.pi:
        if abs(math.sin(x)) < 1e-4:
            x_prev, f_prev = x + 2e-4, f(x + 2e-4)
            x += step
            continue
        fx = f(x)
        if f_prev * fx < 0:
            lo, hi = x_prev, x
            for _ in range(60):
                mid = 0.5 * (lo + hi)
                if f(lo) * f(mid) <= 0:
                    hi = mid
                else:
                    lo = mid
            root = 0.5 * (lo + hi)
            if not roots or root - roots[-1] > 1e-3:
                roots.append(root)
        x_prev, f_prev, x = x, fx, x + step
    return np.asarray(roots)


def robin_sphere_center_ratio(biot: float, fourier: float, terms=30) -> float:
    lambdas = sphere_eigenvalues(biot, terms)
    coeff = 4 * (np.sin(lambdas) - lambdas * np.cos(lambdas)) / (2 * lambdas - np.sin(2 * lambdas))
    return float(np.sum(coeff * np.exp(-(lambdas**2) * fourier)))


def embedded_sphere_constant(resolution=36, biot=2.0, fourier=0.15):
    """Numerical/analytic center ratio for constant properties and Robin heat.

    The numerical implementation deliberately mirrors the production embedded
    surface-area update but removes property and radiation complexity.
    """
    radius = 0.04
    k, rho, cp = 0.48, 1060.0, 3500.0
    alpha = k / (rho * cp)
    h_conv = biot * k / radius
    geom = make_geometry("sphere", 4 / 3 * math.pi * radius**3 * 1060, resolution)
    inside = geom.inside
    t = np.zeros(inside.shape, dtype=np.float64)  # dimensionless, ambient is 1
    duration = fourier * radius**2 / alpha
    dt_max = geom.spacing_m**2 / (6 * alpha)
    steps = math.ceil(duration / (0.75 * dt_max))
    dt = duration / steps
    area = geom.surface_area
    volume = geom.spacing_m**3
    for _ in range(steps):
        power = np.zeros(t.shape)
        for axis in range(3):
            lo, hi = [slice(None)] * 3, [slice(None)] * 3
            lo[axis], hi[axis] = slice(None, -1), slice(1, None)
            lo, hi = tuple(lo), tuple(hi)
            valid = inside[lo] & inside[hi]
            flux = np.where(valid, k * geom.spacing_m * (t[hi] - t[lo]), 0.0)
            power[lo] += flux
            power[hi] -= flux
        power += h_conv * (1 - t) * area
        t[inside] += dt * power[inside] / (rho * cp * volume)
    idx = np.argwhere(inside)
    center = tuple(idx[np.argmin(np.sum((idx - idx.mean(axis=0)) ** 2, axis=1))])
    numerical_theta = 1 - float(t[center])
    exact_theta = robin_sphere_center_ratio(biot, fourier)
    return {
        "numerical_center_ratio": numerical_theta,
        "exact_center_ratio": exact_theta,
        "relative_error": abs(numerical_theta - exact_theta) / exact_theta,
        "surface_area_m2": float(area.sum()),
        "exact_area_m2": 4 * math.pi * radius**2,
    }


def slab_eigenvalues(biot: float, count=30) -> np.ndarray:
    """Positive roots of lambda*tan(lambda)=Bi for a symmetric plane wall."""
    roots = []
    for n in range(count):
        lo = n * math.pi + 1e-10
        hi = n * math.pi + math.pi / 2 - 1e-10
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if mid * math.tan(mid) < biot:
                lo = mid
            else:
                hi = mid
        roots.append(0.5 * (lo + hi))
    return np.asarray(roots)


def slab_center_ratio(biot: float, fourier: float, terms=30) -> float:
    roots = slab_eigenvalues(biot, terms)
    coeff = 4 * np.sin(roots) / (2 * roots + np.sin(2 * roots))
    return float(np.sum(coeff * np.exp(-roots**2 * fourier)))


def slab_1d_constant(cells=80, biot=1.0, fourier=0.2) -> dict[str, float]:
    """Conservative half-slab numerical anchor against the Robin series."""
    length, alpha, k = 0.04, 1.3e-7, 0.48
    rho_cp = k / alpha
    h = length / cells
    h_conv = biot * k / length
    duration = fourier * length**2 / alpha
    steps = math.ceil(duration / (0.45 * h**2 / alpha))
    dt = duration / steps
    temperature = np.zeros(cells)
    for _ in range(steps):
        power = np.zeros(cells)
        flux = k / h * (temperature[1:] - temperature[:-1])
        power[:-1] += flux
        power[1:] -= flux
        power[-1] += h_conv * (1.0 - temperature[-1])
        temperature += dt * power / (rho_cp * h)
    numerical = 1.0 - float(temperature[0])
    exact = slab_center_ratio(biot, fourier)
    return {"numerical_center_ratio": numerical, "exact_center_ratio": exact, "relative_error": abs(numerical - exact) / exact}


def resolution_center_temperatures(resolutions=(20, 28, 36), **simulation_kwargs):
    """Convenience runner imported lazily to keep analytic checks lightweight."""
    from .solver import BoundaryConfig, SimulationConfig, simulate
    values = []
    for resolution in resolutions:
        geom = make_geometry("roast", 1.0, resolution)
        cfg = SimulationConfig(max_cook_s=simulation_kwargs.get("duration_s", 900), rest_s=0, target_c=200, sample_interval_s=900)
        result = simulate(geom, BoundaryConfig(oven_c=160, covered=True), cfg)
        values.append(float(result.coldest_c[-1]))
    return values
