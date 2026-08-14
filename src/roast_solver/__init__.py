"""NumPy reference implementation for Roast Solver milestones M1--M4."""

from .geometry import GridGeometry, make_preset, voxelize
from .solver import Environment, Simulation, SolverConfig, run_roast_and_rest

__all__ = [
    "Environment",
    "GridGeometry",
    "Simulation",
    "SolverConfig",
    "make_preset",
    "run_roast_and_rest",
    "voxelize",
]

__version__ = "0.1.0"
