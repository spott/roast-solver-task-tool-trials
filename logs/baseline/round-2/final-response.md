Implemented Roast Solver through M6 as a complete local web application.

### Included

- NumPy reference solver with temperature-dependent properties
- Parametric roast, bird/cavity, slab, ham, and sphere SDFs
- Conservative 3D finite-volume solver and embedded Robin boundaries
- Radiation, per-cell evaporation/depletion, pan insulation, rest/carryover
- Energy accounting and analytic Robin-sphere validation
- Explicitly synthetic calibration and cross-language fixtures
- Dependency-free Rust/WASM SIMD core with regression tests
- Progressive Web Worker execution and JavaScript fallback
- Static responsive UI with inputs, curves, doneness slices, pull/carryover, and pasteurization output
- Nix flake, CLI, documentation, build and hosting instructions
- M7 WebGPU and M8 photo reconstruction intentionally excluded

### Verification completed

- Python: **13 tests passed**
- Rust: **2 tests passed**, including NumPy golden regression
- JavaScript syntax checks passed
- Production Rust/WASM static build passed
- `nix flake check` passed
- `nix build` passed

See `README.md`, `docs/PHYSICS.md`, `docs/VALIDATION.md`, and `docs/ARCHITECTURE.md`.