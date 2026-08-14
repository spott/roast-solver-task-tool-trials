import { formatDuration, historyRows, presetId, tempColor } from "./ui-utils.js";
const $ = id => document.getElementById(id);
const worker = new Worker("./solver-worker.js", { type: "module" });
let runId = 0, current = [], prior = [], latestImage = null, target = 60, running = false;
const form = $("cook-form"), curveCanvas = $("curve"), sliceCanvas = $("slice");

function readConfig() {
  return { preset: presetId($("preset").value), resolution: +$("resolution").value, mass: +$("mass").value,
    oven: +$("oven").value, initial: +$("initial").value, target: +$("target").value,
    maxCook: +$("maxCook").value * 3600, rest: +$("rest").value * 60,
    convection: $("convection").checked, covered: $("covered").checked, foil: $("foil").checked };
}
function setStatus(kind, title, detail, progress = 0) {
  $("status").className = `status panel ${kind}`; $("status-title").textContent = title;
  $("status-detail").textContent = detail; $("progress-bar").style.width = `${Math.max(0, Math.min(1, progress)) * 100}%`;
}
function valid(c) { return c.mass > 0 && c.oven > c.target && c.target > c.initial && c.maxCook > 0 && c.rest >= 0; }
form.addEventListener("submit", event => {
  event.preventDefault(); const config = readConfig(); if (!valid(config)) { setStatus("error", "Check the setup", "Starting temperature must be below target, and target below oven"); return; }
  if ($("keepOverlay").checked && current.length) prior = current; else prior = [];
  current = []; latestImage = null; target = config.target; runId++; running = true; $("run").disabled = true; $("slice-position").disabled = true;
  setStatus("running", "Solving the 3D field", `Grid ${config.resolution}³ span · initializing geometry`, .01);
  worker.postMessage({ type: "start", runId, config }); drawCurve(); drawEmptySlice();
});
$("slice-position").addEventListener("input", event => { if (!running && latestImage) worker.postMessage({type:"slice",runId,fraction:+event.target.value/100}); });
worker.onmessage = ({ data }) => {
  if (data.runId !== runId) return;
  if (data.type === "error") { running=false; $("run").disabled=false; setStatus("error","Solver stopped",data.message); return; }
  if (data.curve) { current = historyRows(data.curve); latestImage = data.image; drawCurve(); drawSlice(data.image); updateOutputs(data.result, data.image.n); }
  if (data.type === "progress") { const phase=Number.isFinite(data.result.pullTime)?"Rest / carryover":"Cooking"; setStatus("running",phase,`${Math.round(data.result.elapsed/60)} simulated min · progressive worker batches`,data.progress); }
  if (data.type === "complete") { running=false; $("run").disabled=false; $("slice-position").disabled=false; setStatus("", "Prediction complete", `${current.length} curve samples · local Rust/WASM`,1); }
  if (data.type === "slice") { latestImage=data.image; drawSlice(data.image); }
};
function updateOutputs(r, n) {
  const pulled=Number.isFinite(r.pullTime);
  $("pull-time").textContent=formatDuration(r.pullTime); $("pull-temp").textContent=pulled?`${r.pullTemp.toFixed(1)}°C at pull-time cold spot`:"target not reached";
  $("peak-temp").textContent=pulled?`${r.peakTemp.toFixed(1)}°C`:"—"; $("peak-time").textContent=pulled?`at ${formatDuration(r.peakTime)}`:"including carryover";
  $("carryover").textContent=pulled?`+${Math.max(0,r.carryover).toFixed(1)}°C`:"—"; $("peak-after").textContent=pulled?`${formatDuration(r.peakTime-r.pullTime)} after pull`:"—";
  $("time-step").textContent=`${r.dt.toFixed(2)} s`; $("grid-size").textContent=`${n} × ${n} × ${n}`; $("pasteurization").textContent=`${r.pasteurization < 60 ? r.pasteurization.toFixed(1)+' s' : (r.pasteurization/60).toFixed(1)+' min'}`;
}
function setupCanvas(canvas) { const dpr=devicePixelRatio||1, rect=canvas.getBoundingClientRect(), w=Math.max(300,Math.round(rect.width*dpr)),h=Math.max(180,Math.round(rect.height*dpr));if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h}return {ctx:canvas.getContext("2d"),w,h,dpr}; }
function drawCurve() {
  const {ctx,w,h}=setupCanvas(curveCanvas), pad={l:54,r:18,t:18,b:38};ctx.clearRect(0,0,w,h);ctx.fillStyle="#fff";ctx.fillRect(0,0,w,h);
  const all=[...current,...prior];if(!all.length){ctx.fillStyle="#89918c";ctx.font=`12px ${getComputedStyle(document.body).fontFamily}`;ctx.textAlign="center";ctx.fillText("Run a prediction to stream the curve",w/2,h/2);return}
  const xmax=Math.max(...all.map(d=>d.time),1), ymin=Math.min(...all.map(d=>d.cold),target)-5, ymax=Math.max(...all.map(d=>d.probe),target)+8;
  const X=t=>pad.l+t/xmax*(w-pad.l-pad.r),Y=t=>h-pad.b-(t-ymin)/(ymax-ymin)*(h-pad.t-pad.b);
  ctx.strokeStyle="#e3e7e3";ctx.fillStyle="#748078";ctx.font=`${10*(devicePixelRatio||1)}px DM Mono`;ctx.textAlign="right";for(let i=0;i<=4;i++){let v=ymin+(ymax-ymin)*i/4,y=Y(v);ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(w-pad.r,y);ctx.stroke();ctx.fillText(`${v.toFixed(0)}°`,pad.l-8,y+3)}
  ctx.textAlign="center";for(let i=0;i<=4;i++){let t=xmax*i/4;ctx.fillText(`${Math.round(t/60)}m`,X(t),h-12)}
  ctx.setLineDash([5,5]);ctx.strokeStyle="#d69d4488";ctx.beginPath();ctx.moveTo(pad.l,Y(target));ctx.lineTo(w-pad.r,Y(target));ctx.stroke();ctx.setLineDash([]);
  const line=(data,key,color,width,dash=[])=>{if(!data.length)return;ctx.strokeStyle=color;ctx.lineWidth=width;ctx.setLineDash(dash);ctx.beginPath();data.forEach((d,i)=>(i?ctx.lineTo(X(d.time),Y(d[key])):ctx.moveTo(X(d.time),Y(d[key]))));ctx.stroke();ctx.setLineDash([])};
  line(prior,"cold","#aab1ac",1,[5,5]);line(current,"probe","#17695b",2);line(current,"cold","#d45536",2.5);
}
function drawEmptySlice(){const {ctx,w,h}=setupCanvas(sliceCanvas);ctx.fillStyle="#171b19";ctx.fillRect(0,0,w,h);ctx.fillStyle="#9ca69f";ctx.textAlign="center";ctx.font="12px DM Mono";ctx.fillText("temperature field pending",w/2,h/2)}
function drawSlice(image){const {ctx,w,h}=setupCanvas(sliceCanvas),{n,z,values,mask}=image;const off=document.createElement("canvas");off.width=n;off.height=n;const oc=off.getContext("2d"),pixels=oc.createImageData(n,n);for(let i=0;i<n*n;i++){const c=mask[i]?tempColor(values[i],target):[0,0,0,0];pixels.data.set(c,i*4)}oc.putImageData(pixels,0,0);ctx.clearRect(0,0,w,h);ctx.imageSmoothingEnabled=false;ctx.drawImage(off,0,0,w,h);ctx.strokeStyle="#fff";ctx.lineWidth=Math.max(1,devicePixelRatio||1);ctx.globalAlpha=.8;const cell=w/n;for(let y=0;y<n-1;y++)for(let x=0;x<n-1;x++){let i=y*n+x;if(!mask[i])continue;let a=values[i]>=target,b=values[i+1]>=target,c=values[i+n]>=target;if(a!==b){ctx.beginPath();ctx.moveTo((x+1)*cell,y*cell);ctx.lineTo((x+1)*cell,(y+1)*cell);ctx.stroke()}if(a!==c){ctx.beginPath();ctx.moveTo(x*cell,(y+1)*cell);ctx.lineTo((x+1)*cell,(y+1)*cell);ctx.stroke()}}ctx.globalAlpha=1;$("slice-label").textContent=`plane ${z+1} of ${n}`;}
addEventListener("resize",()=>{drawCurve();if(latestImage)drawSlice(latestImage);else drawEmptySlice()});drawCurve();drawEmptySlice();
