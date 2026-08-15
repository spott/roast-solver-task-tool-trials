import numpy as np

from roast_solver.solver import explicit_dirichlet_box


def _error(n: int) -> float:
    length = 0.04
    alpha = 1.3e-7
    h = length / (n - 1)
    x = np.linspace(0.0, length, n)
    xx, yy, zz = np.meshgrid(x, x, x, indexing="ij")
    initial = np.sin(np.pi * xx / length) * np.sin(np.pi * yy / length) * np.sin(np.pi * zz / length)
    dt = 0.12 * h * h / alpha
    steps = max(1, round(120.0 / dt))
    elapsed = steps * dt
    numerical = explicit_dirichlet_box(initial, h, alpha, 0.0, dt, steps)
    exact = initial * np.exp(-3.0 * np.pi**2 * alpha * elapsed / length**2)
    return float(np.sqrt(np.mean((numerical - exact) ** 2)))


def test_dirichlet_box_converges_second_order_in_space():
    coarse = _error(15)
    fine = _error(29)
    assert fine < coarse / 3.2


def test_dirichlet_rejects_unstable_step():
    with np.testing.assert_raises(ValueError):
        explicit_dirichlet_box(np.zeros((5, 5, 5)), 0.001, 1e-7, 20, 2.0, 1)
