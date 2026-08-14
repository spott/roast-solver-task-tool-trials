"""Analytic and discrete validation anchors for the reference solver."""
from __future__ import annotations

import math
import numpy as np

from .geometry import SDFGeometry, voxelize
from .properties import meat_properties
from .solver import Environment, Simulation, SolverConfig


def sphere_eigenvalues(biot: float, count: int = 40) -> np.ndarray:
    """Roots of ``1 - lambda*cot(lambda) = Bi`` by robust bisection."""
    if biot <= 0:
        raise ValueError("Biot number must be positive")
    roots = []
    for n in range(count):
        lo = n*math.pi + 1e-9 if n else 1e-9
        hi = (n+1)*math.pi - 1e-9
        def f(x):
            return 1.0-x/math.tan(x)-biot
        flo = f(lo)
        for _ in range(90):
            mid = (lo+hi)/2
            fm = f(mid)
            if (fm > 0) == (flo > 0):
                lo, flo = mid, fm
            else:
                hi = mid
        roots.append((lo+hi)/2)
    return np.asarray(roots)


def sphere_center_ratio(biot: float, fourier: float, terms: int = 60) -> float:
    """Exact center dimensionless temperature for a convective sphere."""
    lam = sphere_eigenvalues(biot, terms)
    coeff = 4*(np.sin(lam)-lam*np.cos(lam))/(2*lam-np.sin(2*lam))
    return float(np.sum(coeff*np.exp(-lam*lam*fourier)))


def embedded_sphere_case(radius_m: float = 0.04, cells_per_radius: int = 18,
                         initial_c: float = 20.0, ambient_c: float = 30.0,
                         h_conv: float = 10.0, fourier: float = 0.08) -> dict:
    shape = SDFGeometry("validation-sphere",
                        lambda x,y,z: np.sqrt(x*x+y*y+z*z)-radius_m,
                        ((-radius_m,radius_m),)*3, 4*math.pi*radius_m**3/3)
    grid = voxelize(shape, radius_m/cells_per_radius, 2)
    rho, cp, k = meat_properties(initial_c)
    alpha = k/(rho*cp)
    duration = fourier*radius_m**2/alpha
    sim = Simulation(grid, SolverConfig(initial_temp_c=initial_c,
                                         moisture_reservoir_kg_m2=0.0,
                                         dtype="float64"))
    env = Environment(ambient_c, ambient_c, h_conv, 0.0, 1.0, True, False)
    sim.run_for(duration, env, "validation", duration)
    center = float(sim.temperature_c[sim._probe_index])
    numerical_ratio = (center-ambient_c)/(initial_c-ambient_c)
    biot = h_conv*radius_m/k
    exact_ratio = sphere_center_ratio(biot, fourier)
    return {
        "cells_per_radius": cells_per_radius,
        "grid_shape": grid.phi.shape,
        "biot": biot,
        "fourier": fourier,
        "numerical_center_ratio": numerical_ratio,
        "exact_center_ratio": exact_ratio,
        "relative_error": abs(numerical_ratio-exact_ratio)/abs(exact_ratio),
        "area_relative_error": abs(grid.surface_area_total_m2-4*math.pi*radius_m**2)/(4*math.pi*radius_m**2),
        "energy_relative_error": sim.energy_relative_error(),
    }


def slab_center_ratio(biot: float, fourier: float, terms: int = 50) -> float:
    """Exact plane-wall center ratio (half-thickness length scale)."""
    roots = []
    for n in range(terms):
        lo, hi = n*math.pi+1e-10, n*math.pi+math.pi/2-1e-10
        for _ in range(80):
            mid = (lo+hi)/2
            if mid*math.tan(mid) < biot:
                lo = mid
            else:
                hi = mid
        roots.append((lo+hi)/2)
    lam = np.asarray(roots)
    coeff = 4*np.sin(lam)/(2*lam+np.sin(2*lam))
    return float(np.sum(coeff*np.exp(-lam*lam*fourier)))


def _bessel_j(order: int, x: float) -> float:
    """J0/J1 power series; validation-only, avoiding a SciPy dependency."""
    term = (x/2)**order/math.factorial(order)
    total = term
    for m in range(1, 180):
        term *= -(x*x/4)/(m*(m+order))
        total += term
        if abs(term) < 1e-16*max(1,abs(total)):
            break
    return total


def cylinder_center_ratio(biot: float, fourier: float, terms: int = 12) -> float:
    """Exact infinite-cylinder center ratio for a convective radial boundary."""
    def characteristic(x):
        return x*_bessel_j(1,x)-biot*_bessel_j(0,x)
    roots=[]
    x0=1e-8
    f0=characteristic(x0)
    step=0.025
    x=x0+step
    while len(roots)<terms and x<terms*math.pi+10:
        f=characteristic(x)
        if f*f0 < 0:
            lo,hi=x-step,x
            flo=f0
            for _ in range(70):
                mid=(lo+hi)/2
                fm=characteristic(mid)
                if fm*flo>0: lo,flo=mid,fm
                else: hi=mid
            roots.append((lo+hi)/2)
        x0,f0,x,f=x,f,x+step,f
    lam=np.asarray(roots)
    j0=np.asarray([_bessel_j(0,float(v)) for v in lam])
    j1=np.asarray([_bessel_j(1,float(v)) for v in lam])
    coeff=2*j1/(lam*(j0*j0+j1*j1))
    return float(np.sum(coeff*np.exp(-lam*lam*fourier)))


def dirichlet_box_mode(n: int, steps: int, diffusivity: float = 1.3e-7,
                        length_m: float = 0.1, cfl: float = 0.7) -> dict:
    """Evolve the sin(pi*x/L)sin(pi*y/L)sin(pi*z/L) Dirichlet eigenmode."""
    if n < 5:
        raise ValueError("n must be at least 5")
    h = length_m/(n-1)
    dt = cfl*h*h/(6*diffusivity)
    xyz = np.linspace(0,length_m,n)
    x,y,z = np.meshgrid(xyz,xyz,xyz,indexing="ij",sparse=True)
    initial = np.sin(math.pi*x/length_m)*np.sin(math.pi*y/length_m)*np.sin(math.pi*z/length_m)
    u = np.asarray(initial, dtype=np.float64)
    r = diffusivity*dt/h**2
    for _ in range(steps):
        v = u.copy()
        v[1:-1,1:-1,1:-1] = u[1:-1,1:-1,1:-1] + r*(
            u[2:,1:-1,1:-1]+u[:-2,1:-1,1:-1]+u[1:-1,2:,1:-1]+
            u[1:-1,:-2,1:-1]+u[1:-1,1:-1,2:]+u[1:-1,1:-1,:-2]-
            6*u[1:-1,1:-1,1:-1])
        u = v
    time_s = steps*dt
    exact = np.asarray(initial)*math.exp(-3*math.pi**2*diffusivity*time_s/length_m**2)
    error = np.sqrt(np.mean((u-exact)**2))/np.sqrt(np.mean(exact**2))
    return {"n":n, "steps":steps, "dt_s":dt, "relative_l2_error":float(error)}
