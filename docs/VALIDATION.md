# Validation and synthetic fixtures

Validation is numerical, not empirical. **No real probe logs are included and
this version is not empirically calibrated.**

## Executable checks

| Check | Location | Purpose |
|---|---|---|
| Choi–Okos ranges | `tests/test_properties.py` | property units/ranges |
| Dirichlet cube | `diffuse_dirichlet_box`, tests | M2 stability, symmetry, convergence anchor |
| Robin sphere series | `sphere_center_ratio` | roots of `1 - lambda cot(lambda) = Bi` |
| Embedded sphere | `embedded_sphere_check` | centre curve and reconstructed area against analytic sphere |
| Energy ledger | `energy_budget_check`, tests | integrated surface power = discrete sensible-energy change |
| Resolution sequence | `resolution_convergence` | reports cold-point movement with grid refinement |
| Rust/Python golden | `fixtures/web_kernel_golden.csv` | exact Float32 seven-point kernel sequence |

Run the complete fast suite with `pytest` and `cargo test --manifest-path
rust-core/Cargo.toml`. Run the more expensive report with:

```sh
python -m roast_solver.cli --validate --resolution 72
```

The plan's <1% sphere-centre target is a **production-resolution acceptance
target**, not a blanket accuracy claim. It is executable in the test suite. A
checked 72-cell run at 1,800 s produced reduced-temperature error 0.0164%, Bi
1.210, Fo 0.0642, and reconstructed-area ratio 1.072. A 32-cell CI anchor
produced 0.0120% and area ratio 1.056. Values can vary slightly with NumPy and
platform; the command reports all terms rather than hiding geometry error. At
coarse interactive resolution, geometry error is expected to dominate. The
energy report's residual was 1.4e-16 relative in the checked run because
conservation is algebraic.

Baldwin/high-h water-bath, slab, and cylinder comparisons are useful external
regression anchors, but published tables combine geometry/property assumptions
that are not fixtures in this repository. They are therefore not presented as
a fitted validation result.

## Synthetic calibration fixtures

`fixtures/synthetic_roast_calibration.json` contains two deliberately synthetic
one-hour forward runs (an uncovered roast and a covered fan-heated slab), with
the exact assumed h, emissivity, and moisture values embedded in each config.
It exists to exercise calibration/regression plumbing, **not** because those
parameters were fitted. Regenerate it with
`scripts/generate_synthetic_calibration.py`; CI reruns and compares the first
scenario, including the fixed deep-probe curve.

`fixtures/web_kernel_golden.csv` is likewise deliberately synthetic: a 9³ cube,
Dirichlet faces at reduced temperature 1, interior 0, and Fourier number per
step `r = 0.1`. `scripts/generate_golden.py` generates centre values with NumPy;
Rust tests consume the checked-in values. It validates indexing, update order,
and Float32 arithmetic across ports. It is **not food data** and does not tune
convection, emissivity, moisture, or material properties.

The model exposes these engineering defaults rather than pretending they were
identified: h = 10/20 W m⁻² K⁻¹, emissivity 0.90, and initial surface reservoir
0.25 kg m⁻². Future probe calibration should version raw logs, loss function,
train/holdout split, and fitted parameter uncertainty.
