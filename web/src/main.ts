import './style.css';
import type { RecordPoint, SolverChunk, SolverInput, WorkerResponse } from './types';

const app = document.querySelector<HTMLDivElement>('#app');
if (!app) throw new Error('Missing app root');

app.innerHTML = `
<header class="masthead">
  <div>
    <p class="eyebrow">Finite-volume cooking lab</p>
    <h1>Roast Solver</h1>
    <p class="lede">Explore heat, moisture, carryover, and pasteurization in a 3D roast—entirely in your browser.</p>
  </div>
  <div class="model-badge"><span></span> CPU · WASM · local</div>
</header>
<main>
  <aside class="control-panel panel">
    <form id="controls">
      <div class="section-title"><span>01</span><h2>Food</h2></div>
      <div class="preset-grid" role="radiogroup" aria-label="Shape preset">
        <label class="preset active"><input type="radio" name="preset" value="roast" checked><b>Roast</b><small>superellipsoid</small></label>
        <label class="preset"><input type="radio" name="preset" value="bird"><b>Bird</b><small>body + cavity</small></label>
        <label class="preset"><input type="radio" name="preset" value="slab"><b>Slab</b><small>rounded cut</small></label>
        <label class="preset"><input type="radio" name="preset" value="ham"><b>Ham</b><small>sphere</small></label>
      </div>
      <div class="field-row">
        <label>Mass <span><input id="mass" type="number" min="0.2" max="12" step="0.1" value="1.5"> kg</span></label>
        <label>Starts at <span><input id="initial" type="number" min="-2" max="30" step="1" value="5"> °C</span></label>
      </div>

      <div class="section-title"><span>02</span><h2>Cook</h2></div>
      <label class="slider-label">Oven <output id="oven-out">180 °C</output><input id="oven" type="range" min="90" max="260" value="180" step="5"></label>
      <label class="slider-label">Pull when coldest point reaches <output id="target-out">63 °C</output><input id="target" type="range" min="45" max="85" value="63" step="1"></label>
      <div class="field-row">
        <label>Convection <span><input id="hcoef" type="number" min="2" max="60" step="1" value="10"> W/m²K</span></label>
        <label>Maximum <span><input id="max-hours" type="number" min="0.25" max="12" step="0.25" value="5"> h</span></label>
      </div>
      <div class="toggle-row">
        <label><input id="covered" type="checkbox"><span></span> Covered</label>
        <label><input id="pan" type="checkbox" checked><span></span> Insulated pan patch</label>
      </div>

      <div class="section-title"><span>03</span><h2>Rest & numerics</h2></div>
      <div class="field-row">
        <label>Rest <span><input id="rest" type="number" min="0" max="120" step="5" value="30"> min</span></label>
        <label>Grid <span><select id="resolution"><option value="20">20 · quick</option><option value="28" selected>28 · balanced</option><option value="36">36 · detailed</option><option value="48">48 · slow</option></select></span></label>
      </div>
      <div class="toggle-row"><label><input id="foil" type="checkbox"><span></span> Foil-tent during rest</label></div>
      <details>
        <summary>Advanced physics</summary>
        <div class="field-row details-grid">
          <label>Emissivity <span><input id="emissivity" type="number" min="0" max="1" step="0.05" value="0.9"></span></label>
          <label>Surface water <span><input id="water" type="number" min="0" max="1" step="0.05" value="0.25"> kg/m²</span></label>
          <label>Rest ambient <span><input id="ambient" type="number" min="0" max="40" step="1" value="22"> °C</span></label>
          <label>Pasteurization ref. <span><input id="pasteur-ref" type="number" min="55" max="75" step="1" value="70"> °C</span></label>
        </div>
      </details>
      <div class="actions">
        <button id="run" type="submit"><span>Run simulation</span><i>→</i></button>
        <button id="cancel" class="secondary" type="button" disabled>Stop</button>
      </div>
      <p class="fineprint">A mechanistic estimate, not food-safety advice. Calibration fixtures are synthetic—not measurements.</p>
    </form>
  </aside>

  <section class="results">
    <div class="status-strip panel">
      <div><span id="status-dot" class="status-dot"></span><strong id="status">WASM loading…</strong><small id="status-detail">Choose inputs, then run</small></div>
      <div class="progress"><span id="progress-bar"></span></div>
      <b id="progress-label">0%</b>
    </div>

    <div class="metrics">
      <article><small>Pull time</small><strong id="pull">—</strong><span id="pull-note">coldest-point target</span></article>
      <article><small>Carryover</small><strong id="carry">—</strong><span id="peak">peak after pull</span></article>
      <article><small>Pasteurization</small><strong id="pasteur">—</strong><span id="pasteur-note">equivalent min at 70 °C</span></article>
      <article><small>Energy closure</small><strong id="energy">—</strong><span>discrete surface / enthalpy</span></article>
    </div>

    <article class="chart-card panel">
      <div class="card-heading"><div><p class="eyebrow">Thermal history</p><h2>Temperature curves</h2></div><div class="legend"><span class="core">Cold spot</span><span class="probe">Center probe</span><span class="surface">Surface</span></div></div>
      <canvas id="chart" aria-label="Temperature curves"></canvas>
      <div class="axis-note">Elapsed time</div>
    </article>

    <article class="slice-card panel">
      <div class="card-heading">
        <div><p class="eyebrow">Volume field</p><h2>Interior slice</h2></div>
        <div class="view-controls"><select id="view-mode"><option value="temperature">Temperature</option><option value="doneness">Target doneness</option><option value="wetness">Surface wetness</option></select><label>Depth <input id="slice" type="range" min="0" max="1" value="0" disabled></label></div>
      </div>
      <div class="slice-wrap"><canvas id="slice-canvas" aria-label="Axial temperature slice"></canvas><div class="colorbar"><span id="color-max">hot</span><i></i><span id="color-min">cold</span></div></div>
      <div class="slice-footer"><span id="slice-label">Run a simulation to inspect the volume.</span><span id="grid-label">— cells</span></div>
    </article>
  </section>
</main>
<footer><strong>Roast Solver M6</strong><span>Local-first · open numerical model · no probe data fitted</span><span>Model notes included in the repository</span></footer>
`;

function byId<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!element) throw new Error(`Missing #${id}`);
  return element as T;
}

const form = byId<HTMLFormElement>('controls');
const runButton = byId<HTMLButtonElement>('run');
const cancelButton = byId<HTMLButtonElement>('cancel');
const chartCanvas = byId<HTMLCanvasElement>('chart');
const sliceCanvas = byId<HTMLCanvasElement>('slice-canvas');
const sliceInput = byId<HTMLInputElement>('slice');
const viewMode = byId<HTMLSelectElement>('view-mode');
const worker = new Worker(new URL('./solver.worker.ts', import.meta.url), { type: 'module' });
let runId = 0;
let running = false;
let records: RecordPoint[] = [];
let latest: SolverChunk | undefined;
let activeInput: SolverInput | undefined;

function number(id: string): number {
  return Number(byId<HTMLInputElement>(id).value);
}
function selectedPreset(): SolverInput['preset'] {
  return (form.querySelector<HTMLInputElement>('input[name="preset"]:checked')?.value ?? 'roast') as SolverInput['preset'];
}
function buildInput(): SolverInput {
  return {
    preset: selectedPreset(), mass_kg: number('mass'), resolution: number('resolution'), material_density: 1060,
    initial_c: number('initial'), target_c: number('target'), oven_c: number('oven'), convection_h: number('hcoef'),
    emissivity: number('emissivity'), wall_c: null, covered: byId<HTMLInputElement>('covered').checked,
    ambient_vapor_density: 0.010, lewis_number: 0.90, surface_water_kg_m2: number('water'),
    pan_insulated: byId<HTMLInputElement>('pan').checked, max_cook_s: number('max-hours') * 3600,
    rest_s: number('rest') * 60, sample_interval_s: 30, requested_dt_s: 30,
    rest_ambient_c: number('ambient'), rest_h: 7, foil_tent: byId<HTMLInputElement>('foil').checked,
    pasteurization_ref_c: number('pasteur-ref'), pasteurization_z_c: 10, denaturation_bump: false,
  };
}

function setStatus(label: string, detail: string, state: 'idle' | 'running' | 'done' | 'error'): void {
  byId('status').textContent = label;
  byId('status-detail').textContent = detail;
  byId('status-dot').className = `status-dot ${state}`;
}
function setRunning(value: boolean): void {
  running = value;
  runButton.disabled = value;
  cancelButton.disabled = !value;
  runButton.querySelector('span')!.textContent = value ? 'Computing…' : 'Run simulation';
}
function formatTime(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return '—';
  const hours = Math.floor(seconds / 3600);
  const mins = Math.round((seconds % 3600) / 60);
  return hours > 0 ? `${hours}h ${String(mins).padStart(2, '0')}m` : `${mins} min`;
}
function updateMetrics(chunk: SolverChunk): void {
  byId('pull').textContent = formatTime(chunk.pull_time_s);
  byId('pull-note').textContent = chunk.pull_reached ? `target reached · dt ${chunk.dt_s.toFixed(1)} s` : chunk.done ? 'target not reached before limit' : 'coldest-point target';
  byId('carry').textContent = chunk.pull_time_s === null ? '—' : `${chunk.carryover_c >= 0 ? '+' : ''}${chunk.carryover_c.toFixed(1)} °C`;
  byId('peak').textContent = chunk.pull_time_s === null ? 'peak after pull' : `peak ${chunk.peak_core_c.toFixed(1)} °C at ${formatTime(chunk.peak_time_s)}`;
  const last = records.at(-1);
  byId('pasteur').textContent = last ? `${last.pasteurization_equivalent_min.toFixed(last.pasteurization_equivalent_min < 10 ? 2 : 1)} min` : '—';
  byId('pasteur-note').textContent = `equivalent at ${activeInput?.pasteurization_ref_c ?? 70} °C · z=10 °C`;
  byId('energy').textContent = chunk.done ? `${(chunk.energy.relative_balance_error * 100).toPrecision(2)}%` : 'tracking';
}

function fitCanvas(canvas: HTMLCanvasElement, cssHeight: number): CanvasRenderingContext2D {
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(canvas.clientWidth, 320);
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(cssHeight * ratio);
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Canvas unavailable');
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return context;
}
function drawEmptyChart(): void {
  const ctx = fitCanvas(chartCanvas, 300);
  const w = chartCanvas.clientWidth;
  ctx.fillStyle = '#f7f5f0'; ctx.fillRect(0, 0, w, 300);
  ctx.strokeStyle = '#ddd8cd'; ctx.setLineDash([3, 5]);
  for (let y = 50; y < 270; y += 55) { ctx.beginPath(); ctx.moveTo(52, y); ctx.lineTo(w - 16, y); ctx.stroke(); }
  ctx.setLineDash([]); ctx.fillStyle = '#817b70'; ctx.font = '13px system-ui'; ctx.fillText('Temperature history appears here', 64, 155);
}
function drawChart(): void {
  if (records.length < 2) { drawEmptyChart(); return; }
  const ctx = fitCanvas(chartCanvas, 300); const w = chartCanvas.clientWidth; const h = 300;
  const pad = { l: 52, r: 18, t: 18, b: 34 };
  const maxTime = Math.max(...records.map(r => r.time_s), 1);
  const values = records.flatMap(r => [r.coldest_c, r.probe_c, r.surface_mean_c]);
  const minT = Math.floor((Math.min(...values, activeInput?.initial_c ?? 0) - 5) / 10) * 10;
  const maxT = Math.ceil((Math.max(...values, activeInput?.oven_c ?? 100) + 5) / 20) * 20;
  const x = (t: number): number => pad.l + t / maxTime * (w - pad.l - pad.r);
  const y = (t: number): number => pad.t + (maxT - t) / (maxT - minT) * (h - pad.t - pad.b);
  ctx.fillStyle = '#f7f5f0'; ctx.fillRect(0, 0, w, h); ctx.font = '11px system-ui'; ctx.fillStyle = '#777267';
  ctx.strokeStyle = '#dfdbd2'; ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) { const temp = minT + (maxT - minT) * i / 4; const yy = y(temp); ctx.beginPath(); ctx.moveTo(pad.l, yy); ctx.lineTo(w - pad.r, yy); ctx.stroke(); ctx.fillText(`${Math.round(temp)}°`, 10, yy + 4); }
  for (let i = 0; i <= 4; i++) { const time = maxTime * i / 4; const xx = x(time); ctx.fillText(formatTime(time), Math.max(2, xx - 16), h - 10); }
  const restStart = records.find(r => r.phase === 'rest')?.time_s;
  if (restStart !== undefined) { ctx.fillStyle = 'rgba(42,101,94,.07)'; ctx.fillRect(x(restStart), pad.t, w - pad.r - x(restStart), h - pad.t - pad.b); ctx.fillStyle = '#2a655e'; ctx.fillText('REST', x(restStart) + 7, pad.t + 14); }
  const lines: Array<[keyof RecordPoint, string, number]> = [['surface_mean_c', '#d47a38', 2], ['probe_c', '#183c39', 2.5], ['coldest_c', '#9b3434', 2.5]];
  for (const [key, color, width] of lines) { ctx.beginPath(); records.forEach((r, i) => { const px = x(r.time_s); const py = y(r[key] as number); if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py); }); ctx.strokeStyle = color; ctx.lineWidth = width; ctx.stroke(); }
  if (activeInput) { ctx.setLineDash([5, 4]); ctx.strokeStyle = '#9b343488'; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(pad.l, y(activeInput.target_c)); ctx.lineTo(w - pad.r, y(activeInput.target_c)); ctx.stroke(); ctx.setLineDash([]); }
}

function thermalColor(value: number, min: number, max: number): [number, number, number] {
  const t = Math.max(0, Math.min(1, (value - min) / Math.max(max - min, 1e-6)));
  const stops: Array<[number, number, number]> = [[24, 46, 51], [42, 101, 94], [216, 181, 99], [210, 93, 52], [116, 31, 38]];
  const p = t * (stops.length - 1); const i = Math.min(Math.floor(p), stops.length - 2); const f = p - i;
  const a = stops[i]!; const b = stops[i + 1]!;
  return [Math.round(a[0] + (b[0] - a[0]) * f), Math.round(a[1] + (b[1] - a[1]) * f), Math.round(a[2] + (b[2] - a[2]) * f)];
}
function drawSlice(): void {
  if (!latest || !activeInput) { const ctx = fitCanvas(sliceCanvas, 340); ctx.fillStyle = '#161e1d'; ctx.fillRect(0, 0, sliceCanvas.clientWidth, 340); ctx.fillStyle = '#83918c'; ctx.font = '13px system-ui'; ctx.fillText('3D voxel field waiting for a run', 24, 170); return; }
  const chunk = latest; const input = activeInput;
  const [nz, ny, nx] = chunk.dimensions_zyx; const z = Math.min(Number(sliceInput.value), nz - 1); const mode = viewMode.value;
  const off = document.createElement('canvas'); off.width = nx; off.height = ny; const ox = off.getContext('2d')!; const image = ox.createImageData(nx, ny);
  const tMin = input.initial_c; let tMax = input.target_c + 12;
  chunk.temperatures_c.forEach((temperature, i) => { if (chunk.inside[i]) tMax = Math.max(tMax, temperature); });
  for (let y = 0; y < ny; y++) for (let x = 0; x < nx; x++) {
    const source = (z * ny + y) * nx + x; const dest = ((ny - 1 - y) * nx + x) * 4;
    if (!latest.inside[source]) { image.data[dest + 3] = 0; continue; }
    let value: number; let min: number; let max: number;
    if (mode === 'wetness') { value = latest.wet_fraction[source] ?? 0; min = 0; max = 1; }
    else if (mode === 'doneness') { value = latest.temperatures_c[source] ?? tMin; min = activeInput.target_c - 20; max = activeInput.target_c + 5; }
    else { value = latest.temperatures_c[source] ?? tMin; min = tMin; max = tMax; }
    const color = mode === 'wetness' ? thermalColor(value, min, max).reverse() as [number,number,number] : thermalColor(value, min, max);
    image.data[dest] = color[0]; image.data[dest + 1] = color[1]; image.data[dest + 2] = color[2]; image.data[dest + 3] = 255;
  }
  ox.putImageData(image, 0, 0); const ctx = fitCanvas(sliceCanvas, 340); const w = sliceCanvas.clientWidth;
  ctx.fillStyle = '#161e1d'; ctx.fillRect(0, 0, w, 340); ctx.imageSmoothingEnabled = false;
  const scale = Math.min((w - 32) / nx, 308 / ny); const dw = nx * scale; const dh = ny * scale; ctx.drawImage(off, (w - dw) / 2, (340 - dh) / 2, dw, dh);
  const depth = nz <= 1 ? 0 : (z / (nz - 1) * 100);
  byId('slice-label').textContent = `${mode[0]!.toUpperCase()}${mode.slice(1)} · axial depth ${depth.toFixed(0)}%`;
  byId('grid-label').textContent = `${nz} × ${ny} × ${nx} grid · ${latest.inside.filter(Boolean).length.toLocaleString()} food cells`;
  if (mode === 'temperature') { byId('color-max').textContent = `${tMax.toFixed(0)} °C`; byId('color-min').textContent = `${tMin.toFixed(0)} °C`; }
  else if (mode === 'doneness') { byId('color-max').textContent = 'at target'; byId('color-min').textContent = '20 °C under'; }
  else { byId('color-max').textContent = 'wet'; byId('color-min').textContent = 'dry'; }
}

function handleChunk(chunk: SolverChunk): void {
  latest = chunk; records.push(...chunk.records);
  const percent = Math.round(chunk.progress * 100); byId<HTMLElement>('progress-bar').style.width = `${percent}%`; byId('progress-label').textContent = `${percent}%`;
  setStatus(chunk.done ? 'Simulation complete' : chunk.phase === 'cook' ? 'Cooking in worker' : 'Resting & carryover', `${records.length} samples · ${chunk.dimensions_zyx.join(' × ')} grid`, chunk.done ? 'done' : 'running');
  if (sliceInput.disabled) { sliceInput.disabled = false; sliceInput.min = '0'; sliceInput.max = String(chunk.dimensions_zyx[0] - 1); sliceInput.value = String(Math.floor(chunk.dimensions_zyx[0] / 2)); }
  updateMetrics(chunk); drawChart(); drawSlice();
  if (chunk.done) setRunning(false);
}

worker.onmessage = (event: MessageEvent<WorkerResponse>): void => {
  const message = event.data;
  if (message.type === 'ready') { if (!running) setStatus('Ready to simulate', 'WASM core loaded locally', 'idle'); return; }
  if (message.runId !== runId) return;
  if (message.type === 'chunk') handleChunk(message.chunk);
  else { setRunning(false); setStatus('Simulation failed', message.message, 'error'); }
};
worker.onerror = (event): void => { setRunning(false); setStatus('Worker failed', event.message, 'error'); };

form.addEventListener('submit', (event) => {
  event.preventDefault(); runId += 1; records = []; latest = undefined; activeInput = buildInput(); sliceInput.disabled = true;
  setRunning(true); setStatus('Preparing voxel model', `${activeInput.resolution} cells across longest axis`, 'running');
  byId<HTMLElement>('progress-bar').style.width = '1%'; byId('progress-label').textContent = '1%'; drawChart(); drawSlice();
  worker.postMessage({ type: 'start', runId, input: activeInput });
});
cancelButton.addEventListener('click', () => { worker.postMessage({ type: 'cancel', runId }); setRunning(false); setStatus('Stopped', 'Partial result remains visible', 'idle'); });
sliceInput.addEventListener('input', drawSlice); viewMode.addEventListener('change', drawSlice);
for (const id of ['oven', 'target']) byId<HTMLInputElement>(id).addEventListener('input', () => { byId(`${id}-out`).textContent = `${number(id)} °C`; });
for (const radio of form.querySelectorAll<HTMLInputElement>('input[name="preset"]')) radio.addEventListener('change', () => { form.querySelectorAll('.preset').forEach(el => el.classList.remove('active')); radio.closest('.preset')?.classList.add('active'); });
window.addEventListener('resize', () => { drawChart(); drawSlice(); });

drawEmptyChart(); drawSlice();
