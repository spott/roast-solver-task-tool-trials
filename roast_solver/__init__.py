"""Reference physics implementation for Roast Solver (SI units internally)."""

from .geometry import GridGeometry, make_geometry
from .solver import BoundaryConfig, SimulationConfig, SimulationResult, simulate

__all__ = [
    "GridGeometry",
    "make_geometry",
    "BoundaryConfig",
    "SimulationConfig",
    "SimulationResult",
    "simulate",
]
