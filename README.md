# Roast Solver — locally hostable M6

A complete first web version of a three-dimensional roast heat-transfer model:
NumPy reference physics, SDF presets, conservative embedded Robin boundary,
radiation and per-cell staged evaporation, rest/carryover, Rust/WASM worker core,
and a dependency-free static UI.

> **Engineering estimate, not a food-safety guarantee.** This repository has no
> real probe logs and makes no empirical-calibration claim. Verify food with a
> calibrated thermometer. Fixtures are clearly labeled synthetic.

![scope](https://img.shields.io/badge/scope-M1--M6-b64c2b)

## Quick start (Nix)

```sh
nix develop
pytest
cargo test --manifest-path rust-core/Cargo.toml
npm run build                 # dist/; attempts the Rust SIMD WASM build
npm run preview               # http://localhost:4173
```

If the host Rust installation lacks `wasm32-unknown-unknown`, `npm run build`
still produces a functional static site with the matching worker JS fallback.
Install that standard-library target (for rustup: `rustup target add
wasm32-unknown-unknown`) and run `npm run build:wasm` before rebuilding to ship
the preferred Rust core. To require WASM in CI use `REQUIRE_WASM=1 npm run
build`.

Without Nix, use Python 3.10+, NumPy, pytest, stable Rust with the wasm target,
and Node 20+:

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e '.[test]'
pytest
cargo test --manifest-path rust-core/Cargo.toml
npm test && npm run build && npm run preview
```

Run a reference simulation or validation report:

```sh
python -m roast_solver.cli --preset roast --mass 1.5 --oven 180 --target 57 --fan
python -m roast_solver.cli --validate --resolution 72
```

## Static hosting

`dist/` contains relative URLs and needs no server logic. Upload its **contents**
to any static host (GitHub Pages, Netlify, S3, nginx, Caddy). WASM must be served
with `Content-Type: application/wasm`; the included preview server does so. A
minimal local alternative is `python -m http.server -d dist 8080`.

The app runs entirely client-side. It sends no inputs or results over the
network. The Google font import is cosmetic; remove the first CSS line for a
strictly offline deployment (system fallbacks are already specified).

## What is implemented

* **M1:** temperature-dependent Choi–Okos composition properties and scaled SDF
  roast, composed cavity bird, rounded slab, ham, and validation sphere.
* **M2:** Float32 3-D explicit seven-point solver plus Dirichlet cube checks.
* **M3:** projected-area embedded Robin cells, distinct insulated pan patch,
  analytic convective-sphere helpers, and exact discrete energy ledger.
* **M4:** lagged nonlinear radiation, Lewis staged evaporation with independent
  cell reservoirs/dry transition, covered mode, rest/carryover, and per-cell
  pasteurization integral.
* **M5:** dependency-free Rust/WASM port, SIMD release flag, NumPy-generated
  golden kernel fixture, worker progression, and JS fallback.
* **M6:** responsive inputs, progressive cold-point curve, scrubbable final 3-D
  slice, pull/peak/carryover, and conservative pasteurization readout.

M7 WebGPU and M8 photo reconstruction are intentionally absent.

## Review map

* [`docs/PHYSICS.md`](docs/PHYSICS.md) — equations, units, boundary staging
* [`docs/VALIDATION.md`](docs/VALIDATION.md) — checks and synthetic-fixture policy
* [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — ports, worker, compromises
* [`PROJECT_PLAN.md`](PROJECT_PLAN.md) — authoritative product plan

For a clean review run `pytest`, `cargo test --manifest-path rust-core/Cargo.toml`,
`npm test`, and `npm run build`. Generated `dist/`, `target/`, caches, and probe
outputs are ignored; no generated artifact needs to be committed.
