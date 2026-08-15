let cancelled = false;
let activeCore = null;

async function loadCore() {
  const url = new URL("./roast_core.wasm", self.location.href);
  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    let source;
    if (WebAssembly.instantiateStreaming) {
      try { source = await WebAssembly.instantiateStreaming(response.clone(), {}); }
      catch { source = await WebAssembly.instantiate(await response.arrayBuffer(), {}); }
    } else {
      source = await WebAssembly.instantiate(await response.arrayBuffer(), {});
    }
    return source.instance.exports;
  } catch (error) {
    throw new Error(`Could not load the Rust/WASM solver (${error.message}). Build with \`npm run build\`, then serve the dist directory over HTTP.`);
  }
}

function readSlice(core, sliceIndex) {
  const n = core.solver_grid_size();
  const pointer = core.solver_field_ptr();
  const length = core.solver_field_len();
  const field = new Float32Array(core.memory.buffer, pointer, length);
  const output = new Float32Array(n * n);
  const z = Math.max(0, Math.min(n - 1, sliceIndex));
  for (let x = 0; x < n; x += 1) {
    for (let y = 0; y < n; y += 1) output[x * n + y] = field[(x * n + y) * n + z];
  }
  return output;
}

self.onmessage = async ({ data }) => {
  if (data.type === "cancel") { cancelled = true; return; }
  if (data.type === "slice" && activeCore) {
    const slice = readSlice(activeCore, data.index);
    self.postMessage({ type: "slice", slice, gridSize: activeCore.solver_grid_size(), index: data.index }, [slice.buffer]);
    return;
  }
  if (data.type !== "start") return;
  cancelled = false;
  try {
    const core = await loadCore();
    activeCore = core;
    const c = data.config;
    const presets = { roast: 0, bird: 1, slab: 2, ham: 3 };
    core.solver_new(
      presets[c.preset], c.massKg, c.ovenC, c.initialC, c.targetC,
      c.convection ? 1 : 0, c.covered ? 1 : 0, c.gridSize,
      c.maxCookMinutes * 60, c.restMinutes * 60,
    );
    const n = core.solver_grid_size();
    self.postMessage({ type: "ready", gridSize: n });
    let phase = 0;
    let iteration = 0;
    let previousPhase = 0;
    while (phase !== 2 && !cancelled) {
      phase = core.solver_step(80);
      const point = {
        time: core.solver_time(),
        coldest: core.solver_coldest(),
        probe: core.solver_probe(),
        hottest: core.solver_hottest(),
        pasteurization: core.solver_pasteurization(),
        phase,
        moisture: core.solver_moisture_fraction(),
      };
      const message = { type: "progress", point };
      if (iteration % 4 === 0 || phase !== previousPhase || phase === 2) {
        message.slice = readSlice(core, Math.floor(n / 2));
        message.gridSize = n;
        self.postMessage(message, [message.slice.buffer]);
      } else {
        self.postMessage(message);
      }
      previousPhase = phase;
      iteration += 1;
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
    if (!cancelled) {
      const slice = readSlice(core, Math.floor(n / 2));
      self.postMessage({
        type: "complete",
        slice,
        gridSize: n,
        metrics: {
          pullTime: core.solver_pull_time(),
          pullProbe: core.solver_pull_probe(),
          peak: core.solver_peak(),
          peakAfterPull: core.solver_peak_after_pull(),
          pasteurization: core.solver_pasteurization(),
          evaporatedKg: core.solver_evaporated_kg(),
        },
      }, [slice.buffer]);
    }
  } catch (error) {
    self.postMessage({ type: "error", message: error.message || String(error) });
  }
};
