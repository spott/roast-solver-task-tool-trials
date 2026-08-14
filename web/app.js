const $ = id => document.getElementById(id);
const form = $('simulation-form');
const runButton = $('run-button');
const cancelButton = $('cancel-button');
const progressWrap = $('progress-wrap');
const progressBar = $('progress-bar');
const progressText = $('progress-text');
const engineState = $('engine-state');
const curveCanvas = $('curve-canvas');
const sliceCanvas = $('slice-canvas');

let worker;
let running = false;
let curve = [];
let latestSlice = null;
let latestResolution = 0;
let latestSummary = null;
let colorMode = 'doneness';
let activeConfig = null;
let latestPasteurization = null;

const colors = {
  ink: '#39342e', grid: '#ded7cc', muted: '#887f74', cold: '#c9472d',
  center: '#397887', mean: '#d59820', rest: '#8375a1',
};

function number(id) { return Number($(id).value); }
function readConfig() {
  return {
    preset: $('preset').value,
    massKg: number('mass'),
    resolution: number('resolution'),
    initialC: number('initial'),
    ovenC: number('oven'),
    targetC: number('target'),
    hConv: number('convection'),
    emissivity: number('emissivity'),
    covered: $('covered').checked,
    maxRoastMinutes: number('max-hours') * 60,
    restMinutes: number('rest-minutes'),
    ambientC: number('ambient'),
    restH: number('rest-h'),
    foilTent: $('foil').checked,
    chunkSeconds: 30,
  };
}
function validate(config) {
  if (config.targetC <= config.initialC) return 'Pull target must exceed starting temperature.';
  if (config.ovenC <= config.targetC) return 'Oven temperature must exceed the pull target.';
  if (!Object.values(config).every(v => typeof v !== 'number' || Number.isFinite(v))) return 'All numeric inputs must be valid.';
  return '';
}
function setRunning(value) {
  running = value;
  runButton.disabled = value || !worker;
  cancelButton.hidden = !value;
  progressWrap.hidden = !value;
  form.querySelectorAll('input, select').forEach(input => { input.disabled = value; });
  runButton.querySelector('span').textContent = value ? 'Simulation running' : 'Run simulation';
}
function resetResults() {
  curve = [];
  latestSlice = null;
  latestSummary = null;
  ['pull-time', 'peak-core', 'carryover'].forEach(id => $(id).textContent = '—');
  latestPasteurization = null;
  renderPasteurization();
  $('pull-note').textContent = 'to coldest-point target';
  $('peak-note').textContent = 'after rest';
  updateLive(null);
  $('chart-empty').hidden = false;
  $('slice-empty').hidden = false;
  drawCurve();
  drawSlice();
}
function initializeWorker() {
  try {
    worker = new Worker(new URL('./worker.js', import.meta.url), { type: 'module' });
    worker.onmessage = onWorkerMessage;
    worker.onerror = event => fail(event.message || 'Worker failed to load.');
  } catch (error) { fail(error.message); }
}
function onWorkerMessage(event) {
  const message = event.data || {};
  if (message.type === 'ready') {
    engineState.textContent = 'Engine ready';
    engineState.className = 'engine-state ready';
    if (!running) runButton.disabled = false;
  } else if (message.type === 'progress') {
    if (!running) return;
    curve.push(message.summary);
    latestSummary = message.summary;
    latestSlice = message.slice;
    latestResolution = message.resolution;
    $('chart-empty').hidden = true;
    $('slice-empty').hidden = true;
    updateProgress(message.summary);
    updateLive(message.summary);
    drawCurve();
    drawSlice();
  } else if (message.type === 'complete') {
    curve = message.curve;
    latestSlice = message.slice;
    latestResolution = message.resolution;
    latestSummary = curve.at(-1);
    showResult(message.result);
    updateLive(latestSummary);
    drawCurve();
    drawSlice();
    setRunning(false);
  } else if (message.type === 'cancelled') {
    setRunning(false);
    progressText.textContent = 'Cancelled. Partial results remain visible.';
  } else if (message.type === 'error') {
    fail(message.message);
  }
}
function fail(message) {
  setRunning(false);
  engineState.textContent = 'Engine error';
  engineState.className = 'engine-state error';
  progressWrap.hidden = false;
  progressText.textContent = message || 'Simulation failed.';
  console.error(message);
}

form.addEventListener('submit', event => {
  event.preventDefault();
  if (!form.reportValidity() || running) return;
  const config = readConfig();
  const error = validate(config);
  if (error) { progressWrap.hidden = false; progressText.textContent = error; return; }
  activeConfig = config;
  resetResults();
  setRunning(true);
  progressBar.style.width = '2%';
  progressText.textContent = 'Voxelizing the signed-distance shape…';
  worker.postMessage({ type: 'start', config });
});
cancelButton.addEventListener('click', () => {
  if (running) worker.postMessage({ type: 'cancel' });
});
$('show-pasteur').addEventListener('change', renderPasteurization);
document.querySelectorAll('[data-color-mode]').forEach(button => {
  button.addEventListener('click', () => {
    colorMode = button.dataset.colorMode;
    document.querySelectorAll('[data-color-mode]').forEach(b => b.classList.toggle('active', b === button));
    drawSlice();
    updateColorKey();
  });
});

function updateProgress(summary) {
  const roastLimit = activeConfig.maxRoastMinutes * 60;
  let fraction;
  if (summary.mode === 'roast') {
    const byTime = summary.time_s / roastLimit;
    const byTemp = (summary.coldest_c - activeConfig.initialC) / (activeConfig.targetC - activeConfig.initialC);
    fraction = Math.max(byTime * .75, Math.min(.82, byTemp * .82));
    progressText.textContent = `Roasting · coldest ${formatTemp(summary.coldest_c)} · ${formatTime(summary.time_s)}`;
  } else {
    const roastEnd = curve.find(s => s.mode === 'rest')?.time_s || summary.time_s;
    const restFraction = activeConfig.restMinutes ? (summary.time_s - roastEnd) / (activeConfig.restMinutes * 60) : 1;
    fraction = .84 + .15 * restFraction;
    progressText.textContent = `Resting · coldest ${formatTemp(summary.coldest_c)} · ${formatTime(summary.time_s - roastEnd)}`;
  }
  progressBar.style.width = `${Math.max(2, Math.min(99, fraction * 100))}%`;
}
function showResult(result) {
  progressBar.style.width = '100%';
  const pull = result.pull;
  const restElapsed = Math.max(0, result.peak.time_s - pull.time_s);
  $('pull-time').textContent = formatTime(pull.time_s);
  $('pull-note').textContent = result.hitTarget ? `pulled at ${formatTemp(pull.coldest_c)}` : `target not reached (${formatTemp(pull.coldest_c)})`;
  $('peak-core').textContent = formatTemp(result.peak.coldest_c);
  $('peak-note').textContent = restElapsed ? `${formatTime(restElapsed)} after pull` : 'at pull';
  $('carryover').textContent = `${result.carryover_c >= 0 ? '+' : ''}${result.carryover_c.toFixed(1)}°C`;
  latestPasteurization = result.pasteurization_s;
  renderPasteurization();
  progressText.textContent = result.hitTarget ? 'Simulation complete.' : 'Maximum roast time reached before target; rest was still simulated.';
}
function updateLive(summary) {
  $('phase-value').textContent = summary ? (summary.mode === 'rest' ? 'Carryover rest' : 'Oven roast') : 'Ready';
  $('elapsed-value').textContent = summary ? formatTime(summary.time_s) : '—';
  $('cold-value').textContent = summary ? formatTemp(summary.coldest_c) : '—';
  $('moisture-value').textContent = summary ? `${(summary.moisture_remaining_kg * 1000).toFixed(1)} g` : '—';
}
const formatTemp = value => `${value.toFixed(1)}°C`;
function formatTime(seconds) {
  const totalMinutes = Math.max(0, Math.round(seconds / 60));
  const hours = Math.floor(totalMinutes / 60), minutes = totalMinutes % 60;
  return hours ? `${hours}h ${String(minutes).padStart(2, '0')}m` : `${minutes} min`;
}
function formatEquivalent(seconds) {
  if (seconds < .01) return '<0.01 s';
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 2 : 1)} s`;
  return `${(seconds / 60).toFixed(1)} min`;
}
function renderPasteurization() {
  const shown = $('show-pasteur').checked;
  $('pasteurization').textContent = shown ? (latestPasteurization == null ? '—' : formatEquivalent(latestPasteurization)) : 'Hidden';
  $('pasteur-note').textContent = shown ? 'illustrative z = 7.5°C · not safety advice' : 'enable in advanced · not safety advice';
}

function sizeCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.min(devicePixelRatio || 1, 2);
  const width = Math.max(1, Math.round(rect.width * dpr));
  const height = Math.max(1, Math.round(rect.height * dpr));
  if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
  return { ctx: canvas.getContext('2d'), width, height, dpr };
}
function drawCurve() {
  const { ctx, width: w, height: h, dpr } = sizeCanvas(curveCanvas);
  ctx.clearRect(0, 0, w, h);
  if (curve.length < 2) return;
  const margin = { l: 43*dpr, r: 14*dpr, t: 8*dpr, b: 31*dpr };
  const plotW = w-margin.l-margin.r, plotH = h-margin.t-margin.b;
  const maxTime = Math.max(1, curve.at(-1).time_s);
  const values = curve.flatMap(s => [s.coldest_c, s.center_c, s.mean_c]);
  const minT = Math.floor((Math.min(...values)-5)/10)*10;
  const maxT = Math.ceil((Math.max(...values)+5)/10)*10;
  const rangeT = Math.max(10, maxT-minT);
  const x = t => margin.l + t/maxTime*plotW;
  const y = t => margin.t + (maxT-t)/rangeT*plotH;
  ctx.font = `${9*dpr}px DM Mono, ui-monospace, monospace`;
  ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
  for (let q=0; q<=4; q++) {
    const temp = minT + rangeT*q/4, yy = y(temp);
    ctx.strokeStyle = colors.grid; ctx.lineWidth = dpr*.6;
    ctx.beginPath(); ctx.moveTo(margin.l, yy); ctx.lineTo(w-margin.r, yy); ctx.stroke();
    ctx.fillStyle = colors.muted; ctx.fillText(`${Math.round(temp)}°`, margin.l-7*dpr, yy);
  }
  ctx.textBaseline = 'top';
  for (let q=0; q<=4; q++) {
    const time = maxTime*q/4, xx = x(time);
    ctx.textAlign = q===0 ? 'left' : q===4 ? 'right' : 'center';
    ctx.fillStyle = colors.muted; ctx.fillText(formatAxisTime(time), xx, h-margin.b+9*dpr);
  }
  const restStart = curve.find(s => s.mode === 'rest');
  if (restStart) {
    const xx = x(restStart.time_s);
    ctx.fillStyle = 'rgba(131,117,161,.08)'; ctx.fillRect(xx, margin.t, w-margin.r-xx, plotH);
    ctx.strokeStyle = colors.rest; ctx.setLineDash([3*dpr,3*dpr]);
    ctx.beginPath(); ctx.moveTo(xx, margin.t); ctx.lineTo(xx, margin.t+plotH); ctx.stroke(); ctx.setLineDash([]);
    ctx.textAlign='left'; ctx.textBaseline='top'; ctx.fillStyle=colors.rest; ctx.fillText('REST', xx+5*dpr, margin.t+4*dpr);
  }
  [['mean_c', colors.mean], ['center_c', colors.center], ['coldest_c', colors.cold]].forEach(([key,color]) => {
    ctx.beginPath(); curve.forEach((s,index) => { const xx=x(s.time_s), yy=y(s[key]); index ? ctx.lineTo(xx,yy) : ctx.moveTo(xx,yy); });
    ctx.strokeStyle=color; ctx.lineWidth=key==='coldest_c'?2*dpr:1.4*dpr; ctx.lineJoin='round'; ctx.stroke();
  });
}
function formatAxisTime(seconds) {
  const hours = seconds/3600;
  return hours >= 1 ? `${hours.toFixed(hours < 3 ? 1 : 0)}h` : `${Math.round(seconds/60)}m`;
}

const donenessStops = [
  { limit: -10, color: [74,43,76], label: '>10°C below target' },
  { limit: -3, color: [169,65,72], label: 'Approaching target' },
  { limit: 4, color: [221,136,92], label: 'At target band' },
  { limit: Infinity, color: [116,66,36], label: '>4°C over target' },
];
function drawSlice() {
  const { ctx, width: w, height: h } = sizeCanvas(sliceCanvas);
  ctx.fillStyle='#27241f'; ctx.fillRect(0,0,w,h);
  if (!latestSlice || !latestResolution) return;
  const n=latestResolution;
  const pixel=document.createElement('canvas'); pixel.width=n; pixel.height=n;
  const pctx=pixel.getContext('2d'); const image=pctx.createImageData(n,n);
  let min=activeConfig?.initialC ?? 0;
  let max=Math.max((activeConfig?.targetC ?? 60)+25, latestSummary?.mean_c ?? 80);
  for(let q=0;q<latestSlice.length;q++) {
    const t=latestSlice[q], o=q*4;
    if(!Number.isFinite(t)) { image.data[o+3]=0; continue; }
    const rgb=colorMode==='doneness' ? donenessColor(t-(activeConfig?.targetC ?? 60)) : thermalColor((t-min)/(max-min));
    image.data[o]=rgb[0]; image.data[o+1]=rgb[1]; image.data[o+2]=rgb[2]; image.data[o+3]=255;
  }
  pctx.putImageData(image,0,0);
  const scale=Math.min(w/n,h/n)*.88, dw=n*scale, dh=n*scale;
  ctx.imageSmoothingEnabled=false;
  ctx.drawImage(pixel,(w-dw)/2,(h-dh)/2,dw,dh);
}
function donenessColor(delta) { return donenessStops.find(stop => delta < stop.limit).color; }
function thermalColor(value) {
  const stops=[[28,35,70],[43,95,133],[58,157,143],[230,183,72],[202,64,42],[247,230,180]];
  const x=Math.max(0,Math.min(.999,value))*(stops.length-1), i=Math.floor(x), f=x-i;
  return stops[i].map((v,q)=>Math.round(v+(stops[Math.min(i+1,stops.length-1)][q]-v)*f));
}
function updateColorKey() {
  const key=$('color-key');
  if(colorMode==='doneness') {
    key.innerHTML=donenessStops.map(stop=>`<div class="key-item"><i style="background:rgb(${stop.color})"></i>${stop.label}</div>`).join('');
  } else {
    key.innerHTML='<div class="key-item"><i style="background:linear-gradient(90deg,#1c2346,#3a9d8f,#e6b748,#ca402a)"></i>Cool → hot</div>';
  }
}

new ResizeObserver(() => { drawCurve(); drawSlice(); }).observe(document.querySelector('.results-column'));
updateColorKey();
resetResults();
initializeWorker();
