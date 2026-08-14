import init, { WasmSolver } from '../pkg/roast_core.js';

await init();
let stopped = false;
self.onmessage = async ({data}) => {
  if (data.type === 'cancel') { stopped = true; return; }
  if (data.type !== 'run') return;
  stopped = false;
  try {
    const p=data.params;
    const solver=new WasmSolver(p.preset,+p.mass,+p.oven,+p.initial,+p.target,
      p.convection,p.covered,+p.rest,+p.resolution);
    let done=false, ticks=0;
    while (!done && !stopped) {
      done=solver.step_chunk(24); ticks++;
      if (ticks%3===0 || done) {
        self.postMessage({type:'progress',progress:solver.progress(),phase:solver.phase(),
          times:solver.times(),cold:solver.coldest(),probe:solver.probe(),dose:solver.pasteurization()});
        await new Promise(r=>setTimeout(r,0));
      }
    }
    if (!stopped) {
      const slice=solver.slice();
      self.postMessage({type:'done',pull:solver.pull_time(),dx:solver.dx_m(),n:solver.resolution(),
        times:solver.times(),cold:solver.coldest(),probe:solver.probe(),dose:solver.pasteurization(),slice},[slice.buffer]);
    }
    solver.free();
  } catch(error) { self.postMessage({type:'error',message:error?.stack||String(error)}); }
};
