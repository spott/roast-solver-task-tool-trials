Implemented the Roast Solver through M6 as a complete, locally hostable web application.

### Delivered

- NumPy reference implementation:
  - Temperature-dependent food properties
  - Roast, bird/cavity, slab, sphere/ham SDF geometry
  - Conservative 3D explicit solver
  - Embedded-boundary Robin flux and energy accounting
  - Radiation, staged per-cell evaporation, dry-crust transition
  - Pan-contact behavior, rest/carryover, pasteurization output
- Validation suite:
  - Dirichlet convergence
  - Robin sphere and high-Biot slab anchors
  - Resolution convergence
  - Energy closure
  - Geometry and evaporation/rest regressions
- Rust/WASM core:
  - Matching geometry and solver behavior
  - Progressive chunk API
  - Python-generated deterministic golden regression fixture
- Static TypeScript/Vite application:
  - Full cooking, geometry, rest, and numerical controls
  - Module worker with progressive updates and cancellation
  - Temperature curves
  - Temperature, doneness, and wetness slice visualization
  - Pull, carryover, pasteurization, and energy outputs
- Reproducible tooling:
  - `flake.nix` and locked dependencies
  - `Makefile`
  - Production static package and local preview app
  - Comprehensive setup, physics, limitations, testing, and hosting documentation in `README.md`

Fixtures are clearly labeled synthetic and non-empirical. M7 WebGPU and M8 photo reconstruction were not implemented.

### Verification

All checks pass:

- 11 Python reference tests
- 4 Rust tests plus doc tests
- Python/Rust golden parity
- Rust formatting
- Release WASM build
- Strict TypeScript checking
- Vite production build
- Direct progressive WASM runtime smoke test
- Nix sandbox checks and static package build
- Packaged preview HTTP smoke test
- `git diff --check`

Primary commands:

```bash
nix develop -c make check
nix build
nix run .#preview
```

No commits were created, as requested.