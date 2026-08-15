Implemented Roast Solver through M6 as a complete locally hostable web app.

### Delivered

- NumPy reference implementation:
  - Choi–Okos temperature-dependent properties
  - Roast, bird-with-cavity, slab, and ham SDF presets
  - Conservative 3D explicit solver
  - Embedded Robin boundary with corrected curved-surface area
  - Radiation, per-cell evaporation/crust state, covered mode, and pan insulation
  - Rest/carryover and pasteurization integration
- Validation:
  - Dirichlet convergence
  - Exact sphere, slab, and cylinder anchors
  - High-h water-bath regression
  - Energy accounting
  - Sphere center error ≈0.12% at 14 cells/radius
- Rust/WASM core:
  - Progressive chunked execution
  - Web Worker cancellation and progress updates
  - Python golden regression checks
  - SIMD-enabled WASM build
- Static Vite UI:
  - Required inputs and toggles
  - Temperature curves with previous-run overlay
  - Doneness/temperature slice
  - Pull, carryover, peak, energy, and P70 outputs
  - Responsive layout and calibration/safety disclosures
- Reproducibility:
  - Locked Nix flake
  - Source-built WASM and static web packages
  - Setup, testing, preview, and static-hosting documentation

### Verification

- Python: **12 tests passed**
- Rust: **3 integration tests passed**
- Rust formatting and strict Clippy: passed
- WASM progressive smoke test: passed
- TypeScript typecheck: passed
- Production Vite build: passed
- `nix flake check`: **all 5 checks passed**
- Static HTTP preview and `application/wasm` MIME check: passed

No M7 WebGPU or M8 photo reconstruction was added. Synthetic fixtures are explicitly identified as non-empirical. No changes were committed.