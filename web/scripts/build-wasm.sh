#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
out="$root/web/src/generated"
manifest="$root/rust-core/Cargo.toml"
mkdir -p "$out"
cargo build --manifest-path "$manifest" --target wasm32-unknown-unknown --features wasm --release
wasm-bindgen \
  "$root/rust-core/target/wasm32-unknown-unknown/release/roast_solver_core.wasm" \
  --target web \
  --out-dir "$out" \
  --out-name roast_solver_core
printf 'WASM bindings written to %s\n' "$out"
