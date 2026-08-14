# Roast Solver

A locally hostable web app that predicts internal time–temperature curves by
solving the 3-D heat equation on parametric food geometry. This repository
implements milestones **M1 through M6** of [`PROJECT_PLAN.md`](PROJECT_PLAN.md):
a NumPy reference, validated embedded-boundary physics, a Rust/WASM port,
progressive worker execution, and a production static UI.

> **Modelling notice:** this is not food-safety advice and is not empirically
> calibrated. No real probe logs were supplied. The included “calibration”
> fixtures are clearly labelled, deterministic **synthetic model outputs**.

![Scope: M1–M6](https://img.shields.io/badge/scope-M1--M6-bd4a30)

## What works

- volume-scaled superellipsoid roast, composed bird with cavity/limbs, rounded
  slab, and teardrop ham SDF presets;
- temperature-dependent Choi–Okos lean-meat properties and Float32 3-D
  finite-volume/finite-difference evolution;
- SDF-normal-corrected embedded Robin boundary with convection, radiation,
  cell-local finite moisture reservoir/crust transition, covered mode, and
  insulated pan patch;
- continued ambient/foil-capable rest integration, pull-time cold-point probe,
  carryover peak/time, and cold-point P70 integral;
- exact sphere/slab/cylinder anchors, Dirichlet convergence, and discrete energy
  accounting;
- regression-locked Rust/WASM core with `simd128`, advanced progressively in a
  cancellable Web Worker;
- responsive static UI with inputs, what-if curve overlay, middle doneness
  slice, pull/carryover results, and advanced pasteurization readout.

M7 WebGPU and M8 photo reconstruction are intentionally not implemented.

## Quick start with Nix

Nix 2.18+ with flakes enabled is the reproducible path:

```sh
nix develop
# first frontend install
cd web && npm ci && cd ..

# run all source-level tests
pytest -q
cargo test --locked --manifest-path web-core/Cargo.toml

# regenerate WASM, typecheck, and make production static assets
cd web && npm run build

# preview: open http://localhost:8000
python -m http.server 8000 --directory dist
```

For a fully sandboxed static build and all flake checks:

```sh
nix flake check
nix build .#web
python -m http.server 8000 --directory result
```

`result/` is the complete deployable site. The app uploads no data and needs no
server-side runtime.

## Conventional setup

Required versions are Python 3.11+ with NumPy/pytest, stable Rust with the
`wasm32-unknown-unknown` target, `wasm-bindgen-cli` **0.2.95**, Binaryen
(`wasm-opt`), lld, and Node 20+.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'

cd web-core
cargo test --locked
cd ../web
npm ci
npm run build             # calls ../scripts/build-wasm.sh, then tsc + Vite
npm run preview           # Vite production preview
```

The wasm-bindgen CLI must match the pinned Rust crate. Nix supplies the matching
version. `npm run build:web` skips Rust regeneration and is useful only when the
checked/generated `web/src/wasm` is already current.

For live UI development:

```sh
./scripts/build-wasm.sh
cd web && npm run dev
```

The worker is rebuilt by Vite; rerun the WASM script after changing Rust.

## Tests and validation

```sh
# Python M1–M4 suite
PYTHONPATH=src pytest -q

# Rust properties, geometry, fixed-curve golden parity, progressive state
cargo test --locked --manifest-path web-core/Cargo.toml
cargo clippy --manifest-path web-core/Cargo.toml --all-targets -- -D warnings

# frontend static analysis, direct WASM smoke, and existing-WASM build
cd web && npm run typecheck && npm run smoke:wasm && npm run build:web

# regenerate deterministic synthetic oracle after an intentional model change
PYTHONPATH=src python scripts/generate_fixtures.py
```

The Robin sphere center error in the checked anchor is about 0.12% at 14 cells
per radius and about 0.03% at 32 cells per radius. Surface flux and discrete body
enthalpy agree to floating-point roundoff. These are numerical validations, not
real-food accuracy claims. See [`docs/PHYSICS.md`](docs/PHYSICS.md) for equations,
area treatment, test evidence, and assumptions; see
[`docs/WEB_CORE.md`](docs/WEB_CORE.md) for parity and worker details.

`fixtures/python_golden.json` is the permanent cross-language oracle.
`fixtures/synthetic_calibration.json` records model priors and conspicuously
states that its scenarios are not observations.

## Python reference CLI

```sh
roast-reference \
  --preset roast --weight-kg 1.8 --spacing-mm 6 \
  --oven-c 180 --initial-c 5 --target-c 57 \
  --rest-minutes 30 --output prediction.json
```

Use a coarse 6–8 mm grid for quick checks. A 3–4 mm browser grid is more detailed
but costs roughly with the voxel count and time-step count; the plan’s 1.5 mm
production study can be expensive on CPU. The explicit stable step is selected
automatically.

## Architecture

```text
src/roast_solver/         NumPy properties, SDF contract, solver, analytics, CLI
web-core/                 Rust native + wasm-bindgen port and golden tests
web/src/solver.worker.ts  Progressive/cancellable worker owner of WASM
web/src/main.ts           Static M6 UI and Canvas visualizations
fixtures/                 Synthetic calibration metadata and Python oracle
docs/                     Physics/validation and web-core details
scripts/                  Oracle and WASM regeneration
flake.nix                 Dev shell, Python/core/web packages and checks
```

Geometry is deliberately source-agnostic downstream: presets provide occupancy,
signed distance, normals, surface area/wetted fraction, and pan mask. A future
geometry source could satisfy the same contract without changing the solver.

## Static hosting

Build with `nix build .#web` (output in `result/`) or `cd web && npm run build`
(output in `web/dist/`), then upload that directory unchanged to any static host:
GitHub Pages, GitLab Pages, Netlify, Cloudflare Pages, S3, nginx, or Caddy.

Assets use relative URLs, so a domain root or repository subpath works. Ensure
the host serves `.wasm` as `application/wasm`; no SPA rewrite is required because
both `index.html` and `model-notes.html` are real files. Cross-origin isolation is
not required (the implementation does not use shared memory/threads).

Example local/production-equivalent server:

```sh
python -m http.server 8000 --directory web/dist
```

Do not open `index.html` directly with `file://`: browsers normally block module
workers/WASM there. Use any HTTP static server.

## Limits and interpretation

- Homogeneous lean material only; bone/fat fields are out of scope.
- Oven coefficients, emissivity, and moisture reservoir are engineering priors.
- “Covered” suppresses evaporation; the bottom patch is insulated, not a heated
  metal-pan model.
- P70 defaults to reference 70 °C and z=7 °C. It is an advanced equivalent-time
  quantity, not a safety pass/fail result.
- Preset shape and weight are not a scan of a particular food.
- Real predictive calibration needs traceable probe logs and controlled oven
  metadata. Nothing in this build substitutes synthetic fixtures for such data.

## License

MIT; see [`LICENSE`](LICENSE).
