"""NumPy reference implementation for Roast Solver."""

from .geometry import Grid, Geometry, make_geometry
from .solver import BoundaryConfig, SimulationConfig, SimulationResult, simulate

__all__ = [
    "Grid", "Geometry", "make_geometry", "BoundaryConfig", "SimulationConfig",
    "SimulationResult", "simulate",
]
