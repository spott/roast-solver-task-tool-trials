# Roast Solver

A complete, locally hostable M1–M6 web application that predicts 3-D internal time–temperature fields for roasts and poultry. It solves the heat equation with an SDF geometry contract, embedded-boundary Robin flux, convection, radiation, per-surface-cell evaporation, and rest/carryover. The production UI runs the Rust/WASM core in a Web Worker and needs no server API.

> **Calibration and safety:** all baseline coefficients and the included fixture are analytic, published-property, or explicitly **synthetic**. No real probe logs were provided, so this project makes no empirical-accuracy claim. Pasteurization output is a simplified conservative model result, not food-safety advice. Verify food with a calibrated thermometer and follow local guidance.

The authoritative product/physics scope is [`PROJECT_PLAN.md`](PROJECT_PLAN.md). M7 WebGPU and M8 photo reconstruction are intentionally not implemented.

## Quick start with Nix

Nix supplies Python/NumPy/pytest, Node, Rust with the WASM target, and `lld`:

```sh
nix develop
python -m pytest                 # Python reference and golden tests
cargo test --manifest-path rust_core/Cargo.toml
npm test
npm run build                    # production app in dist/
npm run preview                  # http://127.0.0.1:4173
```

Run the reference CLI:

```sh
python -m roast_solver.cli --validate --resolution 32
python -m roast_solver.cli --preset roast --mass 1.5 --resolution 24 \
  --oven 180 --initial 5 --target 60 --convection
```

One-command reproducible checks and package build:

```sh
nix flake check
nix build                         # static site is linked at result/
nix run nixpkgs#python3 -- -m http.server -d result 8000
```

During review of an uncommitted worktree, use `nix flake check path:.` / `nix build path:.` so Nix includes new untracked files.

## Setup without Nix

Requirements: Python 3.10+ with NumPy and pytest, Node 20+, and Rust/Cargo with `wasm32-unknown-unknown` plus an LLVM WASM linker.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
rustup target add wasm32-unknown-unknown
python -m pytest
cargo test --manifest-path rust_core/Cargo.toml
npm test && npm run build && npm run preview
```

If `npm run build` reports `lld` missing, install LLVM `lld` or use `nix develop`. There are no npm or Cargo package dependencies to download.

## What is implemented

- **M1:** temperature-dependent Choi–Okos lean-meat properties; superellipsoid roast, body/limb/cavity bird, rounded slab, and teardrop ham SDF presets.
- **M2:** Float32 explicit 3-D seven-point solver with lagged properties and a manufactured Dirichlet convergence test.
- **M3:** SDF normals, projected cut-cell surface area, center-to-interface Robin resistance, analytic convective sphere series, and exact discrete energy accounting.
- **M4:** lagged radiation, Lewis-analogy evaporation with an independent reservoir/dry-crust stage on every surface cell, insulated pan patch, covered mode, ambient/foil rest, pull-time cold-spot carryover, and coldest-point pasteurization integral.
- **M5:** dependency-free Rust port, `wasm32` SIMD release, Python-generated property/stencil/full-run goldens, and bounded progressive worker execution.
- **M6:** production static UI with required inputs, coldest/center curves, prior-run what-if overlay, pull/carryover/peak results, advanced pasteurization readout, and scrubbable temperature/doneness slices from the actual 3-D field.

## Architecture

```text
analytic preset SDF
  -> occupancy + phi + normals + embedded area + pan patch
  -> conservative 3-D explicit solver
  -> temperature field + per-cell moisture state
  -> coldest/probe curves + pull/rest + pasteurization
  -> Worker snapshots -> static Canvas UI
```

The Python oracle is in [`roast_solver/`](roast_solver/); the browser port and C ABI are in [`rust_core/`](rust_core/); static sources are in [`web/`](web/). The solver consumes only voxelized SDF products, so a future geometry source can be added without changing the thermal kernel.

Numerical and modeling details:

- [`docs/PHYSICS.md`](docs/PHYSICS.md) — properties, embedded boundary, evaporation, energy accounting, calibration status
- [`docs/WASM_CORE.md`](docs/WASM_CORE.md) — ABI, SIMD build, Python/Rust parity
- [`docs/WEB_UI.md`](docs/WEB_UI.md) — worker progression and visualization

## Validation evidence

At 32 cells across a sphere diameter (`Bi = 0.5`, `Fo = 0.2`):

| Check | Result | Acceptance |
|---|---:|---:|
| center dimensionless-temperature relative error | 0.048% | < 1% |
| embedded area relative error | 1.04% | < 2% test limit |
| discrete surface-energy residual | floating-point zero | < 1e-10 fraction |

The suite also covers second-order Dirichlet convergence, infinite-slab Robin resolution convergence, a high-transfer `Bi=20` water-bath/interior anchor, geometry volume/normal contracts, radiation, wet-reservoir depletion and dry-crust transition, covered evaporation, rest carryover, and synthetic fixture stability. `fixtures/core_golden_v1.csv` is consumed by both Python and Rust; its full cook/rest case has exact pull-time agreement, <0.01°C carryover difference, and <0.5% pasteurization-integral difference.

Regenerate fixtures only after an intentional oracle change:

```sh
python scripts/generate_synthetic_fixture.py
python scripts/generate_core_golden.py
python -m pytest && cargo test --manifest-path rust_core/Cargo.toml
```

## Production build and static hosting

`npm run build` compiles `rust_core` with `-C target-feature=+simd128` and writes a self-contained `dist/` containing HTML, CSS, ES modules, Worker code, and `roast_core.wasm`. Serve it over HTTP; opening `index.html` via `file://` will not reliably allow Worker/WASM fetches.

Upload the **contents** of `dist/` (or the Nix `result/`) to any static host: GitHub Pages, Netlify, Cloudflare Pages, S3, nginx, Caddy, etc. Configure:

- `*.wasm` as `application/wasm` (the included preview does this);
- normal static handling for `.html`, `.css`, and `.js`;
- HTTPS in production, as expected by modern browser worker policies.

No rewrite, backend, database, environment variables, telemetry, external fonts, or network API is required. Modern Chromium, Firefox, and Safari versions with WebAssembly, SIMD, ES modules, Canvas, and module Workers are supported.

## Performance and interpretation

The UI defaults to a 24-cell longest shape span (plus padding), which is responsive on typical laptops. 18 is useful for what-if iteration; 32–40 is for finer/validation runs. Runtime scales roughly with voxel count and explicit time-step count. The browser resolution is intentionally capped at 64 before M7 GPU work.

The red curve is the instantaneous coldest occupied cell; the green curve is a fixed geometric-center probe. Pull occurs when the entire occupied field reaches the target. Carryover is then followed at the stable pull-time coldest cell. Covered mode suppresses evaporation and foil changes rest convection/emissivity.
