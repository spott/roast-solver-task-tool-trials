"""Roast Solver NumPy reference implementation."""
from .boundary import BoundaryConditions
from .geometry import Geometry, make_geometry
from .solver import ExplicitSolver, SimulationResult, SolverConfig, simulate_preset

__all__ = [
    "BoundaryConditions",
    "ExplicitSolver",
    "Geometry",
    "SimulationResult",
    "SolverConfig",
    "make_geometry",
    "simulate_preset",
]

__version__ = "0.1.0"
