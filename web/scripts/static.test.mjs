import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const root = new URL("../src/", import.meta.url);
test("UI exposes milestone M6 outputs", async () => {
  const html = await readFile(new URL("index.html", root), "utf8");
  for (const id of ["curve", "slice", "pull-time", "carryover", "pasteurization", "slice-index"]) {
    assert.match(html, new RegExp(`id=["']${id}["']`));
  }
  assert.match(html, /uncalibrated/i);
});

test("worker loads and progressively steps the WASM core", async () => {
  const worker = await readFile(new URL("worker.js", root), "utf8");
  assert.match(worker, /WebAssembly\.instantiateStreaming/);
  assert.match(worker, /solver_step/);
  assert.match(worker, /type: "progress"/);
});
