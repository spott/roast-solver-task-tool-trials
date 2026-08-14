"""Analytic and conservation validation helpers.

These checks are intentionally separate from calibration.  They test numerical
physics against manufactured/closed-form cases and contain no food probe data.
"""
from __future__ import annotations
import math
import numpy as np

from .solver import RoastSolver, SolverConfig
from .sdf import voxelize
from .properties import meat_properties


def _bisect(fn, a, b, iterations=80):
    fa = fn(a)
    for _ in range(iterations):
        m = (a+b)/2; fm = fn(m)
        if fa*fm <= 0: b = m
        else: a, fa = m, fm
    return (a+b)/2


def sphere_eigenvalues(bi: float, count: int = 40):
    """Roots of ``1 - λ cot(λ) = Bi`` (convective sphere)."""
    if bi <= 0: raise ValueError("Bi must be positive")
    roots = []
    f = lambda x: 1.0 - x/math.tan(x) - bi
    eps = 1e-9
    # one root in a suitable branch of each pi interval; scan avoids special
    # handling on either side of Bi=1.
    x0 = eps; f0 = f(x0)
    step = math.pi/300
    x = step
    while len(roots) < count and x < (count+3)*math.pi:
        # Never bridge a cotangent pole.
        if int(x0/math.pi) == int(x/math.pi):
            fx = f(x)
            if f0*fx < 0: roots.append(_bisect(f, x0, x))
            f0 = fx
        else:
            f0 = f(x)
        x0 = x; x += step
    return np.asarray(roots[:count])


def sphere_center_ratio(fourier: float | np.ndarray, bi: float, terms=40):
    """Exact center reduced temperature for a sphere with a Robin boundary."""
    lam = sphere_eigenvalues(bi, terms)
    coeff = 4*(np.sin(lam)-lam*np.cos(lam))/(2*lam-np.sin(2*lam))
    fo = np.atleast_1d(fourier)
    out = np.sum(coeff[:,None]*np.exp(-lam[:,None]**2*fo[None,:]), axis=0)
    # The discontinuous initial/boundary compatibility makes the truncated
    # series converge slowly at exactly t=0; enforce its known initial value.
    out[fo == 0] = 1.0
    return out if np.ndim(fourier) else float(out[0])


def embedded_sphere_check(resolution=72, elapsed_s=1800.0, radius_mass_kg=1.0):
    """Run the embedded sphere with convection only and compare its centre.

    Property variation is lagged in the numerical model, so the analytic anchor
    uses properties at the mean of initial and current centre temperature.  The
    result reports, rather than hides, geometric and property-model error.
    """
    cfg = SolverConfig(preset="sphere", mass_kg=radius_mass_kg, resolution=resolution,
        initial_c=20, oven_c=100, target_c=200, emissivity=0, moisture_kg_m2=0,
        h_still=10, max_roast_hours=elapsed_s/3600, rest_minutes=0,
        sample_seconds=elapsed_s)
    solver = RoastSolver(cfg)
    while solver.time_s < elapsed_s:
        solver.step(min(solver.stable_timestep(), elapsed_s-solver.time_s))
    g = solver.geometry
    center = tuple(v//2 for v in g.inside.shape)
    tc = float(solver.temperature[center])
    rho, cp, k = [float(v) for v in meat_properties(np.asarray((20+tc)/2))]
    radius = (3*g.volume/(4*math.pi))**(1/3)
    bi = cfg.h_still*radius/k
    fo = (k/(rho*cp))*elapsed_s/radius**2
    exact = cfg.oven_c-(cfg.oven_c-cfg.initial_c)*sphere_center_ratio(fo, bi)
    return {"numerical_c": tc, "analytic_c": exact, "error_c": tc-exact,
            "relative_reduced_error": abs(tc-exact)/(cfg.oven_c-cfg.initial_c),
            "bi": bi, "fourier": fo,
            "area_ratio": float(g.surface_area.sum()/(4*math.pi*radius**2))}


def energy_budget_check(resolution=32, steps=40):
    cfg = SolverConfig(preset="sphere", mass_kg=0.5, resolution=resolution,
        initial_c=20, oven_c=120, moisture_kg_m2=0.05)
    s = RoastSolver(cfg)
    for _ in range(steps): s.step()
    return {"input_j": s.ledger.boundary_input_j,
            "body_j": s.ledger.body_sensible_j,
            "residual_j": s.ledger.residual_j,
            "relative": abs(s.ledger.residual_j)/max(abs(s.ledger.boundary_input_j), 1)}


def resolution_convergence(resolutions=(24, 32, 44), elapsed_s=600):
    values = []
    for n in resolutions:
        cfg = SolverConfig(resolution=n, max_roast_hours=elapsed_s/3600,
                           target_c=200, rest_minutes=0, sample_seconds=elapsed_s)
        r = RoastSolver(cfg)
        while r.time_s < elapsed_s: r.step(min(r.stable_timestep(), elapsed_s-r.time_s))
        values.append(float(np.min(r.temperature[r.geometry.inside])))
    return dict(zip(resolutions, values))
