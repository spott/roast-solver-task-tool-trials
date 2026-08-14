// Progressive CPU/WASM runner. Each chunk yields to the worker event loop so
// cancel messages are observed and the main UI thread is never occupied.
import init, { Simulation } from './wasm/roast_solver_web_core.js';

let generation = 0;
const wasmReady = init();
const yieldWorker = () => new Promise(resolve => setTimeout(resolve, 0));

function snapshot(sim, mode) {
  return { ...JSON.parse(sim.summary_json()), mode };
}
function sendSlice(sim, summary) {
  const slice = sim.center_slice();
  self.postMessage({ type: 'progress', summary, resolution: sim.resolution(), slice }, [slice.buffer]);
}

async function execute(config, token) {
  await wasmReady;
  if (token !== generation) return;
  const sim = new Simulation(
    config.preset, config.massKg, config.resolution, config.initialC,
    config.ovenC, config.hConv, config.emissivity, config.covered,
  );
  sim.set_rest_conditions(config.ambientC, config.restH, config.foilTent);
  const chunkSeconds = Math.max(5, config.chunkSeconds || 30);
  const maxRoastSeconds = Math.max(chunkSeconds, config.maxRoastMinutes * 60);
  const curve = [];
  let roastElapsed = 0;
  let summary = snapshot(sim, 'roast');
  curve.push(summary);
  sendSlice(sim, summary);

  while (summary.coldest_c < config.targetC && roastElapsed < maxRoastSeconds) {
    if (token !== generation) return;
    const duration = Math.min(chunkSeconds, maxRoastSeconds - roastElapsed);
    summary = JSON.parse(sim.run_chunk(duration, false));
    summary.mode = 'roast';
    roastElapsed += duration;
    curve.push(summary);
    sendSlice(sim, summary);
    await yieldWorker();
  }
  const pull = summary;
  const hitTarget = pull.coldest_c >= config.targetC;
  let peak = pull;
  const restEnd = simTime(pull) + Math.max(0, config.restMinutes * 60);
  while (simTime(summary) < restEnd - 1e-8) {
    if (token !== generation) return;
    summary = JSON.parse(sim.run_chunk(Math.min(chunkSeconds, restEnd - simTime(summary)), true));
    summary.mode = 'rest';
    curve.push(summary);
    if (summary.coldest_c > peak.coldest_c) peak = summary;
    sendSlice(sim, summary);
    await yieldWorker();
  }
  const slice = sim.center_slice();
  self.postMessage({
    type: 'complete', resolution: sim.resolution(), slice, curve,
    result: {
      pull, peak, hitTarget,
      carryover_c: peak.coldest_c - pull.coldest_c,
      pasteurization_s: summary.pasteurization_s,
    },
  }, [slice.buffer]);
}
const simTime = s => s.time_s;

self.onmessage = event => {
  const { type } = event.data || {};
  if (type === 'cancel') {
    generation += 1;
    self.postMessage({ type: 'cancelled' });
    return;
  }
  if (type !== 'start') return;
  const token = ++generation;
  execute(event.data.config, token).catch(error => {
    if (token === generation) self.postMessage({ type: 'error', message: error?.message || String(error) });
  });
};

wasmReady.then(() => self.postMessage({ type: 'ready' })).catch(error => {
  self.postMessage({ type: 'error', message: `WASM initialization failed: ${error?.message || error}` });
});
