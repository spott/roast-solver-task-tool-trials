import { readFile } from 'node:fs/promises';
import init, { RoastSimulation } from '../web/src/wasm/roast_solver_core.js';

const bytes = await readFile(new URL('../web/src/wasm/roast_solver_core_bg.wasm', import.meta.url));
await init({ module_or_path: bytes });
const simulation = new RoastSimulation(JSON.stringify({
  preset: 'roast', mass_kg: 0.3, spacing_m: 0.012,
  initial_c: 5, oven_c: 180, target_c: 8,
  convection: false, covered: false,
  max_roast_s: 1800, rest_s: 120, sample_interval_s: 60,
  moisture_kg_m2: 0.24
}));
let snapshot;
for (let chunk = 0; chunk < 100; chunk++) {
  snapshot = JSON.parse(simulation.advance(8));
  if (snapshot.done) break;
}
simulation.free();
if (!snapshot?.done || snapshot.samples.length < 3 ||
    !Number.isFinite(snapshot.energy_relative_error)) {
  throw new Error('WASM progressive smoke test did not complete cleanly');
}
console.log(JSON.stringify({
  phase: snapshot.phase, samples: snapshot.samples.length,
  pull_s: snapshot.pull_time_s, carryover_c: snapshot.carryover_c,
  energy_error: snapshot.energy_relative_error
}));
