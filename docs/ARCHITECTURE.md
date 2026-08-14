# Architecture through M6

```text
analytic preset SDF -> GridGeometry -> Python reference finite-volume solver
                              |       -> field / curves / pull / lethality
                              `-> Rust/WASM interactive core -> Web Worker
                                                           -> static canvas UI
```

* `roast_solver/`: NumPy property, SDF, solver, analytic validation, and CLI.
* `rust-core/`: dependency-free Rust library plus a small direct WASM C ABI.
  Release compilation enables `simd128`; LLVM auto-vectorizes suitable loops.
* `web/src/worker.js`: progressive batches, cancellation by worker replacement,
  WASM memory bridge, and readable JS fallback if a host omitted the optional
  `.wasm` artifact.
* `web/src/app.js`: no framework/runtime dependencies; curve and slice canvases.
* `fixtures/`: explicitly synthetic cross-port regression data.

The Python geometry interface is the future extension seam. Neither solver nor
UI accepts photographs or reconstructs meshes (M8). There is no WebGPU path
(M7). The worker sends one-minute curve samples progressively and transfers the
final Float32 field only once, avoiding main-thread stalls and copies.

## Deliberate first-version compromises

The reference uses temperature-dependent properties and complete composed SDFs.
The browser core uses constant representative properties and superellipsoid
surrogates at 34–40 cells to keep a broad range of phones responsive. Equations,
units, staging, and update order remain aligned; the synthetic interior golden
locks the most error-prone indexing. This distinction is explicit rather than
claiming bit-for-bit parity between unlike resolutions/property modes.

The visualization is a scrubbable orthogonal temperature/doneness slice. A true
marching-cubes isosurface is not required to inspect the three-dimensional field
and would materially increase the dependency/download budget for M6.
