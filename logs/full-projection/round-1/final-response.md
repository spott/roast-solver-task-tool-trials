Implemented Roast Solver milestones **M1–M6** as a complete locally hostable web application.

### Delivered

- NumPy reference implementation:
  - Temperature-dependent food properties
  - Roast, bird, slab, and ham SDF geometries
  - Conservative 3D explicit heat solver
  - Embedded Robin boundaries, radiation, pan shielding
  - Per-surface-cell evaporation and crust transition
  - Rest/carryover and pasteurization calculations
  - Discrete energy accounting
- Analytic, convergence, energy, and regression tests
- Clearly labeled synthetic calibration fixture—no empirical calibration claims
- Matching Rust/WASM implementation with Python-generated golden parity tests
- Progressive, cancellable Web Worker execution
- Responsive static UI featuring:
  - Cooking and geometry inputs
  - Temperature curves
  - Thermal/doneness slice visualization
  - Pull, peak, and carryover outputs
  - Advanced pasteurization output with safety caveats
- Reproducible Nix flake
- Production build, preview server, static-hosting documentation, and MIT license
- M7 WebGPU and M8 photo reconstruction remain intentionally excluded

### Verification

All final checks passed:

- 10 Python tests
- 4 Rust integration/golden tests plus doc tests
- Rust formatting checks
- JavaScript syntax and static asset checks
- Release WASM build
- Direct WASM execution smoke test
- Local HTTP preview smoke test
- Sandboxed `nix flake check`
- Golden fixture regeneration was byte-identical

### Run locally

```bash
nix develop
npm test
npm run build
npm run preview -- --host 127.0.0.1 --port 8080
```

Then open `http://127.0.0.1:8080`.

The production static site is generated in `dist/`. Complete setup, deployment, physics, validation, parity, calibration, and limitation documentation is in `README.md` and `docs/`. No changes were committed.