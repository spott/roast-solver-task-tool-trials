//! Dependency-free Rust port of the browser solver kernel.
//!
//! The C ABI deliberately avoids a JS glue generator: a worker can instantiate
//! the `.wasm`, call `rs_init`/`rs_step`, and view linear memory directly.

use std::f32::consts::PI;

const RHO: f32 = 1060.0;
const CP: f32 = 3500.0;
const K: f32 = 0.47;
const SIGMA: f32 = 5.670_374_4e-8;
const HFG: f32 = 2.30e6;

#[derive(Clone)]
pub struct Core {
    pub n: usize,
    pub h: f32,
    pub temp: Vec<f32>,
    pub inside: Vec<u8>,
    area: Vec<f32>,
    pan: Vec<u8>,
    moisture: Vec<f32>,
    lethality_s: Vec<f32>,
    oven: f32,
    ambient: f32,
    h_roast: f32,
    covered: bool,
    emissivity: f32,
    pub time_s: f32,
    pub phase: u8,
}

impl Core {
    pub fn new(n: usize, preset: u32, mass: f32, initial: f32, oven: f32,
               fan: bool, covered: bool, moisture: f32) -> Self {
        let n = n.clamp(18, 96);
        let volume = mass / RHO;
        let ratios: (f32,f32,f32,f32) = match preset {
            1 => (1.25, 0.83, 0.78, 2.0), // bird body surrogate for interactive core
            2 => (1.45, 0.95, 0.30, 5.0),
            3 => (1.15, 0.86, 0.82, 2.3),
            _ => (1.35, 0.88, 0.78, 2.6),
        };
        // ellipsoid-equivalent axes. Superellipse exponent changes volume only
        // modestly; this normalization makes weight error visible but bounded.
        let scale = (volume / ((4.0/3.0)*PI*ratios.0*ratios.1*ratios.2)).cbrt();
        let (a,b,c) = (ratios.0*scale, ratios.1*scale, ratios.2*scale);
        let h = 2.0*a/(n as f32-6.0);
        let len = n*n*n;
        let mut inside = vec![0; len];
        let idx = |x:usize,y:usize,z:usize| (x*n+y)*n+z;
        for x in 0..n { for y in 0..n { for z in 0..n {
            let xx = ((x as f32+0.5)-n as f32/2.0)*h/a;
            let yy = ((y as f32+0.5)-n as f32/2.0)*h/b;
            let zz = ((z as f32+0.5)-n as f32/2.0)*h/c;
            let p = ratios.3;
            if xx.abs().powf(p)+yy.abs().powf(p)+zz.abs().powf(p) <= 1.0 {
                inside[idx(x,y,z)] = 1;
            }
        }}}
        let mut area = vec![0.0; len]; let mut pan = vec![0; len];
        let dirs = [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)];
        for x in 1..n-1 { for y in 1..n-1 { for z in 1..n-1 {
            let i=idx(x,y,z); if inside[i]==0 {continue}
            let mut v=[0f32;3];
            for &(dx,dy,dz) in &dirs {
                let j=idx((x as isize+dx) as usize,(y as isize+dy) as usize,(z as isize+dz) as usize);
                if inside[j]==0 { v[0]+=dx as f32; v[1]+=dy as f32; v[2]+=dz as f32; }
            }
            area[i]=h*h*(v[0]*v[0]+v[1]*v[1]+v[2]*v[2]).sqrt();
            if area[i]>0.0 && v[2] < -0.4 && (z as f32)<n as f32/2.0 {pan[i]=1}
        }}}
        let mut wet=vec![0.0;len];
        for i in 0..len {if area[i]>0.0 {wet[i]=moisture}}
        Self { n,h,temp:vec![initial;len],inside,area,pan,moisture:wet,
            lethality_s:vec![0.0;len],oven,ambient:22.0,h_roast:if fan {20.0}else{10.0},
            covered,emissivity:0.90,time_s:0.0,phase:0 }
    }
    #[inline] fn index(&self,x:usize,y:usize,z:usize)->usize {(x*self.n+y)*self.n+z}
    pub fn stable_dt(&self)->f32 { 0.80*self.h*self.h*RHO*CP/(6.0*K) }
    pub fn step(&mut self, requested_dt:f32) -> f32 {
        let dt=requested_dt.min(self.stable_dt()).max(0.01);
        let mut power=vec![0f32;self.temp.len()];
        for axis in 0..3 { for x in 0..self.n { for y in 0..self.n { for z in 0..self.n {
            let (xx,yy,zz)=match axis {0=>(x+1,y,z),1=>(x,y+1,z),_=>(x,y,z+1)};
            if xx>=self.n||yy>=self.n||zz>=self.n {continue}
            let i=self.index(x,y,z); let j=self.index(xx,yy,zz);
            if self.inside[i]!=0 && self.inside[j]!=0 {
                let q=K*self.h*(self.temp[j]-self.temp[i]); power[i]+=q; power[j]-=q;
            }
        }}}}
        let (env,h,eps,rh)=if self.phase==0 {(self.oven,self.h_roast,self.emissivity,if self.covered{0.98}else{0.15})}
                             else {(self.ambient,7.0,self.emissivity,0.5)};
        for i in 0..self.temp.len() { if self.area[i]>0.0 && self.pan[i]==0 {
            let ts=self.temp[i];
            let conv=h*(env-ts);
            let rad=eps*SIGMA*((env+273.15).powi(4)-(ts+273.15).powi(4));
            let ps=611.21*((18.678-ts/234.5)*(ts/(257.14+ts))).exp();
            let rho_v=ps/(461.52*(ts+273.15));
            let mut mf=h/(1.10*1007.0*0.9f32.powf(2.0/3.0))*rho_v*(1.0-rh);
            if self.covered {mf*=0.05}
            mf=mf.min(self.moisture[i]/dt).max(0.0);
            self.moisture[i]=(self.moisture[i]-mf*dt).max(0.0);
            power[i]+=(conv+rad-HFG*mf)*self.area[i];
        }}
        let cap=RHO*CP*self.h*self.h*self.h;
        for i in 0..self.temp.len() {if self.inside[i]!=0 {
            self.temp[i]+=dt*power[i]/cap;
            self.lethality_s[i]+=dt*10f32.powf((self.temp[i]-70.0)/7.0);
        }}
        self.time_s+=dt; dt
    }
    pub fn coldest(&self)->f32 {self.temp.iter().zip(&self.inside).filter(|(_,m)|**m!=0).map(|(t,_)|*t).fold(f32::INFINITY,f32::min)}
    pub fn hottest(&self)->f32 {self.temp.iter().zip(&self.inside).filter(|(_,m)|**m!=0).map(|(t,_)|*t).fold(f32::NEG_INFINITY,f32::max)}
    pub fn probe(&self)->f32 { self.temp[self.index(self.n/2,self.n/2,self.n/2)] }
    pub fn min_lethality_minutes(&self)->f32 {self.lethality_s.iter().zip(&self.inside).filter(|(_,m)|**m!=0).map(|(v,_)|*v/60.0).fold(f32::INFINITY,f32::min)}
}

/// Tiny deterministic diffusion oracle shared with Python fixture generation.
pub fn golden_box_centres(n:usize, steps:&[usize])->Vec<f32>{
    let mut t=vec![0f32;n*n*n]; let at=|x,y,z|(x*n+y)*n+z;
    for x in 0..n {for y in 0..n {for z in 0..n {if x==0||y==0||z==0||x==n-1||y==n-1||z==n-1{t[at(x,y,z)]=1.0}}}}
    let max=*steps.iter().max().unwrap_or(&0); let mut out=Vec::new();
    for s in 0..=max {
        if steps.contains(&s){out.push(t[at(n/2,n/2,n/2)])}
        if s==max {break} let old=t.clone();
        for x in 1..n-1{for y in 1..n-1{for z in 1..n-1{let i=at(x,y,z);t[i]=old[i]+0.1*(old[at(x+1,y,z)]+old[at(x-1,y,z)]+old[at(x,y+1,z)]+old[at(x,y-1,z)]+old[at(x,y,z+1)]+old[at(x,y,z-1)]-6.0*old[i]);}}}
    } out
}

static mut STATE: Option<Core> = None;
#[no_mangle] pub extern "C" fn rs_init(n:u32,preset:u32,mass:f32,initial:f32,oven:f32,fan:u32,covered:u32,moisture:f32){unsafe{STATE=Some(Core::new(n as usize,preset,mass,initial,oven,fan!=0,covered!=0,moisture));}}
#[no_mangle] pub extern "C" fn rs_step(dt:f32,steps:u32)->f32{unsafe{let s=STATE.as_mut().unwrap();for _ in 0..steps{s.step(dt);}s.time_s}}
#[no_mangle] pub extern "C" fn rs_set_phase(phase:u32){unsafe{STATE.as_mut().unwrap().phase=phase as u8;}}
#[no_mangle] pub extern "C" fn rs_time()->f32{unsafe{STATE.as_ref().unwrap().time_s}}
#[no_mangle] pub extern "C" fn rs_coldest()->f32{unsafe{STATE.as_ref().unwrap().coldest()}}
#[no_mangle] pub extern "C" fn rs_hottest()->f32{unsafe{STATE.as_ref().unwrap().hottest()}}
#[no_mangle] pub extern "C" fn rs_probe()->f32{unsafe{STATE.as_ref().unwrap().probe()}}
#[no_mangle] pub extern "C" fn rs_pasteurization()->f32{unsafe{STATE.as_ref().unwrap().min_lethality_minutes()}}
#[no_mangle] pub extern "C" fn rs_temperature_ptr()->*const f32{unsafe{STATE.as_ref().unwrap().temp.as_ptr()}}
#[no_mangle] pub extern "C" fn rs_mask_ptr()->*const u8{unsafe{STATE.as_ref().unwrap().inside.as_ptr()}}
#[no_mangle] pub extern "C" fn rs_len()->u32{unsafe{STATE.as_ref().unwrap().temp.len() as u32}}
#[no_mangle] pub extern "C" fn rs_n()->u32{unsafe{STATE.as_ref().unwrap().n as u32}}
