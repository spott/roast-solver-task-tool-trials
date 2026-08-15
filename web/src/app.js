const $ = (id) => document.getElementById(id);
const form = $("setup-form");
const runButton = $("run");
const curveCanvas = $("curve");
const sliceCanvas = $("slice");
let worker;
let points = [];
let comparison = [];
let gridSize = 31;
let target = 57;
let pullProbe = null;
let running = false;

function configFromForm() {
  return {
    preset: $("preset").value,
    massKg: Number($("mass").value),
    ovenC: Number($("oven").value),
    initialC: Number($("initial").value),
    targetC: Number($("target").value),
    convection: $("convection").checked,
    covered: $("covered").checked,
    gridSize: 31,
    maxCookMinutes: Number($("max-cook").value),
    restMinutes: Number($("rest").value),
  };
}

function createWorker() {
  if (worker) worker.terminate();
  worker = new Worker("worker.js", { type: "module" });
  worker.onmessage = handleWorkerMessage;
  worker.onerror = (event) => showError(event.message);
}

function formatTime(seconds) {
  if (!(seconds >= 0)) return "Not reached";
  const minutes = Math.round(seconds / 60);
  return minutes >= 60 ? `${Math.floor(minutes / 60)}h ${minutes % 60}m` : `${minutes} min`;
}

function setRunning(value) {
  running = value;
  runButton.disabled = value;
  runButton.querySelector("span").textContent = value ? "Solving locally…" : "Run prediction";
  $("status-dot").classList.toggle("running", value);
}

function showError(message) {
  setRunning(false);
  $("status").textContent = "Solver error";
  $("progress-label").textContent = message;
  $("status-dot").style.background = "#c85043";
}

function handleWorkerMessage({ data }) {
  if (data.type === "ready") {
    gridSize = data.gridSize;
    $("slice-index").max = gridSize - 1;
    $("slice-index").value = Math.floor(gridSize / 2);
    $("slice-label").value = `center · ${Math.floor(gridSize / 2) + 1}/${gridSize}`;
    $("status").textContent = "Cooking · embedded Robin boundary";
    $("progress-label").textContent = `${gridSize}³ WASM grid`;
  }
  if (data.type === "progress") {
    points.push(data.point);
    if (data.point.phase === 1 && pullProbe === null) pullProbe = data.point.probe;
    $("status").textContent = data.point.phase === 0 ? "Cooking · wet surface / crust stages" : data.point.phase === 1 ? "Resting · carryover" : "Finalizing";
    $("progress-label").textContent = `${formatTime(data.point.time)} · moisture ${Math.round(data.point.moisture * 100)}%`;
    $("pasteurization").textContent = `${data.point.pasteurization.toFixed(data.point.pasteurization < 1 ? 3 : 1)} min @ 70°C`;
    if (data.slice && Number($("slice-index").value) === Math.floor(gridSize / 2)) drawSlice(data.slice, data.gridSize);
    drawCurves();
  }
  if (data.type === "slice") drawSlice(data.slice, data.gridSize);
  if (data.type === "complete") {
    setRunning(false);
    drawSlice(data.slice, data.gridSize);
    const m = data.metrics;
    $("pull-time").textContent = formatTime(m.pullTime);
    $("peak").textContent = `${m.peak.toFixed(1)}°C`;
    $("peak-time").textContent = m.pullTime >= 0 ? `at +${Math.round(m.peakAfterPull / 60)} min rest` : "target not reached";
    $("carryover").textContent = m.pullTime >= 0 ? `+${Math.max(0, m.peak - m.pullProbe).toFixed(1)}°C` : "—";
    $("mass-loss").textContent = `${(m.evaporatedKg * 1000).toFixed(0)} g`;
    $("pasteurization").textContent = `${m.pasteurization.toFixed(m.pasteurization < 1 ? 3 : 1)} min @ 70°C`;
    $("status").textContent = m.pullTime >= 0 ? "Prediction complete" : "Cook limit reached before target";
    $("progress-label").textContent = "Results are model estimates";
  }
  if (data.type === "error") showError(data.message);
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const config = configFromForm();
  if (!form.reportValidity() || config.targetC >= config.ovenC) {
    if (config.targetC >= config.ovenC) showError("Pull target must be below oven temperature.");
    return;
  }
  comparison = $("comparison").checked ? points.slice() : [];
  points = [];
  pullProbe = null;
  target = config.targetC;
  for (const id of ["pull-time", "peak", "carryover", "mass-loss", "pasteurization"]) $(id).textContent = "—";
  $("peak-time").textContent = "during rest";
  $("chart-empty").style.display = "none";
  createWorker();
  setRunning(true);
  worker.postMessage({ type: "start", config });
  drawCurves();
});

$("slice-index").addEventListener("input", (event) => {
  const index = Number(event.target.value);
  $("slice-label").value = `${index === Math.floor(gridSize / 2) ? "center · " : ""}${index + 1}/${gridSize}`;
  if (worker) worker.postMessage({ type: "slice", index });
});

function canvasContext(canvas) {
  const rect = canvas.getBoundingClientRect();
  const ratio = Math.min(devicePixelRatio || 1, 2);
  const width = Math.max(1, Math.round(rect.width * ratio));
  const height = Math.max(1, Math.round(rect.height * ratio));
  if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return [context, rect.width, rect.height];
}

function drawCurves() {
  const [ctx, width, height] = canvasContext(curveCanvas);
  ctx.clearRect(0, 0, width, height);
  const all = points.length ? points : comparison;
  if (!all.length) return;
  const margin = { left: 43, right: 12, top: 12, bottom: 28 };
  const w = width - margin.left - margin.right;
  const h = height - margin.top - margin.bottom;
  const maxTime = Math.max(...all.map((p) => p.time), ...comparison.map((p) => p.time), 60);
  const values = [...points, ...comparison].flatMap((p) => [p.coldest, p.probe, p.hottest]);
  const minTemp = Math.floor((Math.min(...values, target) - 5) / 10) * 10;
  const maxTemp = Math.ceil((Math.max(...values, target) + 5) / 10) * 10;
  const x = (time) => margin.left + time / maxTime * w;
  const y = (temp) => margin.top + (maxTemp - temp) / Math.max(1, maxTemp - minTemp) * h;
  ctx.font = "9px 'DM Mono', monospace";
  ctx.strokeStyle = "#332f29"; ctx.fillStyle = "#746e65"; ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i += 1) {
    const temp = minTemp + (maxTemp - minTemp) * i / 4;
    ctx.beginPath(); ctx.moveTo(margin.left, y(temp)); ctx.lineTo(width - margin.right, y(temp)); ctx.stroke();
    ctx.fillText(`${Math.round(temp)}°`, 6, y(temp) + 3);
  }
  ctx.fillText(`${Math.round(maxTime / 60)} min`, width - 46, height - 7);
  ctx.setLineDash([4, 4]); ctx.strokeStyle = "#9c714c"; ctx.beginPath(); ctx.moveTo(margin.left, y(target)); ctx.lineTo(width-margin.right,y(target));ctx.stroke();ctx.setLineDash([]);
  const line = (series, key, color, dash = []) => {
    if (series.length < 2) return;
    ctx.strokeStyle = color; ctx.lineWidth = key === "probe" ? 2 : 1.35; ctx.setLineDash(dash); ctx.beginPath();
    series.forEach((p, index) => { const command = index ? "lineTo" : "moveTo"; ctx[command](x(p.time), y(p[key])); }); ctx.stroke(); ctx.setLineDash([]);
  };
  line(comparison, "probe", "#77716a", [5, 4]);
  line(points, "coldest", "#83a9c7"); line(points, "probe", "#e6b66a"); line(points, "hottest", "#e36c3f");
}

function temperatureColor(value) {
  if (!Number.isFinite(value)) return [0, 0, 0, 0];
  if (value <= target) {
    const u = Math.max(0, Math.min(1, (value - 0) / Math.max(target, 1)));
    return [Math.round(30 + 180 * u), Math.round(55 + 100 * u), Math.round(78 - 20 * u), 255];
  }
  const u = Math.min(1, (value - target) / 15);
  return [Math.round(210 - 25 * u), Math.round(155 - 85 * u), Math.round(78 - 45 * u), 255];
}

function drawSlice(values, n) {
  const context = sliceCanvas.getContext("2d");
  sliceCanvas.width = n; sliceCanvas.height = n;
  const image = context.createImageData(n, n);
  for (let x = 0; x < n; x += 1) for (let y = 0; y < n; y += 1) {
    const color = temperatureColor(values[x * n + y]);
    const pixel = ((n - 1 - y) * n + x) * 4;
    image.data.set(color, pixel);
  }
  context.putImageData(image, 0, 0);
  $("slice-caption").textContent = `Current modeled field · target band starts at ${target}°C. Transparent cells are outside the SDF.`;
}

window.addEventListener("resize", () => drawCurves());
drawCurves();
