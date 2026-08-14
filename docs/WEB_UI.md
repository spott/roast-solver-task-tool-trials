# Static web application (M6)

The browser app is deliberately framework- and dependency-free. `scripts/build.mjs` compiles the SIMD-enabled Rust core and copies five static source assets plus the WASM module to `dist/`. It makes no API calls and contains no telemetry or external runtime assets.

`solver-worker.js` owns the WASM instance. It advances six explicit steps per bounded batch, yields to the worker event loop, and posts curve and slice snapshots every three batches. A monotonically increasing run id cancels stale runs. Temperature/occupancy views are copied before posting because WASM allocation can replace its memory buffer.

The UI provides all M6 inputs (preset, weight, oven, convection, start, target, covered mode), plus grid quality, maximum duration, rest, and foil controls. It draws instantaneous-coldest and fixed-center curves, optionally retains the previous run as a what-if overlay, and reports pull time, pull-temperature cold spot, carryover, peak/time, and conservative pasteurization output. The latter is collapsed behind an explicit warning.

The 3D output is a scrubbable stack of axial temperature slices with the pull-target contour and doneness color bands. It is a view of the actual final 3D field, not a decorative interpolation or photo reconstruction.
