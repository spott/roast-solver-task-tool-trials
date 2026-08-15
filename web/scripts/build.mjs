import { cp, mkdir, rm, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const web = resolve(here, "..");
const dist = resolve(web, "dist");
await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });
await cp(resolve(web, "src"), dist, { recursive: true });
if (process.env.ROAST_SKIP_WASM !== "1") {
  const built = spawnSync(process.execPath, [resolve(here, "build-wasm.mjs")], { stdio: "inherit" });
  if (built.status !== 0) process.exit(built.status ?? 1);
}
await writeFile(resolve(dist, "build.json"), JSON.stringify({ version: "0.1.0", builtAt: new Date().toISOString(), wasm: process.env.ROAST_SKIP_WASM !== "1" }, null, 2));
console.log(`Static production site built in ${dist}`);
