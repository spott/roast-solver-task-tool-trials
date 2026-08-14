# Rust / WASM core (M5)

`rust_core` is a dependency-free Rust port of the reference geometry, lagged properties, conservative face stencil, embedded Robin interface, radiation, staged per-cell evaporation, pull, and rest model. It is built as both an `rlib` for native tests and a `cdylib` for `wasm32-unknown-unknown`.

The browser-facing ABI deliberately uses numeric C exports rather than `wasm-bindgen`: `roast_start(...)` initializes a run, `roast_advance(step_count)` performs a bounded batch, and pointer/length getters expose interleaved `[time, coldest, center probe]` history plus final temperature and occupancy arrays. A Web Worker can yield between batches, so the page remains responsive. The worker must copy views before the next call because WASM memory can grow.

Release builds use `-C target-feature=+simd128`; LLVM can vectorize contiguous property/update loops. No WebGPU path is present.

## Cross-language lock

`scripts/generate_core_golden.py` emits `fixtures/core_golden_v1.csv` from Python. Both pytest and `cargo test` consume it. It covers property/radiation values, the M2 seven-point stencil, and a complete synthetic cook/rest integration. The integration currently agrees exactly on pull time, within 0.01°C on carryover, and within 0.5% on the conservative coldest-point pasteurization integral. Minor field differences are expected from Rust scalar ordering/Float32 rounding.

Regenerate only when intentionally changing the Python oracle:

```sh
python scripts/generate_core_golden.py
cargo test --manifest-path rust_core/Cargo.toml
```
