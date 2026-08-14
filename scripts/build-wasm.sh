#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root/rust-core"
RUSTFLAGS="${RUSTFLAGS:-} -C target-feature=+simd128" cargo build --release --target wasm32-unknown-unknown
mkdir -p "$root/web/public/wasm"
cp target/wasm32-unknown-unknown/release/roast_solver_core.wasm "$root/web/public/wasm/roast_solver_core.wasm"
echo "WASM SIMD core: web/public/wasm/roast_solver_core.wasm"
