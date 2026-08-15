Implemented Roast Solver through M6 as a complete locally hostable web app.

Highlights:
- NumPy reference properties, SDF presets, 3-D solver, Robin boundary, radiation, evaporation, rest/carryover, and pasteurization.
- Analytic sphere, convergence, energy-accounting, evaporation-stage, and cross-language golden tests.
- Rust/WASM solver with progressive Web Worker execution.
- Responsive static UI with controls, curves, doneness slice, pull/carryover, and pasteurization output.
- Clearly labeled synthetic calibration fixtures and documentation.
- Reproducible Nix flake, npm production build, preview, and static-hosting instructions.

Validation completed:
- Python: **8 tests passed**
- Rust: **3 tests passed**
- `npm test`: production WASM/Vite build and smoke test passed
- `nix build path:.# --no-link`: passed

M7 WebGPU and M8 photo reconstruction were not implemented. No empirical calibration claims are made.