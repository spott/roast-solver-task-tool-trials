/// <reference lib="webworker" />
import init, { WasmSimulation } from './generated/roast_solver_core.js';
import type { SolverChunk, WorkerRequest, WorkerResponse } from './types';

const scope: DedicatedWorkerGlobalScope = self as unknown as DedicatedWorkerGlobalScope;
let activeRun = 0;
let initialized: Promise<unknown> | undefined;

function post(message: WorkerResponse): void {
  scope.postMessage(message);
}

async function ensureInitialized(): Promise<void> {
  initialized ??= init();
  await initialized;
}

function explain(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

async function run(runId: number, input: unknown): Promise<void> {
  try {
    await ensureInitialized();
    if (runId !== activeRun) return;
    const simulation = new WasmSimulation(JSON.stringify(input));
    const advance = (): void => {
      if (runId !== activeRun) {
        simulation.free();
        return;
      }
      try {
        // A bounded chunk keeps cancel and progress messages responsive. The core
        // chooses a stability-limited dt, so this is a work budget, not physics.
        const chunk = JSON.parse(simulation.run_chunk(80)) as SolverChunk;
        post({ type: 'chunk', runId, chunk });
        if (chunk.done) simulation.free();
        else setTimeout(advance, 0);
      } catch (error) {
        simulation.free();
        post({ type: 'error', runId, message: explain(error) });
      }
    };
    advance();
  } catch (error) {
    post({ type: 'error', runId, message: explain(error) });
  }
}

scope.onmessage = (event: MessageEvent<WorkerRequest>): void => {
  const message = event.data;
  if (message.type === 'cancel') {
    if (message.runId === activeRun) activeRun += 1;
    return;
  }
  activeRun = message.runId;
  void run(message.runId, message.input);
};

void ensureInitialized().then(() => post({ type: 'ready' })).catch(() => undefined);
