# Roast Solver

Roast Solver is a locally hostable, client-side web application that predicts 3-D temperature evolution in roasts and poultry. It combines a NumPy reference implementation with a regression-locked Rust/WASM core and runs progressive simulations in a Web Worker.

This repository implements **milestones M1–M6** from [`PROJECT_PLAN.md`](PROJECT_PLAN.md). It intentionally does **not** implement M7 WebGPU or M8 photo reconstruction.

> **Model status:** this is a mechanistic engineering estimate, not food-safety advice. No real probe logs were supplied or fitted. Both checked-in fixtures are explicitly synthetic numerical/regression data and do not establish empirical accuracy.

## What is included

- Temperature-dependent lean-meat properties using published Choi–Okos component correlations and mixture rules.
- Source-agnostic signed-distance-field (SDF) voxel geometry.
- Roast superellipsoid, composed whole bird with cavity, rounded slab, and spherical ham presets.
- Conservative 3-D explicit conduction with embedded-boundary Robin surface flux.
- Convection, nonlinear radiation, per-surface-cell evaporation reservoirs, dry-crust transition, and an insulated pan patch.
- Pull-target detection, ambient rest/carryover, optional foil tent, and coldest-point pasteurization integration.
- Analytic, energy-budget, geometry, convergence, and Python↔Rust golden regression tests.
- Rust CPU core exposed to the browser through WASM.
- Progressive execution and cancellation in a module worker.
- A responsive static UI with controls, curves, temperature/doneness/wetness slices, pull/carryover, pasteurization, and energy closure.
- Reproducible Nix development, checks, and static production packaging.

## Quick start with Nix

[Nix with flakes enabled](https://nixos.org/) is the only prerequisite. Tool versions are pinned by [`flake.lock`](flake.lock).

```sh
nix develop
make setup          # npm ci
make check          # Python + Rust + TypeScript tests, then production build
make dev            # http://localhost:5173
```

For a reproducible production build and local static preview:

```sh
nix build
nix run .#preview   # http://127.0.0.1:4173
```

The build result is a directory of static files. `nix flake check` independently builds and tests the Python reference, native Rust core, WASM bindings, and frontend.

## Setup without Nix

Install:

- Python 3.11+ and NumPy 1.26+
- Node.js 20+ and npm
- a Rust 2021 toolchain with the `wasm32-unknown-unknown` target
- `wasm-bindgen-cli` **0.2.121**, matching [`rust-core/Cargo.toml`](rust-core/Cargo.toml)
- a C linker and `lld`

One typical setup is:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
rustup target add wasm32-unknown-unknown
cargo install wasm-bindgen-cli --version 0.2.121 --locked
npm ci
make check
```

Useful commands:

| Command | Purpose |
|---|---|
| `make test-python` | NumPy reference and validation suite |
| `make test-rust` | Rust formatting, unit, energy, and golden tests |
| `make test-web` | Build WASM and strictly type-check worker/UI code |
| `make wasm` | Generate browser bindings under `web/src/generated/` |
| `make build` | Generate WASM, type-check, and build `dist/` |
| `make preview` | Preview an existing `dist/` build |
| `make golden` | Regenerate the deterministic Python↔Rust oracle |
| `make clean` | Remove generated WASM, web, and Rust build output |

## Static hosting

`npm run build` produces `dist/`. Upload that directory unchanged to any static host (GitHub Pages, Netlify, Cloudflare Pages, S3, nginx, or similar). There is no server component, database, telemetry, remote font, or runtime network request.

Vite's base is `./`, so the app works at a domain root or a nested path. The host must:

1. serve `.wasm` as `application/wasm` (most modern static hosts do), and
2. preserve the hashed files under `dist/assets/`.

For nginx, a minimal location is:

```nginx
location /roast-solver/ {
    alias /srv/roast-solver/dist/;
    try_files $uri $uri/ /roast-solver/index.html;
}
types { application/wasm wasm; }
```

No cross-origin isolation is required by this CPU/WASM version.

## Architecture

```text
analytic preset SDF
      │
      ▼
occupancy + φ + normals + embedded area + pan mask
      │
      ├──────── NumPy reference / validation oracle
      │
      ▼
Rust finite-volume core → wasm-bindgen → module Web Worker
                                          │ progressive chunks
                                          ▼
                            curves + slices + summary outputs
```

The SDF grid is the geometry contract. Solver code consumes arrays in `(z, y, x)` order and does not depend on how the SDF was created. This leaves a clean future geometry boundary without implementing the out-of-scope photo pipeline.

### Repository map

- [`roast_solver/properties.py`](roast_solver/properties.py) — component correlations and lean-meat mixture properties.
- [`roast_solver/geometry.py`](roast_solver/geometry.py) — analytic SDFs, voxelization, normals, area, and pan mask.
- [`roast_solver/solver.py`](roast_solver/solver.py) — NumPy reference cook/rest solver and accounting.
- [`roast_solver/validation.py`](roast_solver/validation.py) — transparent analytic/regression anchors.
- [`rust-core/src/lib.rs`](rust-core/src/lib.rs) — native and WASM implementation of the same numerical contract.
- [`tools/generate_golden.py`](tools/generate_golden.py) — deterministic Python oracle generator.
- [`web/src/solver.worker.ts`](web/src/solver.worker.ts) — progressive worker and cancellation boundary.
- [`web/src/main.ts`](web/src/main.ts) — static UI, charts, slices, and outputs.
- [`fixtures/`](fixtures/) — clearly labeled synthetic fixtures.
- [`tests/test_reference.py`](tests/test_reference.py) — NumPy physics and validation tests.

## Numerical and physical model

All internal dimensions and fluxes use SI units; temperatures are represented in degrees Celsius except radiation, which converts to Kelvin.

### Material properties

The baseline composition is 75% water, 20% protein, 3% fat, 0.5% carbohydrate, and 1.5% ash by mass. Component density, heat capacity, and conductivity use Choi–Okos temperature correlations over a clipped −20 to 150 °C range. Mixture density uses reciprocal volume additivity, heat capacity is mass weighted, and conductivity uses a parallel volume-fraction rule. Properties are evaluated at the previous temperature (one-step Picard lag).

An optional broad heat-capacity bump around 60 °C exists as an explicitly synthetic model knob. It is disabled in the web app because there is no calibration evidence for fitting it.

### Geometry and embedded boundary

The SDF is negative inside. Each preset is scaled from requested mass using a nominal material density of 1060 kg/m³. The grid includes an exterior margin, and `resolution` means cells across the longest body dimension.

Instead of counting exposed voxel faces, the implementation assigns surface area to the interior shell `−h ≤ φ ≤ 0` using

```text
A_cell = h² |∇φ|.
```

This one-sided level-set delta integral reduces orientation-dependent stair-step area inflation. Normals are `∇φ / |∇φ|`. Downward-facing shell cells near the bottom form a distinct pan-contact patch, insulated by default.

This first version retains full thermal volume `h³` for occupied cells rather than introducing tiny cut-cell volumes. That keeps the explicit update stable while applying embedded physical surface area. It is a documented finite-volume approximation, not an exact sub-cell volume reconstruction.

### Interior update and stability

For each pair of occupied neighbors, a harmonic-mean conductivity link transfers equal and opposite power. This is the conservative 7-point stencil. Forward Euler uses Float32 temperature state with wider intermediates, lagged properties, and

```text
dt = min(requested dt, 0.9 h² / (6 max α)).
```

The same surface power used in the enthalpy update is accumulated in the energy report, making discrete conservation directly testable.

### Boundary flux

Each exposed boundary cell receives

```text
q″ = h(T_air − T_s)
   + εσ(T_wall⁴ − T_s⁴)
   − h_fg ṁ.
```

Radiation is evaluated through the algebraically exact secant coefficient at the lagged surface temperature. Evaporation uses a Lewis-analogy mass-transfer coefficient, Tetens saturation vapor density, explicit ambient vapor density, and a finite water reservoir in kg/m² **per boundary cell**. The evaporation rate is capped by remaining water for the current step. Once depleted, latent cooling becomes zero and that cell enters the dry-surface stage. Covered mode disables evaporation to represent saturated enclosure air.

During rest, the oven boundary switches to room-temperature convection/radiation and evaporation is disabled. A foil tent scales convection and emissivity down. The solver continues through the requested rest to report peak coldest-point temperature, peak time, and carryover from pull.

### Outputs and interpretation

- **Cold spot:** instantaneous minimum over occupied cells; this controls pull and pasteurization.
- **Probe:** stable cell nearest the occupied-volume centroid.
- **Surface:** embedded-area-weighted shell average.
- **Pull:** first step where the coldest point reaches target, or the configured time limit with `pull_reached = false`.
- **Carryover:** peak coldest-point temperature after pull minus pull temperature.
- **Pasteurization:** `∫10^((T_cold−T_ref)/z)dt`, reported as equivalent minutes, with `z = 10 °C` in the UI.
- **Slice:** axial views of temperature, target-relative doneness, or remaining wet fraction.

Pasteurization uses the instantaneous coldest point and is deliberately conservative within this model, but it is **not** a regulatory lethality calculation or safety guarantee. Organism, food composition, measurement uncertainty, initial contamination, and model bias are not represented.

## Validation and regression strategy

Run all local checks with `make test`, or sandboxed checks with `nix flake check`.

The NumPy suite covers:

1. property ranges and temperature response;
2. all SDF presets and retention of the bird cavity;
3. sphere surface-area convergence;
4. second-order trend for a separable Dirichlet cube mode;
5. exact Robin sphere series roots from `1 − λ cot λ = Bi`;
6. an embedded constant-property Robin sphere;
7. a symmetric Robin slab series anchor (a high-boundary-transfer interior check);
8. preset resolution convergence;
9. full radiation/evaporation/rest energy closure and wet-reservoir depletion; and
10. insulated pan-patch behavior.

The routine CI grid is intentionally small and fast. The embedded-sphere test requires center-temperature and area errors below 8% at resolution 36; a release spot check at resolution 96 produced about 0.14% center-temperature error for the documented constant-property case. Full-physics tests require relative discrete energy mismatch below `3×10⁻⁵`.

Rust tests check properties, presets, energy closure, and [`fixtures/python_rust_golden.json`](fixtures/python_rust_golden.json). The golden scenario avoids cells exactly on an analytic surface (where platform `libm` rounding can change occupancy). Tolerances are `2×10⁻⁴ °C` for temperatures and `2×10⁻⁴` relative for energy, while property samples use a tighter relative tolerance.

Regenerate and review the oracle after an intentional Python numerical change:

```sh
make golden
make test-rust
```

A golden update is a model change and should not be accepted merely to silence a regression.

## Synthetic calibration fixtures

- [`fixtures/synthetic_calibration.json`](fixtures/synthetic_calibration.json) contains hand-selected demonstration observations and baseline assumptions. Its provenance is `synthetic; not measured probe data` and `empirically_calibrated` is false.
- [`fixtures/python_rust_golden.json`](fixtures/python_rust_golden.json) is deterministic output from the NumPy reference for software parity. It is not calibration data.

A future calibration process may fit convection, emissivity, and surface-water reservoir against actual leave-in probe logs by preset. That work requires provenance, train/validation separation, uncertainty reporting, and real measurements. None of it has been performed here.

## Known limitations

- Homogeneous lean-meat material only; no bones, fat layers, stuffing, phase change, shrinkage, or juices moving internally.
- Preset shape scaling is approximate at voxel resolution, especially rounded slab corners and composed-bird details.
- Oven air and wall temperatures are spatially uniform; the pan patch is insulated rather than conductively coupled to cookware.
- Surface evaporation is a staged engineering approximation, not coupled airflow/humidity transport.
- Explicit CPU execution trades speed for transparency. Browser defaults are moderate grids; high resolutions can be slow and transfer full fields between chunks.
- Pull predictions are sensitive to geometry, convection, emissivity, moisture, starting conditions, and appliance behavior. Those parameters have not been empirically fitted.
- The visualizer uses axial slices rather than a 3-D isosurface renderer.
- WebGPU (M7) and photo-to-mesh/SDF reconstruction (M8) are deliberately absent.

## License

The Rust crate declares MIT. Add an appropriate repository-level license file before public redistribution if needed.
