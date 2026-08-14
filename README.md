# Roast Solver

Roast Solver is a local-first 3D heat-transfer simulator for roasting and
carryover rest. This repository implements milestones **M1–M6** from
[`PROJECT_PLAN.md`](PROJECT_PLAN.md): a readable NumPy reference, a matching
Rust/WASM browser core, analytic and regression validation, progressive worker
execution, and a production-buildable static interface.

> **Model status:** validated against analytic and deterministic synthetic
> fixtures, but **not empirically calibrated**. No real probe logs were
> supplied. Outputs are engineering estimates, not food-safety advice.

M7 WebGPU and M8 photo reconstruction are intentionally not implemented.

## Try it locally

[Nix](https://nixos.org/) with flakes enabled is the supported reproducible
environment:

```sh
nix develop
npm test                 # NumPy, native Rust, and JavaScript source checks
npm run build            # release WASM + static site in dist/
npm run check:web        # inspect production asset/UI contracts
npm run preview          # http://127.0.0.1:4173
```

Open the printed URL; do not open `index.html` with `file://`, because module
workers and WASM require HTTP. `npm run preview -- --port 8080` selects another
port. The preview server binds only to `127.0.0.1` by default; use
`--host 0.0.0.0` deliberately to expose it on the local network.

The UI accepts shape, mass, initial/oven/pull temperatures, airflow, covered
state, emissivity, grid resolution, maximum roast time, and rest conditions.
It streams coldest/center/mean curves and a center-plane temperature or
relative-doneness slice while running, and reports pull time, peak after rest,
carryover, and an optional illustrative pasteurization equivalent.

### Without Nix

Install Python 3.11+ with NumPy/pytest, a current Rust toolchain with the
`wasm32-unknown-unknown` target, `wasm-pack`, and Node 20+. Then use the same
`npm` commands. There are no npm runtime dependencies and no install step.

## Reference solver

Run the inspectable NumPy implementation directly:

```sh
nix develop -c bash -lc \
  'PYTHONPATH=python python -m roast_solver.cli \
   --preset roast --mass 2 --oven 180 --initial 5 --target 58'
```

It prints JSON containing the roast/rest curve, pull and peak summaries,
pasteurization integral, energy ledger, and final center slice. Available
presets are `roast`, `bird`, `slab`, and `ham`; `--help` lists all options.

Useful focused checks:

```sh
nix develop -c npm run test:python
nix develop -c npm run test:rust
nix develop -c npm run test:web
nix develop -c bash -lc \
  'PYTHONPATH=python python python/scripts/validate_sphere.py'
```

`nix flake check` independently builds and runs the Python and Rust checks and
builds the production static package. `nix build` produces the deployable site
at `result/` without creating `dist/` in the worktree.

## Production build and static hosting

```sh
nix develop -c npm run build
# upload the contents of dist/, preserving paths and MIME types
```

The result has no server-side component and can be hosted at a path root on
GitHub Pages, Netlify, Cloudflare Pages, S3, nginx, or any equivalent static
host. Configure `.wasm` as `application/wasm` and serve over HTTPS in
production. All asset URLs are relative, so a repository subpath works. The
included preview server also emits COOP/COEP headers, though this CPU/WASM
version does not require shared memory. Simulation data stays in the browser.

## Architecture

```text
python/roast_solver/       NumPy physics/property/SDF oracle and CLI
python/tests/              analytic, convergence, energy, and feature tests
web-core/src/lib.rs        f64 Rust port; native library + wasm-bindgen API
web-core/tests/golden.rs   Python↔Rust fixture regression tests
web/worker.js              chunked/cancellable WASM execution
web/                       dependency-free HTML/CSS/Canvas interface
fixtures/                  explicitly synthetic calibration and parity data
docs/                      physics, validation, calibration, parity details
```

Both CPU implementations use the same Choi–Okos lean-meat property mixture,
analytic SDF presets, 3× sub-cell occupancy quadrature, finite-volume-like
shared-face conduction, SDF embedded surface areas, a 0.25 effective cut-cell
volume floor, convection, lagged T⁴ radiation, independent finite moisture per
surface cell, crust transition, pan insulation, and ambient/foil rest. The
explicit timestep is stability bounded. Surface energy and lagged discrete
enthalpy are reconciled every step.

The browser runs that Rust model in a module worker and yields between short
simulated-time chunks, keeping rendering and cancellation responsive. It is a
CPU baseline, not WebGPU. The NumPy-generated
[`fixtures/rust_golden.tsv`](fixtures/rust_golden.tsv) checks property,
geometry, trajectory, moisture, rest, and energy parity in native Rust tests.
See:

- [`docs/PHYSICS.md`](docs/PHYSICS.md) — equations and numerical choices
- [`docs/VALIDATION.md`](docs/VALIDATION.md) — analytic and convergence evidence
- [`docs/PARITY.md`](docs/PARITY.md) — Python/Rust/WASM consistency contract
- [`docs/CALIBRATION.md`](docs/CALIBRATION.md) — synthetic-fixture provenance

## Validation summary

The permanent tests cover property ranges, all SDF presets, sphere volume and
area, an interior Dirichlet mode, spatial behavior, a convective Robin sphere,
roundoff-level discrete energy accounting, radiation, staged evaporation,
pan insulation, rest/carryover, pasteurization integration, and fixture
provenance. At the UI's balanced 26³ resolution, the documented Robin sphere
center-temperature-ratio error is `0.00006476` (well below the milestone's 1%
target for that case). This numerical benchmark is not evidence of real-food
accuracy.

The fixture generator is deterministic:

```sh
nix develop -c bash -lc \
  'PYTHONPATH=python python python/scripts/generate_rust_golden.py'
```

Treat any golden change as a reviewed physics change. Never regenerate it just
to silence a failed parity test.

## Scope and limitations

- Geometry is an idealized mass-scaled preset, not a scan of the actual food.
- Meat is homogeneous; bones, fat layers, anisotropy, shrinkage, and phase
  change inside the food are not represented.
- Oven temperature and transfer coefficients are uniform engineering inputs.
- Evaporation/wet-surface and foil closures are documented synthetic choices.
- Surface moisture affects evaporative flux but mass/shape shrinkage is absent.
- The displayed center plane is a slice, not an M7 3D WebGPU isosurface.
- Pasteurization defaults are configurable mathematical examples, not a
  validated process or replacement for official time/temperature guidance and
  a calibrated thermometer.

For empirical calibration, retain raw probe logs, declared oven and geometry
metadata, train/validation splits, parameter bounds, solver version, and error
metrics as described in [`docs/CALIBRATION.md`](docs/CALIBRATION.md).

## License

[MIT](LICENSE)
