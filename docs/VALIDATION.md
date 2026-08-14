# Validation status

Run all permanent checks with `pytest` from `python/`. They cover Choi–Okos
property ranges, required SDFs, sphere volume/area, the M2 Dirichlet cube mode
and spatial convergence, M3 Robin sphere and exact discrete energy balance,
resolution behavior, staged per-cell evaporation, pan insulation, radiation,
rest/carryover, pasteurization integration, and fixture provenance.

`PYTHONPATH=python python python/scripts/validate_sphere.py` reproduces the
Robin sphere evidence (`Bi=2`, `Fo=0.1`). On the pinned environment:

| box cells/axis | center ratio | absolute error vs series | area/exact |
|---:|---:|---:|---:|
| 18 | 0.91073338 | 0.00166084 | 0.96967834 |
| 26 | 0.91232946 | 0.00006476 | 0.97000021 |
| 36 | 0.91357030 | 0.00117608 | 0.97114241 |

The exact center ratio is 0.91239422. Thus the tested production-like 26-cell
case is below the project's 1% center-temperature-ratio target. The result is
not claimed monotonic at every grid because sub-cell quadrature topology
changes discretely; the permanent coarse-to-fine test checks the broader
trend. Energy residual in this check is around floating-point roundoff.

These are numerical/analytic checks, not real-food accuracy evidence. External
Baldwin/chart comparison remains a broad sanity check rather than calibration;
no external table data is copied into this repository.
