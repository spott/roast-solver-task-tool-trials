import './style.css';

type Sample = {
  time_s: number;
  phase: 'roast' | 'rest';
  coldest_c: number;
  probe_c: number;
  hottest_c: number;
  pasteurization_p70_s: number;
};
type Snapshot = {
  done: boolean;
  phase: 'roast' | 'rest' | 'done';
  progress: number;
  pull_time_s: number | null;
  carryover_c: number;
  peak_core_c: number;
  peak_time_after_pull_s: number;
  pasteurization_p70_s: number;
  samples: Sample[];
  slice_width: number;
  slice_height: number;
  slice_c: (number | null)[];
  energy_relative_error: number;
};

const app = document.querySelector<HTMLDivElement>('#app')!;
app.innerHTML = `
<header class="hero">
  <div class="brand"><span class="brand-mark">RS</span><span>Roast Solver</span></div>
  <div class="hero-copy">
    <p class="eyebrow">3D heat-transfer model · local in your browser</p>
    <h1>See the heat move<br><em>before you pull.</em></h1>
    <p class="lede">An open numerical estimate of internal temperature, surface physics, and carryover—not a mystery timer.</p>
  </div>
  <div class="model-badge"><span class="pulse"></span> M1–M6 · WASM / CPU</div>
</header>
<main>
  <section class="control-panel" aria-labelledby="inputs-title">
    <div class="section-heading"><div><span class="step">01</span><h2 id="inputs-title">Describe the cook</h2></div><p>All temperatures are °C. The model runs entirely on this device.</p></div>
    <form id="solver-form">
      <label>Shape preset<select id="preset"><option value="roast">Boneless roast</option><option value="bird">Whole bird + cavity</option><option value="slab">Rounded slab</option><option value="ham">Ham / teardrop</option></select></label>
      <label>Weight <span class="unit">kg</span><input id="weight" type="number" min="0.15" max="12" step="0.1" value="1.8" required></label>
      <label>Oven <span class="unit">°C</span><input id="oven" type="number" min="60" max="280" step="5" value="180" required></label>
      <label>Starting temp <span class="unit">°C</span><input id="initial" type="number" min="-2" max="35" step="1" value="5" required></label>
      <label>Pull target <span class="unit">°C</span><input id="target" type="number" min="35" max="95" step="1" value="57" required></label>
      <label>Grid detail<select id="spacing"><option value="0.008">Quick · 8 mm</option><option value="0.006" selected>Balanced · 6 mm</option><option value="0.004">Detailed · 4 mm</option><option value="0.003">Fine · 3 mm</option></select></label>
      <div class="toggles">
        <label class="toggle"><input id="convection" type="checkbox"><span></span><b>Fan convection</b><small>h = 20 vs 10 W/m²K</small></label>
        <label class="toggle"><input id="covered" type="checkbox"><span></span><b>Covered vessel</b><small>Saturated air; evaporation off</small></label>
      </div>
      <button class="run" type="submit"><span>Run 3D simulation</span><b>→</b></button>
      <button class="cancel" id="cancel" type="button" hidden>Cancel run</button>
    </form>
    <p class="assumption">Baseline: lean-meat properties · ε 0.90 · 0.24 kg/m² synthetic moisture prior · 30 min uncovered rest at 22 °C</p>
  </section>

  <section class="results" aria-live="polite">
    <div class="section-heading"><div><span class="step">02</span><h2>Prediction</h2></div><div class="status" id="status"><span></span>Ready</div></div>
    <div class="progress-track"><i id="progress"></i></div>
    <div class="metrics">
      <article><p>Recommended pull</p><strong id="pull">—</strong><small>elapsed oven time</small></article>
      <article><p>Peak core</p><strong id="peak">—</strong><small id="peak-time">during rest</small></article>
      <article><p>Carryover</p><strong id="carry">—</strong><small>pull-time cold point</small></article>
      <article><p>Energy check</p><strong id="energy">—</strong><small>surface vs enthalpy</small></article>
    </div>
    <div class="visual-grid">
      <article class="chart-card">
        <div class="card-head"><div><p class="eyebrow">Internal history</p><h3>Temperature curves</h3></div><div class="legend"><span class="cold">Coldest</span><span class="probe">Pull probe</span><span class="hot">Hottest</span></div></div>
        <canvas id="curve" role="img" aria-label="Predicted temperature over time"></canvas>
        <p class="compare" id="compare">A previous run appears dashed for quick what-if comparison.</p>
      </article>
      <article class="slice-card">
        <div class="card-head"><div><p class="eyebrow">Middle plane</p><h3>Doneness slice</h3></div><span id="slice-time">t = 0:00</span></div>
        <canvas id="slice" role="img" aria-label="Temperature-colored middle slice of the food"></canvas>
        <div class="bands"><span><i style="--c:#432524"></i>&lt;45 rare</span><span><i style="--c:#a84d38"></i>45–52</span><span><i style="--c:#dc8851"></i>52–60</span><span><i style="--c:#e9b675"></i>60–68</span><span><i style="--c:#d8ccb6"></i>68+ °C</span></div>
      </article>
    </div>
    <details class="advanced">
      <summary><span>Advanced food-safety model</span><b>Pasteurization equivalent ▾</b></summary>
      <div><p>Equivalent exposure at 70 °C (z = 7 °C), integrated at the instantaneous coldest cell.</p><strong id="p70">—</strong><p class="warning">Model-dependent quantity—not a safety verdict. Apply the correct organism, product, regulatory schedule, and margin.</p></div>
    </details>
  </section>

  <section class="honesty">
    <span class="step">03</span><div><h2>What this can—and cannot—say</h2><p>The solver accounts for 3D conduction, curved embedded boundaries, convection, radiation, staged surface evaporation, an insulated pan patch, and ambient rest. Its calibration fixtures are synthetic. No real probe logs were provided, so this version does <strong>not</strong> claim empirical accuracy.</p></div>
    <a href="./model-notes.html" aria-label="Read model documentation">Read the model notes <b>↗</b></a>
  </section>
</main>
<footer><span>Roast Solver v0.1 · static, local-first</span><span>No WebGPU · no photo reconstruction · no data upload</span></footer>`;

const form = document.querySelector<HTMLFormElement>('#solver-form')!;
const worker = new Worker(new URL('./solver.worker.ts', import.meta.url), { type: 'module' });
const status = document.querySelector<HTMLDivElement>('#status')!;
const progress = document.querySelector<HTMLElement>('#progress')!;
const cancel = document.querySelector<HTMLButtonElement>('#cancel')!;
const curve = document.querySelector<HTMLCanvasElement>('#curve')!;
const slice = document.querySelector<HTMLCanvasElement>('#slice')!;
let current: Snapshot | undefined;
let previous: Sample[] | undefined;
let running = false;

const input = (id: string) => document.querySelector<HTMLInputElement>(`#${id}`)!;
const select = (id: string) => document.querySelector<HTMLSelectElement>(`#${id}`)!;
const text = (id: string, value: string) => { document.querySelector<HTMLElement>(`#${id}`)!.textContent = value; };
const duration = (seconds: number) => { const minutes = Math.round(seconds / 60); return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}`; };

form.addEventListener('submit', event => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  if (current?.samples.length) previous = current.samples.map(sample => ({ ...sample }));
  running = true;
  current = undefined;
  cancel.hidden = false;
  status.className = 'status working';
  status.innerHTML = '<span></span>Voxelizing…';
  progress.style.width = '1%';
  worker.postMessage({ type: 'start', config: {
    preset: select('preset').value,
    mass_kg: Number(input('weight').value),
    spacing_m: Number(select('spacing').value),
    initial_c: Number(input('initial').value),
    oven_c: Number(input('oven').value),
    target_c: Number(input('target').value),
    convection: input('convection').checked,
    covered: input('covered').checked,
    max_roast_s: 8 * 3600,
    rest_s: 30 * 60,
    sample_interval_s: 60,
    moisture_kg_m2: 0.24
  }});
});

cancel.addEventListener('click', () => {
  worker.postMessage({ type: 'cancel' });
  running = false;
  cancel.hidden = true;
  status.className = 'status';
  status.innerHTML = '<span></span>Cancelled';
});

worker.onmessage = (event: MessageEvent<{ type: string; snapshot?: Snapshot; message?: string }>) => {
  if (event.data.type === 'error') {
    running = false; cancel.hidden = true; status.className = 'status error';
    status.innerHTML = `<span></span>${event.data.message ?? 'Simulation failed'}`;
    return;
  }
  if (!event.data.snapshot) return;
  current = event.data.snapshot;
  render(current);
  if (event.data.type === 'complete') {
    running = false; cancel.hidden = true;
    const horizonReached = (current.pull_time_s ?? 0) >= 8 * 3600 - 1;
    status.className = horizonReached ? 'status error' : 'status complete';
    status.innerHTML = horizonReached ? '<span></span>Target not reached by 8 h' : '<span></span>Complete';
    progress.style.width = '100%';
  } else {
    status.className = 'status working';
    status.innerHTML = `<span></span>${current.phase === 'rest' ? 'Calculating carryover…' : 'Solving oven phase…'}`;
  }
};

function render(snapshot: Snapshot) {
  progress.style.width = `${Math.max(2, snapshot.progress * 100)}%`;
  text('pull', snapshot.pull_time_s == null ? 'Calculating' : duration(snapshot.pull_time_s));
  text('peak', snapshot.pull_time_s == null ? '—' : `${snapshot.peak_core_c.toFixed(1)}°`);
  text('peak-time', snapshot.pull_time_s == null ? 'during rest' : `at +${Math.round(snapshot.peak_time_after_pull_s / 60)} min`);
  text('carry', snapshot.pull_time_s == null ? '—' : `${snapshot.carryover_c >= 0 ? '+' : ''}${snapshot.carryover_c.toFixed(1)}°`);
  text('energy', `${(snapshot.energy_relative_error * 100).toExponential(1)}%`);
  text('p70', formatExposure(snapshot.pasteurization_p70_s));
  text('slice-time', `t = ${duration(snapshot.samples.at(-1)?.time_s ?? 0)}`);
  drawCurve(snapshot.samples, previous);
  drawSlice(snapshot);
}

function formatExposure(seconds: number) {
  if (seconds < 0.01) return '< 0.01 equivalent seconds';
  if (seconds < 120) return `${seconds.toFixed(seconds < 10 ? 2 : 1)} equivalent seconds`;
  return `${(seconds / 60).toFixed(1)} equivalent minutes`;
}

function canvasContext(canvas: HTMLCanvasElement, cssHeight: number) {
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(300, canvas.clientWidth);
  canvas.width = Math.round(width * ratio); canvas.height = Math.round(cssHeight * ratio);
  const ctx = canvas.getContext('2d')!; ctx.scale(ratio, ratio);
  return { ctx, width, height: cssHeight };
}

function drawCurve(samples: Sample[], old?: Sample[]) {
  const { ctx, width, height } = canvasContext(curve, 300);
  const pad = { l: 45, r: 16, t: 15, b: 32 };
  ctx.clearRect(0, 0, width, height);
  const all = old ? samples.concat(old) : samples;
  const maxT = Math.max(80, ...all.map(s => s.hottest_c));
  const minT = Math.min(0, ...all.map(s => s.coldest_c));
  const maxTime = Math.max(60, ...all.map(s => s.time_s));
  const x = (t: number) => pad.l + t / maxTime * (width - pad.l - pad.r);
  const y = (t: number) => height - pad.b - (t - minT) / (maxT - minT) * (height - pad.t - pad.b);
  ctx.font = '11px ui-monospace, monospace'; ctx.fillStyle = '#857b72'; ctx.strokeStyle = '#ddd6cc'; ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) { const value = minT + i * (maxT - minT) / 4; const yy = y(value); ctx.beginPath(); ctx.moveTo(pad.l, yy); ctx.lineTo(width - pad.r, yy); ctx.stroke(); ctx.fillText(`${Math.round(value)}°`, 5, yy + 4); }
  ctx.fillText('0', pad.l, height - 8); ctx.fillText(`${(maxTime / 3600).toFixed(1)} h`, width - 45, height - 8);
  const line = (data: Sample[], key: keyof Pick<Sample, 'coldest_c'|'probe_c'|'hottest_c'>, color: string, dashed = false) => {
    if (!data.length) return; ctx.beginPath(); ctx.strokeStyle = color; ctx.lineWidth = dashed ? 1.2 : 2.4; ctx.setLineDash(dashed ? [5, 5] : []);
    data.forEach((s, i) => { const point = [x(s.time_s), y(s[key])] as const; i ? ctx.lineTo(...point) : ctx.moveTo(...point); }); ctx.stroke();
  };
  if (old) { line(old, 'coldest_c', '#776f68', true); line(old, 'probe_c', '#776f68', true); }
  line(samples, 'hottest_c', '#c9a982'); line(samples, 'probe_c', '#c44f35'); line(samples, 'coldest_c', '#442b2a'); ctx.setLineDash([]);
}

function colorFor(temp: number) {
  const stops: [number, number, number, number][] = [[35,38,26,28],[45,67,37,36],[52,168,77,56],[60,220,136,81],[68,233,182,117],[85,216,204,182]];
  let a = stops[0]!, b = stops.at(-1)!;
  for (let i = 1; i < stops.length; i++) if (temp <= stops[i]![0]) { a = stops[i-1]!; b = stops[i]!; break; }
  const f = Math.max(0, Math.min(1, (temp - a[0]) / (b[0] - a[0])));
  return `rgb(${Math.round(a[1]+f*(b[1]-a[1]))},${Math.round(a[2]+f*(b[2]-a[2]))},${Math.round(a[3]+f*(b[3]-a[3]))})`;
}

function drawSlice(snapshot: Snapshot) {
  const { ctx, width, height } = canvasContext(slice, 300);
  ctx.fillStyle = '#171311'; ctx.fillRect(0, 0, width, height);
  const cell = Math.min((width - 28) / snapshot.slice_width, (height - 28) / snapshot.slice_height);
  const ox = (width - cell * snapshot.slice_width) / 2, oy = (height - cell * snapshot.slice_height) / 2;
  snapshot.slice_c.forEach((temperature, index) => { if (temperature == null) return; const x = index % snapshot.slice_width, y = Math.floor(index / snapshot.slice_width); ctx.fillStyle = colorFor(temperature); ctx.fillRect(ox+x*cell, oy+y*cell, Math.ceil(cell+.2), Math.ceil(cell+.2)); });
}

window.addEventListener('resize', () => { if (current) render(current); else drawCurve([]); });
drawCurve([]);
