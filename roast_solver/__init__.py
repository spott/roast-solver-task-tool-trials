"""NumPy reference implementation for Roast Solver."""

from .geometry import GridGeometry, make_geometry
from .solver import Boundary, Solver, SimulationResult, simulate_roast

__all__ = [
    "Boundary", "GridGeometry", "SimulationResult", "Solver",
    "make_geometry", "simulate_roast",
]
