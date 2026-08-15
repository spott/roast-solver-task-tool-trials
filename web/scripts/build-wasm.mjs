import { cp, mkdir } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const web = resolve(here, "..");
const root = resolve(web, "..");
const output = resolve(web, "dist", "roast_core.wasm");
mkdir(resolve(web, "dist"), { recursive: true });
const rustflags = `${process.env.RUSTFLAGS || ""} -C target-feature=+simd128`.trim();
const result = spawnSync("cargo", ["build", "--manifest-path", resolve(root, "rust-core/Cargo.toml"), "--release", "--target", "wasm32-unknown-unknown"], { stdio: "inherit", env: { ...process.env, RUSTFLAGS: rustflags } });
if (result.status !== 0) {
  throw new Error("WASM build failed. Enter `nix develop` (or install Rust with the wasm32-unknown-unknown target) and retry.");
}
await cp(resolve(root, "rust-core/target/wasm32-unknown-unknown/release/roast_core.wasm"), output);
console.log(`Wrote ${output}`);
