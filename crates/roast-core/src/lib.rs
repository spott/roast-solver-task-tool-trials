//! WASM implementation of the NumPy reference kernel.
//! The formulas, units, lagged properties, Crofton boundary area and half-cell
//! Robin resistance intentionally mirror `roast_solver/`.
use wasm_bindgen::prelude::*;

const SIGMA:f64=5.670374419e-8;
const HFG:f64=2.257e6;
fn cp(t:f64)->f64 { let x=t.clamp(-10.,120.); 0.75*(4176.2-0.0909*x+0.005473*x*x)+0.20*(2008.2+1.2089*x-0.0013129*x*x)+0.05*(1984.2+1.4733*x-0.0048008*x*x) }
fn rho(t:f64)->f64 {1060./(1.+3e-4*(t.clamp(-10.,120.)-20.))}
fn k(t:f64)->f64 { let x=t.clamp(-10.,120.); 0.75*(0.57109+0.0017625*x-6.7036e-6*x*x)+0.20*(0.17881+0.0011958*x-2.7178e-6*x*x)+0.05*(0.18071-0.00027604*x-1.7749e-7*x*x) }
fn vapor(t:f64)->f64 {let x=t.clamp(-20.,100.); let p=610.94*(17.625*x/(x+243.04)).exp();p/(461.5*(x+273.15))}
fn lrad(e:f64,wall:f64,surf:f64)->f64 {let a=wall+273.15;let b=surf+273.15;e*SIGMA*(a+b)*(a*a+b*b)}

fn ellipsoid(x:f64,y:f64,z:f64,a:f64,b:f64,c:f64,p:f64)->f64 {(((x/a).abs().powf(p)+(y/b).abs().powf(p)+(z/c).abs().powf(p)).powf(1./p)-1.)*a.min(b).min(c)}
fn rounded_box(x:f64,y:f64,z:f64)->f64 {let r=0.12;let q=[x.abs()-1.+r,y.abs()-0.68+r,z.abs()-0.27+r];let out=(q[0].max(0.).powi(2)+q[1].max(0.).powi(2)+q[2].max(0.).powi(2)).sqrt();out+q[0].max(q[1].max(q[2])).min(0.)-r}
fn capsule(x:f64,y:f64,z:f64,p:[f64;3],q:[f64;3],r:f64)->f64 {let v=[q[0]-p[0],q[1]-p[1],q[2]-p[2]];let u=[x-p[0],y-p[1],z-p[2]];let a=((u[0]*v[0]+u[1]*v[1]+u[2]*v[2])/(v[0]*v[0]+v[1]*v[1]+v[2]*v[2])).clamp(0.,1.);((u[0]-a*v[0]).powi(2)+(u[1]-a*v[1]).powi(2)+(u[2]-a*v[2]).powi(2)).sqrt()-r}
fn smin(a:f64,b:f64,r:f64)->f64 {let h=(0.5+0.5*(b-a)/r).clamp(0.,1.);(1.-h)*b+h*a-r*h*(1.-h)}
fn sdf(kind:&str,x:f64,y:f64,z:f64)->f64 {match kind {
 "slab"=>rounded_box(x,y,z),
 "ham"=>smin(ellipsoid(x+0.12,y,z,0.88,0.73,0.72,2.),ellipsoid(x-0.56,y,z,0.65,0.52,0.53,2.),0.18),
 "bird"=>{let mut o=ellipsoid(x,y,z,0.92,0.63,0.58,2.);o=smin(o,capsule(x,y,z,[-0.25,0.42,-0.12],[0.68,0.63,-0.25],0.23),0.10);o=smin(o,capsule(x,y,z,[-0.25,-0.42,-0.12],[0.68,-0.63,-0.25],0.23),0.10);o=smin(o,capsule(x,y,z,[-0.18,0.48,0.18],[0.30,0.84,0.10],0.13),0.06);o=smin(o,capsule(x,y,z,[-0.18,-0.48,0.18],[0.30,-0.84,0.10],0.13),0.06);o.max(-ellipsoid(x-0.12,y,z,0.43,0.30,0.30,2.))},
 _=>ellipsoid(x,y,z,1.,0.68,0.58,2.5)}}
fn unit_volume(kind:&str,n:usize)->f64 { // exact represented binary volume
 let d=2.76/(n as f64-1.);let mut count=0;for i in 0..n {for j in 0..n {for l in 0..n {if sdf(kind,-1.38+i as f64*d,-1.38+j as f64*d,-1.38+l as f64*d)<=0.{count+=1}}}}count as f64*d.powi(3)}

#[wasm_bindgen]
pub struct WasmSolver {n:usize,dx:f64,inside:Vec<bool>,area:Vec<f64>,pan:Vec<bool>,temp:Vec<f64>,surface:Vec<f64>,moisture:Vec<f64>,power:Vec<f64>,time:f64,pull:f64,max_cook:f64,oven:f64,target:f64,h:f64,covered:bool,phase:u8,probe_idx:usize,rest_seconds:f64,next_sample:f64,dose:f64,times:Vec<f64>,cold:Vec<f64>,probes:Vec<f64>,doses:Vec<f64>}

#[wasm_bindgen]
impl WasmSolver {
 #[wasm_bindgen(constructor)]
 pub fn new(preset:&str,mass_kg:f64,oven_c:f64,initial_c:f64,target_c:f64,convection:bool,covered:bool,rest_minutes:f64,resolution:usize)->WasmSolver {
  let n=resolution.clamp(18,64);let scale=(mass_kg/1060./unit_volume(preset,n)).cbrt();let extent=1.38*scale;let dx=2.*extent/(n as f64-1.);let len=n*n*n;
  let mut phi=vec![0.;len];let mut inside=vec![false;len];let at=|i,j,l| (i*n+j)*n+l;
  for i in 0..n {for j in 0..n {for l in 0..n {let x=-extent+i as f64*dx;let y=-extent+j as f64*dx;let z=-extent+l as f64*dx;let q=scale*sdf(preset,x/scale,y/scale,z/scale);let p=at(i,j,l);phi[p]=q;inside[p]=q<=0.;}}}
  let mut normals=vec![[0.;3];len];for i in 1..n-1 {for j in 1..n-1 {for l in 1..n-1 {let p=at(i,j,l);let g=[phi[at(i+1,j,l)]-phi[at(i-1,j,l)],phi[at(i,j+1,l)]-phi[at(i,j-1,l)],phi[at(i,j,l+1)]-phi[at(i,j,l-1)]];let r=(g[0]*g[0]+g[1]*g[1]+g[2]*g[2]).sqrt()+1e-30;normals[p]=[g[0]/r,g[1]/r,g[2]/r];}}}
  let mut area=vec![0.;len];for i in 0..n {for j in 0..n {for l in 0..n {let p=at(i,j,l);if !inside[p]{continue}let l1=(normals[p][0].abs()+normals[p][1].abs()+normals[p][2].abs()).max(0.35);for (di,dj,dl) in [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)] {let a=i as isize+di;let b=j as isize+dj;let c=l as isize+dl;if a>=0&&b>=0&&c>=0&&a<n as isize&&b<n as isize&&c<n as isize&&!inside[at(a as usize,b as usize,c as usize)] {area[p]+=dx*dx/l1;}}}}}
  let mut pan=vec![false;len];for i in 0..n {for j in 0..n {for l in 0..n {let p=at(i,j,l);let z=-extent+l as f64*dx;pan[p]=area[p]>0.&&normals[p][2] < -0.55&&z < -0.25*scale;}}}
  let moisture=area.iter().map(|a|if *a>0.{0.25}else{0.}).collect();
  WasmSolver{n,dx,inside,area,pan,temp:vec![initial_c;len],surface:vec![initial_c;len],moisture,power:vec![0.;len],time:0.,pull:-1.,max_cook:8.*3600.,oven:oven_c,target:target_c,h:if convection{20.}else{10.},covered,phase:0,probe_idx:usize::MAX,rest_seconds:rest_minutes*60.,next_sample:0.,dose:0.,times:vec![],cold:vec![],probes:vec![],doses:vec![]}
 }
 pub fn step_chunk(&mut self,max_steps:usize)->bool {for _ in 0..max_steps {if self.done(){break}self.step();}self.done()}
 pub fn progress(&self)->f64 {let finish=if self.phase==1{self.pull+self.rest_seconds}else{self.max_cook};(self.time/finish).clamp(0.,1.)}
 pub fn phase(&self)->String {if self.phase==0{"Cooking".into()}else{"Resting".into()}}
 pub fn times(&self)->Vec<f64>{self.times.clone()} pub fn coldest(&self)->Vec<f64>{self.cold.clone()} pub fn probe(&self)->Vec<f64>{self.probes.clone()} pub fn pasteurization(&self)->Vec<f64>{self.doses.clone()}
 pub fn pull_time(&self)->f64{self.pull} pub fn dx_m(&self)->f64{self.dx}
 pub fn slice(&self)->Vec<f32>{let l=self.n/2;let mut v=Vec::with_capacity(self.n*self.n);for i in 0..self.n{for j in 0..self.n{let p=(i*self.n+j)*self.n+l;v.push(if self.inside[p]{self.temp[p] as f32}else{f32::NAN})}}v}
 pub fn resolution(&self)->usize{self.n}
}
impl WasmSolver {
 fn done(&self)->bool {(self.phase==0&&self.time>=self.max_cook)||(self.phase==1&&self.time>=self.pull+self.rest_seconds)}
 fn step(&mut self){let max_alpha=self.temp.iter().zip(self.inside.iter()).filter(|(_,m)|**m).map(|(t,_)|k(*t)/(rho(*t)*cp(*t))).fold(0.,f64::max);let mut dt=(0.82*self.dx*self.dx/(6.*max_alpha)).min(5.);if self.phase==1{dt=dt.min(self.pull+self.rest_seconds-self.time)}self.power.fill(0.);let n=self.n;let at=|i,j,l|(i*n+j)*n+l;
  for i in 0..n {for j in 0..n {for l in 0..n {let p=at(i,j,l);if !self.inside[p]{continue}for (di,dj,dl) in [(1,0,0),(0,1,0),(0,0,1)] {let (a,b,c)=(i+di,j+dj,l+dl);if a<n&&b<n&&c<n {let q=at(a,b,c);if self.inside[q]{let kk=2.*k(self.temp[p])*k(self.temp[q])/(k(self.temp[p])+k(self.temp[q]));let w=kk*self.dx*(self.temp[q]-self.temp[p]);self.power[p]+=w;self.power[q]-=w;}}}}}}
  let (air,wall,h,e,rh) = if self.phase==0 {(self.oven,self.oven,self.h,0.90,0.10)} else {(22.,22.,7.,0.85,0.45)};
  for p in 0..self.temp.len(){if self.area[p]==0.||self.pan[p]{continue}let wet=self.moisture[p]>1e-9;let hc=if wet{h}else{0.72*h};let hr=lrad(e,wall,self.surface[p]);let mut evap=0.;if !self.covered&&wet{let hm=hc/(1.20*1005.*0.90f64.powf(2./3.));let md=(hm*(vapor(self.surface[p])-rh*vapor(air.min(30.0))).max(0.)).min(self.moisture[p]/dt);self.moisture[p]=(self.moisture[p]-md*dt).max(0.);evap=md*HFG;}let q=(hc*air+hr*wall-(hc+hr)*self.temp[p]-evap)/(1.+(hc+hr)*0.5*self.dx/k(self.temp[p]));self.surface[p]=self.temp[p]+q*0.5*self.dx/k(self.temp[p]);self.power[p]+=q*self.area[p];}
  for p in 0..self.temp.len(){if self.inside[p]{self.temp[p]+=dt*self.power[p]/(rho(self.temp[p])*cp(self.temp[p])*self.dx.powi(3));}}
  self.time+=dt;let (cold_idx,cold)=self.temp.iter().zip(self.inside.iter()).enumerate().filter(|(_,(_,m))|**m).map(|(i,(t,_))|(i,*t)).min_by(|a,b|a.1.total_cmp(&b.1)).unwrap();self.dose+=10f64.powf((cold-70.)/7.)*dt/60.;if self.phase==0&&cold>=self.target {self.phase=1;self.pull=self.time;self.probe_idx=cold_idx;}
  if self.time>=self.next_sample||self.done(){let probe=if self.probe_idx==usize::MAX{cold}else{self.temp[self.probe_idx]};self.times.push(self.time);self.cold.push(cold);self.probes.push(probe);self.doses.push(self.dose);self.next_sample+=60.;}
 }
}

#[cfg(test)] mod tests {use super::*;
 #[test] fn property_goldens_match_python(){assert!((cp(40.)-3648.654208).abs()<1e-3);assert!((k(40.)-0.5260761048).abs()<1e-6);assert!((rho(40.)-1053.6779).abs()<1e-3);}
 #[test] fn robin_kernel_matches_python_golden(){let hr=lrad(0.9,120.,20.);let q=(10.*120.+hr*120.-(10.+hr)*20.)/(1.+(10.+hr)*0.5*0.003/k(20.));let ts=20.+q*0.5*0.003/k(20.);assert!((hr-8.423455170613305).abs()<1e-11);assert!((q-1746.18473650121).abs()<1e-9);assert!((ts-25.219475916412456).abs()<1e-11);}
 #[test] fn progressive_solver_is_finite(){let mut s=WasmSolver::new("roast",0.8,160.,10.,25.,false,true,0.1,18);for _ in 0..100{s.step_chunk(10);if s.done(){break}}assert!(s.times.len()>2);assert!(s.cold.iter().all(|x|x.is_finite()));assert!(s.cold.last().unwrap()>s.cold.first().unwrap());}
}
