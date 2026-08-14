/// <reference lib="webworker" />
import init, { RoastSimulation } from './wasm/roast_solver_core.js';

type StartMessage = { type: 'start'; config: Record<string, unknown> };
type CancelMessage = { type: 'cancel' };
let generation = 0;
let wasmReady: Promise<unknown> | undefined;

self.onmessage = async (event: MessageEvent<StartMessage | CancelMessage>) => {
  if (event.data.type === 'cancel') {
    generation += 1;
    return;
  }
  const mine = ++generation;
  try {
    wasmReady ??= init();
    await wasmReady;
    if (mine !== generation) return;
    const simulation = new RoastSimulation(JSON.stringify(event.data.config));
    self.postMessage({ type: 'started', snapshot: JSON.parse(simulation.snapshot()) });
    // Short chunks yield to the worker event loop. Progress and cancellation
    // therefore remain responsive even for production-sized grids.
    while (mine === generation) {
      const snapshot = JSON.parse(simulation.advance(24));
      self.postMessage({ type: 'progress', snapshot });
      if (snapshot.done) {
        self.postMessage({ type: 'complete', snapshot });
        break;
      }
      await new Promise(resolve => setTimeout(resolve, 0));
    }
    simulation.free();
  } catch (error) {
    self.postMessage({ type: 'error', message: error instanceof Error ? error.message : String(error) });
  }
};

export {};
