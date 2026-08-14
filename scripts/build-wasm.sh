#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root/web-core"
cargo build --locked --release --target wasm32-unknown-unknown
rm -rf "$root/web/src/wasm"
mkdir -p "$root/web/src/wasm"
wasm-bindgen --target web --out-dir "$root/web/src/wasm" \
  target/wasm32-unknown-unknown/release/roast_solver_core.wasm
if command -v wasm-opt >/dev/null; then
  wasm-opt -Oz -o "$root/web/src/wasm/core.opt.wasm" "$root/web/src/wasm/roast_solver_core_bg.wasm"
  mv "$root/web/src/wasm/core.opt.wasm" "$root/web/src/wasm/roast_solver_core_bg.wasm"
fi
