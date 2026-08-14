/* Progressive simulation worker. WASM is preferred; the dependency-free JS
   port keeps static previews functional when the optional wasm artifact was not
   built. Both use the same constant-property interactive kernel. */
let cancelled=false;
self.onmessage=async ({data})=>{
  if(data.type==='cancel'){cancelled=true;return}
  if(data.type!=='run')return;
  cancelled=false;
  try { await run(data.config); } catch(error) { self.postMessage({type:'error',message:error.stack||String(error)}); }
};

async function wasmEngine(c){
  try {
    const response=await fetch('./wasm/roast_solver_core.wasm');
    if(!response.ok)return null;
    const {instance}=await WebAssembly.instantiateStreaming(response,{});
    const e=instance.exports, presets={roast:0,bird:1,slab:2,ham:3};
    e.rs_init(c.resolution,presets[c.preset]||0,c.mass,c.initial,c.oven,c.fan?1:0,c.covered?1:0,.25);
    return {name:'Rust/WASM SIMD', step:(dt,n)=>e.rs_step(dt,n), phase:p=>e.rs_set_phase(p),
      time:()=>e.rs_time(), cold:()=>e.rs_coldest(), probe:()=>e.rs_probe(), hot:()=>e.rs_hottest(), pasteurization:()=>e.rs_pasteurization(),
      field:()=>({n:e.rs_n(),temperature:new Float32Array(e.memory.buffer,e.rs_temperature_ptr(),e.rs_len()).slice(),
        mask:new Uint8Array(e.memory.buffer,e.rs_mask_ptr(),e.rs_len()).slice()})};
  } catch(e){ console.warn('WASM unavailable, using JS core',e); return null; }
}

function jsEngine(c){
  // Mirrors rust-core/src/lib.rs. Kept intentionally straightforward as a
  // readable fallback and regression aid, not as a second product model.
  const n=Math.min(c.resolution,34), len=n*n*n, inside=new Uint8Array(len), area=new Float32Array(len), pan=new Uint8Array(len);
  let temp=new Float32Array(len).fill(c.initial); const wet=new Float32Array(len), lethal=new Float32Array(len);
  const rho=1060,cp=3500,k=.47,sigma=5.670374419e-8,hfg=2.30e6;
  const ratios={roast:[1.35,.88,.78,2.6],bird:[1.25,.83,.78,2],slab:[1.45,.95,.30,5],ham:[1.15,.86,.82,2.3]}[c.preset];
  const volume=c.mass/rho, scale=Math.cbrt(volume/(4/3*Math.PI*ratios[0]*ratios[1]*ratios[2]));
  const [a,b,cc]=ratios.slice(0,3).map(x=>x*scale), p=ratios[3], dx=2*a/(n-6), at=(x,y,z)=>(x*n+y)*n+z;
  for(let x=0;x<n;x++)for(let y=0;y<n;y++)for(let z=0;z<n;z++){
    const xx=((x+.5)-n/2)*dx/a, yy=((y+.5)-n/2)*dx/b, zz=((z+.5)-n/2)*dx/cc;
    if(Math.abs(xx)**p+Math.abs(yy)**p+Math.abs(zz)**p<=1)inside[at(x,y,z)]=1;
  }
  const dirs=[[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]];
  for(let x=1;x<n-1;x++)for(let y=1;y<n-1;y++)for(let z=1;z<n-1;z++){let i=at(x,y,z);if(!inside[i])continue;let v=[0,0,0];for(const d of dirs)if(!inside[at(x+d[0],y+d[1],z+d[2])])v=v.map((q,j)=>q+d[j]);area[i]=dx*dx*Math.hypot(...v);if(area[i])wet[i]=.25;if(area[i]&&v[2]<-.4&&z<n/2)pan[i]=1;}
  let time=0,phase=0,power=new Float32Array(len), next=new Float32Array(len), stable=.8*dx*dx*rho*cp/(6*k);
  function step(requested,count){for(let qn=0;qn<count;qn++){const dt=Math.min(requested,stable);power.fill(0);
    for(let x=0;x<n;x++)for(let y=0;y<n;y++)for(let z=0;z<n;z++){let i=at(x,y,z);if(!inside[i])continue;for(const [ox,oy,oz] of [[1,0,0],[0,1,0],[0,0,1]]){if(x+ox>=n||y+oy>=n||z+oz>=n)continue;let j=at(x+ox,y+oy,z+oz);if(inside[j]){let heat=k*dx*(temp[j]-temp[i]);power[i]+=heat;power[j]-=heat;}}}
    const env=phase?22:c.oven,h=phase?7:(c.fan?20:10),rh=phase?.5:(c.covered?.98:.15);
    for(let i=0;i<len;i++)if(area[i]&&!pan[i]){let ts=temp[i],conv=h*(env-ts),rad=.9*sigma*((env+273.15)**4-(ts+273.15)**4),ps=611.21*Math.exp((18.678-ts/234.5)*(ts/(257.14+ts))),rv=ps/(461.52*(ts+273.15)),mf=h/(1.1*1007*.9**(2/3))*rv*(1-rh);if(c.covered)mf*=.05;mf=Math.max(0,Math.min(mf,wet[i]/dt));wet[i]=Math.max(0,wet[i]-mf*dt);power[i]+=(conv+rad-hfg*mf)*area[i];}
    const cap=rho*cp*dx**3;for(let i=0;i<len;i++)if(inside[i]){next[i]=temp[i]+dt*power[i]/cap;lethal[i]+=dt*10**((next[i]-70)/7)}else next[i]=temp[i];[temp,next]=[next,temp];time+=dt;}return time;}
  const minOf=a=>{let v=Infinity;for(let i=0;i<len;i++)if(inside[i])v=Math.min(v,a[i]);return v};
  return {name:'JavaScript fallback',step,phase:p=>phase=p,time:()=>time,cold:()=>minOf(temp),probe:()=>temp[at(n>>1,n>>1,n>>1)],hot:()=>{let v=-Infinity;for(let i=0;i<len;i++)if(inside[i])v=Math.max(v,temp[i]);return v},pasteurization:()=>minOf(lethal)/60,field:()=>({n,temperature:temp.slice(),mask:inside.slice()})};
}

async function run(c){
  const engine=await wasmEngine(c)||jsEngine(c); self.postMessage({type:'engine',name:engine.name});
  const curve=[],maxRoast=8*3600, batch=8,dt=8; let nextReport=0,pull=null;
  while(engine.time()<maxRoast&&!cancelled){engine.step(dt,batch);const t=engine.time(),core=engine.cold();if(t>=nextReport){curve.push({t,core,probe:engine.probe(),pasteurization:engine.pasteurization(),phase:'roast'});self.postMessage({type:'progress',point:curve.at(-1),fraction:Math.min(1,t/maxRoast)});nextReport=t+60;}if(core>=c.target){pull=t;break}await new Promise(r=>setTimeout(r,0));}
  let peak=engine.cold(),peakTime=0;
  if(pull!==null){engine.phase(1);const end=engine.time()+c.rest*60;nextReport=engine.time();while(engine.time()<end&&!cancelled){engine.step(Math.min(dt,(end-engine.time())/batch),batch);let core=engine.cold();if(core>peak){peak=core;peakTime=engine.time()-pull}if(engine.time()>=nextReport){curve.push({t:engine.time(),core,probe:engine.probe(),pasteurization:engine.pasteurization(),phase:'rest'});self.postMessage({type:'progress',point:curve.at(-1),fraction:1});nextReport=engine.time()+60;}await new Promise(r=>setTimeout(r,0));}}
  if(cancelled)return;const field=engine.field();self.postMessage({type:'done',curve,pull,peak,peakTime,pasteurization:engine.pasteurization(),...field},[field.temperature.buffer,field.mask.buffer]);
}
