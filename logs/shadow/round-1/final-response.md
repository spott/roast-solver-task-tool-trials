Implemented Roast Solver through M6 as a complete local static web app.

Highlights:
- NumPy reference physics, SDF presets, 3D solver, Robin boundaries, radiation, evaporation, rest/carryover, pasteurization.
- Analytic sphere/slab validation, energy accounting, convergence tests, synthetic fixtures.
- Rust/WASM core with Python golden parity checks.
- Progressive Web Worker execution.
- Responsive UI with inputs, curves, prior-run overlays, doneness slices, pull/carryover and pasteurization outputs.
- Locked Nix flake, production build, preview server, and static-hosting documentation.
- No M7 WebGPU or M8 photo reconstruction.
- No empirical calibration claims.

Verification:
- Python: 16 tests passed.
- Rust: 3 tests passed plus doc tests.
- UI: 3 tests passed.
- `nix flake check path:.`: passed.
- `nix build path:.`: passed.
- Production WASM runtime smoke test passed.
- Static preview and WASM MIME checks passed.

Setup and usage are documented in [`README.md`](README.md). No commits were created.