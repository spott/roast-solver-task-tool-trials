let wasm, activeRun = 0, lastConfig = null, lastSlice = 0.5;

async function loadCore() {
  if (wasm) return wasm;
  const response = await fetch("./roast_core.wasm");
  if (!response.ok) throw new Error(`WASM core failed to load (${response.status})`);
  const bytes = await response.arrayBuffer();
  wasm = (await WebAssembly.instantiate(bytes, {})).instance.exports;
  return wasm;
}
function history(core) {
  const count = core.roast_history_len();
  return new Float32Array(core.memory.buffer, core.roast_history_ptr(), count).slice();
}
function slice(core, fraction = 0.5) {
  const n = core.roast_grid_n(), z = Math.max(0, Math.min(n - 1, Math.round(fraction * (n - 1))));
  const count = n * n * n;
  const t = new Float32Array(core.memory.buffer, core.roast_temperature_ptr(), count);
  const occupied = new Uint8Array(core.memory.buffer, core.roast_occupancy_ptr(), count);
  const values = new Float32Array(n * n), mask = new Uint8Array(n * n);
  const offset = z * n * n;
  for (let i = 0; i < n * n; i++) { values[i] = t[offset + i]; mask[i] = occupied[offset + i]; }
  return { n, z, values, mask };
}
function result(core) {
  return { pullTime: core.roast_result(0), pullTemp: core.roast_result(1), peakTemp: core.roast_result(2),
    peakTime: core.roast_result(3), carryover: core.roast_result(4), pasteurization: core.roast_result(5),
    elapsed: core.roast_result(6), dt: core.roast_result(7) };
}
async function run(message) {
  const runId = message.runId; activeRun = runId; lastConfig = message.config; lastSlice = 0.5;
  const core = await loadCore(), c = message.config;
  core.roast_start(c.preset, c.resolution, c.mass, c.oven, c.initial, c.target, c.maxCook, c.rest,
    c.convection ? 1 : 0, c.covered ? 1 : 0, c.foil ? 1 : 0);
  let batch = 0, done = 0;
  while (!done && activeRun === runId) {
    done = core.roast_advance(6); batch++;
    if (batch % 3 === 0 || done) {
      const curve = history(core), image = slice(core, lastSlice);
      postMessage({ type: done ? "complete" : "progress", runId, progress: core.roast_progress(),
        curve, image, result: result(core) }, [curve.buffer, image.values.buffer, image.mask.buffer]);
    }
    if (!done) await new Promise(resolve => setTimeout(resolve, 0));
  }
}
onmessage = async ({ data }) => {
  try {
    if (data.type === "start") await run(data);
    else if (data.type === "cancel") { activeRun++; }
    else if (data.type === "slice" && wasm && data.runId === activeRun) {
      lastSlice = data.fraction; const image = slice(wasm, lastSlice);
      postMessage({ type: "slice", runId: activeRun, image }, [image.values.buffer, image.mask.buffer]);
    }
  } catch (error) { postMessage({ type: "error", runId: data.runId, message: error?.message || String(error) }); }
};
