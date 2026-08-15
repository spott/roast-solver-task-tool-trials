Implemented Roast Solver M1–M6 as a locally hostable web application.

### Included

- NumPy reference physics, Choi–Okos properties, SDF presets, 3D explicit solver
- Embedded Robin boundaries, pan insulation, radiation, staged per-cell evaporation
- Rest/carryover, pasteurization integral, energy accounting
- Analytic sphere/slab validation and convergence tests
- Clearly labeled synthetic calibration fixtures
- Rust/WASM SIMD core with Python golden regression matrix
- Progressive Web Worker execution
- Static responsive UI with curves, doneness slices, pull/carryover and safety outputs
- Nix flake, production build, preview and static-hosting documentation

### Verification

- Python: **13 tests passed**
- Rust: **3 tests passed**, including Python golden parity
- Web: **2 tests passed**
- WASM production build and runtime smoke test passed
- `nix build path:.#default` passed
- `nix flake check path:.` passed

Key documentation is in:

- `README.md`
- `docs/PHYSICS.md`
- `docs/VALIDATION.md`
- `docs/CALIBRATION.md`

M7 WebGPU and M8 photo reconstruction were not implemented. No empirical calibration claims are made.