//! Rust/WASM port of the NumPy reference solver.
//!
//! The browser ABI is intentionally a small numeric C interface: `roast_start`,
//! repeated `roast_advance`, then pointer/length getters into WASM memory. This
//! avoids a JS glue dependency and permits progressive worker execution.

const SIGMA: f64 = 5.670_374_419e-8;
const HFG: f64 = 2.30e6;

#[derive(Clone, Copy, Debug)]
pub struct Props {
    pub rho: f64,
    pub cp: f64,
    pub k: f64,
    pub alpha: f64,
}

pub fn food_properties(temp_c: f64) -> Props {
    let t = temp_c.clamp(-5., 130.);
    let cp_w = 4176.2 - 9.0864e-2 * t + 5.4731e-3 * t * t;
    let cp_p = 2008.2 + 1.2089 * t - 1.3129e-3 * t * t;
    let cp_f = 1984.2 + 1.4733 * t - 4.8008e-3 * t * t;
    let cp_a = 1092.6 + 1.8896 * t - 3.6817e-3 * t * t;
    let cp = 0.75 * cp_w + 0.20 * cp_p + 0.04 * cp_f + 0.01 * cp_a;
    let rw = 997.18 + 3.1439e-3 * t - 3.7574e-3 * t * t;
    let rp = 1329.9 - 0.5184 * t;
    let rf = 925.59 - 0.41757 * t;
    let ra = 2423.8 - 0.28063 * t;
    let rho = 1. / (0.75 / rw + 0.20 / rp + 0.04 / rf + 0.01 / ra);
    let kw = 0.57109 + 1.7625e-3 * t - 6.7036e-6 * t * t;
    let kp = 0.17881 + 1.1958e-3 * t - 2.7178e-6 * t * t;
    let kf = 0.18071 - 2.7604e-3 * t - 1.7749e-7 * t * t;
    let ka = 0.32962 + 1.4011e-3 * t - 2.9069e-6 * t * t;
    let k = 1.08 * (0.75 * kw + 0.20 * kp + 0.04 * kf + 0.01 * ka);
    Props {
        rho,
        cp,
        k,
        alpha: k / (rho * cp),
    }
}

pub fn radiation_coefficient(surface_c: f64, wall_c: f64, emissivity: f64) -> f64 {
    let ts = surface_c + 273.15;
    let tw = wall_c + 273.15;
    emissivity * SIGMA * (tw + ts) * (tw * tw + ts * ts)
}
fn saturation_pressure(t: f64) -> f64 {
    let x = t.clamp(-20., 100.);
    611.21 * ((18.678 - x / 234.5) * (x / (257.14 + x))).exp()
}
fn vapor_fraction(t: f64, rh: f64) -> f64 {
    let pv = (rh * saturation_pressure(t)).min(0.98 * 101325.);
    let ratio = 0.62198 * pv / (101325. - pv);
    ratio / (1. + ratio)
}

fn ellipsoid(x: f64, y: f64, z: f64, r: (f64, f64, f64), p: f64) -> f64 {
    let q =
        ((x.abs() / r.0).powf(p) + (y.abs() / r.1).powf(p) + (z.abs() / r.2).powf(p)).powf(1. / p);
    (q - 1.) * r.0.min(r.1).min(r.2)
}
fn capsule(x: f64, y: f64, z: f64, a: (f64, f64, f64), b: (f64, f64, f64), r: f64) -> f64 {
    let ba = (b.0 - a.0, b.1 - a.1, b.2 - a.2);
    let pa = (x - a.0, y - a.1, z - a.2);
    let h = ((pa.0 * ba.0 + pa.1 * ba.1 + pa.2 * ba.2) / (ba.0 * ba.0 + ba.1 * ba.1 + ba.2 * ba.2))
        .clamp(0., 1.);
    ((pa.0 - h * ba.0).powi(2) + (pa.1 - h * ba.1).powi(2) + (pa.2 - h * ba.2).powi(2)).sqrt() - r
}
fn smooth_union(a: f64, b: f64, k: f64) -> f64 {
    let h = (0.5 + 0.5 * (b - a) / k).clamp(0., 1.);
    b * (1. - h) + a * h - k * h * (1. - h)
}
fn rounded_box(x: f64, y: f64, z: f64, half: (f64, f64, f64), r: f64) -> f64 {
    let q = (
        x.abs() - (half.0 - r),
        y.abs() - (half.1 - r),
        z.abs() - (half.2 - r),
    );
    let outside = q.0.max(0.).powi(2) + q.1.max(0.).powi(2) + q.2.max(0.).powi(2);
    outside.sqrt() + q.0.max(q.1).max(q.2).min(0.) - r
}
fn sdf(preset: u32, x: f64, y: f64, z: f64) -> f64 {
    match preset {
        0 => ellipsoid(x, y, z, (1., 0.68, 0.62), 2.6),
        1 => {
            let body = ellipsoid(x, y, z, (1., 0.66, 0.63), 2.);
            let mut o = smooth_union(
                body,
                capsule(x, y, z, (-0.35, -0.42, -0.18), (-0.92, -0.67, -0.42), 0.20),
                0.10,
            );
            o = smooth_union(
                o,
                capsule(x, y, z, (-0.35, 0.42, -0.18), (-0.92, 0.67, -0.42), 0.20),
                0.10,
            );
            o = smooth_union(
                o,
                capsule(x, y, z, (0.12, -0.55, 0.08), (-0.20, -0.90, -0.02), 0.12),
                0.07,
            );
            o = smooth_union(
                o,
                capsule(x, y, z, (0.12, 0.55, 0.08), (-0.20, 0.90, -0.02), 0.12),
                0.07,
            );
            o.max(-ellipsoid(x + 0.30, y, z + 0.03, (0.48, 0.30, 0.31), 2.))
        }
        2 => rounded_box(x, y, z, (1., 0.70, 0.30), 0.16),
        _ => ellipsoid(x + 0.13 * z, y, z, (1., 0.72, 0.72), 2.15) + 0.10 * x,
    }
}
const UNIT_VOLUMES: [f64; 4] = [
    2.198797825938411,
    1.757326654462008,
    1.6338044027879008,
    2.4224915739454262,
];

#[derive(Clone, Copy)]
pub struct Config {
    pub preset: u32,
    pub resolution: usize,
    pub mass_kg: f64,
    pub oven_c: f64,
    pub initial_c: f64,
    pub target_c: f64,
    pub max_cook_s: f64,
    pub rest_s: f64,
    pub convection: bool,
    pub covered: bool,
    pub foil: bool,
}
impl Default for Config {
    fn default() -> Self {
        Self {
            preset: 0,
            resolution: 24,
            mass_kg: 1.5,
            oven_c: 180.,
            initial_c: 5.,
            target_c: 60.,
            max_cook_s: 18000.,
            rest_s: 1800.,
            convection: false,
            covered: false,
            foil: false,
        }
    }
}

pub struct Simulation {
    cfg: Config,
    pub n: usize,
    pub h: f64,
    phi: Vec<f32>,
    pub inside: Vec<u8>,
    area: Vec<f32>,
    pan: Vec<u8>,
    pub temp: Vec<f32>,
    next: Vec<f32>,
    moisture: Vec<f32>,
    power: Vec<f64>,
    pub history: Vec<f32>,
    pub time: f64,
    pub dt: f64,
    next_output: f64,
    pub pulled: bool,
    pub complete: bool,
    pull_time: f64,
    center: usize,
    carry: usize,
    pull_probe: f64,
    peak: f64,
    peak_time: f64,
    pasteurization: f64,
}
fn idx(n: usize, z: usize, y: usize, x: usize) -> usize {
    (z * n + y) * n + x
}

impl Simulation {
    pub fn new(cfg: Config) -> Self {
        let n = cfg.resolution.clamp(8, 64) + 6;
        let target = cfg.mass_kg / 1060.;
        let mut scale = (target / UNIT_VOLUMES[cfg.preset.min(3) as usize]).cbrt();
        let extent = if cfg.preset == 1 { 1.38 } else { 1.18 };
        let mut h = 2. * extent * scale / cfg.resolution as f64;
        let build = |scale: f64, h: f64| {
            let mut phi = vec![0f32; n * n * n];
            let mut inside = vec![0u8; n * n * n];
            for z in 0..n {
                for y in 0..n {
                    for x in 0..n {
                        let i = idx(n, z, y, x);
                        let xx = (-(n as f64) / 2. + x as f64 + 0.5) * h / scale;
                        let yy = (-(n as f64) / 2. + y as f64 + 0.5) * h / scale;
                        let zz = (-(n as f64) / 2. + z as f64 + 0.5) * h / scale;
                        phi[i] = (scale * sdf(cfg.preset, xx, yy, zz)) as f32;
                        inside[i] = (phi[i] <= 0.) as u8;
                    }
                }
            }
            (phi, inside)
        };
        let (_, first) = build(scale, h);
        let count = first.iter().map(|&v| v as usize).sum::<usize>();
        let correction = (target / (count as f64 * h.powi(3))).cbrt();
        scale *= correction;
        h *= correction;
        let (phi, inside) = build(scale, h);
        let mut normals = vec![(0f64, 0f64, 0f64); n * n * n];
        for z in 0..n {
            for y in 0..n {
                for x in 0..n {
                    let i = idx(n, z, y, x);
                    let xm = idx(n, z, y, x.saturating_sub(1));
                    let xp = idx(n, z, y, (x + 1).min(n - 1));
                    let ym = idx(n, z, y.saturating_sub(1), x);
                    let yp = idx(n, z, (y + 1).min(n - 1), x);
                    let zm = idx(n, z.saturating_sub(1), y, x);
                    let zp = idx(n, (z + 1).min(n - 1), y, x);
                    let gx = (phi[xp] - phi[xm]) as f64;
                    let gy = (phi[yp] - phi[ym]) as f64;
                    let gz = (phi[zp] - phi[zm]) as f64;
                    let m = (gx * gx + gy * gy + gz * gz).sqrt().max(1e-15);
                    normals[i] = (gx / m, gy / m, gz / m);
                }
            }
        }
        let mut area = vec![0f32; n * n * n];
        for z in 0..n {
            for y in 0..n {
                for x in 0..n {
                    let a = idx(n, z, y, x);
                    for b in [
                        if x + 1 < n {
                            Some(idx(n, z, y, x + 1))
                        } else {
                            None
                        },
                        if y + 1 < n {
                            Some(idx(n, z, y + 1, x))
                        } else {
                            None
                        },
                        if z + 1 < n {
                            Some(idx(n, z + 1, y, x))
                        } else {
                            None
                        },
                    ]
                    .into_iter()
                    .flatten()
                    {
                        if inside[a] != inside[b] {
                            let i = if inside[a] > 0 { a } else { b };
                            let no = normals[i];
                            let l1 = (no.0.abs() + no.1.abs() + no.2.abs()).max(0.25);
                            area[i] += (h * h / l1) as f32;
                        }
                    }
                }
            }
        }
        let bottom = (0..n)
            .find(|&z| (0..n * n).any(|j| inside[z * n * n + j] > 0))
            .unwrap_or(0);
        let mut pan = vec![0u8; n * n * n];
        for z in 0..n {
            for y in 0..n {
                for x in 0..n {
                    let i = idx(n, z, y, x);
                    if area[i] > 0. && z <= bottom + 1 && normals[i].2 < -0.45 {
                        pan[i] = 1
                    }
                }
            }
        }
        let mut temp = vec![f32::NAN; n * n * n];
        let mut moisture = vec![0.; n * n * n];
        for i in 0..temp.len() {
            if inside[i] > 0 {
                temp[i] = cfg.initial_c as f32
            }
            if area[i] > 0. {
                moisture[i] = 0.30
            }
        }
        let center = (0..temp.len())
            .filter(|&i| inside[i] > 0)
            .min_by_key(|&i| {
                let z = i / (n * n);
                let y = (i / n) % n;
                let x = i % n;
                let dz = z as isize - n as isize / 2;
                let dy = y as isize - n as isize / 2;
                let dx = x as isize - n as isize / 2;
                dx * dx + dy * dy + dz * dz
            })
            .unwrap();
        let dt = 0.72 * h * h / (6. * food_properties(cfg.initial_c).alpha);
        let len = temp.len();
        let initial = cfg.initial_c as f32;
        let mut s = Self {
            cfg,
            n,
            h,
            phi,
            inside,
            area,
            pan,
            temp,
            next: vec![f32::NAN; len],
            moisture,
            power: vec![0.; len],
            history: vec![],
            time: 0.,
            dt,
            next_output: 0.,
            pulled: false,
            complete: false,
            pull_time: f64::NAN,
            center,
            carry: center,
            pull_probe: initial as f64,
            peak: initial as f64,
            peak_time: 0.,
            pasteurization: 0.,
        };
        s.record();
        s
    }
    fn record(&mut self) {
        let cold = self
            .temp
            .iter()
            .enumerate()
            .filter(|(i, _)| self.inside[*i] > 0)
            .map(|(_, v)| *v)
            .fold(f32::INFINITY, f32::min);
        self.history
            .extend_from_slice(&[self.time as f32, cold, self.temp[self.center]]);
    }
    fn do_step(&mut self, dt: f64) {
        self.power.fill(0.);
        let n = self.n;
        let props: Vec<Props> = self
            .temp
            .iter()
            .enumerate()
            .map(|(i, &t)| food_properties(if self.inside[i] > 0 { t as f64 } else { 0. }))
            .collect();
        for z in 0..n {
            for y in 0..n {
                for x in 0..n {
                    let a = idx(n, z, y, x);
                    if self.inside[a] == 0 {
                        continue;
                    }
                    for b in [
                        if x + 1 < n {
                            Some(idx(n, z, y, x + 1))
                        } else {
                            None
                        },
                        if y + 1 < n {
                            Some(idx(n, z, y + 1, x))
                        } else {
                            None
                        },
                        if z + 1 < n {
                            Some(idx(n, z + 1, y, x))
                        } else {
                            None
                        },
                    ]
                    .into_iter()
                    .flatten()
                    {
                        if self.inside[b] > 0 {
                            let k = 2. * props[a].k * props[b].k / (props[a].k + props[b].k);
                            let q = k * self.h * (self.temp[b] - self.temp[a]) as f64;
                            self.power[a] += q;
                            self.power[b] -= q;
                        }
                    }
                }
            }
        }
        let rest = self.pulled;
        for i in 0..self.temp.len() {
            if self.area[i] <= 0. {
                continue;
            }
            if !rest && self.pan[i] > 0 {
                continue;
            }
            let tc = self.temp[i] as f64;
            let (env, hc, eps, evscale) = if rest {
                (
                    22.,
                    if self.cfg.foil { 5. } else { 8. },
                    if self.cfg.foil { 0.30 } else { 0.90 },
                    if self.cfg.foil { 0.15 } else { 0.35 },
                )
            } else {
                (
                    self.cfg.oven_c,
                    if self.cfg.convection { 20. } else { 10. },
                    0.90,
                    if self.cfg.covered { 0.02 } else { 1. },
                )
            };
            let hr = radiation_coefficient(tc, env, eps);
            let hh = hc + hr;
            let teq = env;
            let hm = hc / (1.15 * 1007. * 0.90f64.powf(2. / 3.));
            let mp =
                1.15 * hm * (vapor_fraction(tc.min(99.), 1.) - vapor_fraction(22., 0.20)).max(0.);
            let available = hh * (teq - tc.max(55.)).max(0.);
            let mut latent = (HFG * mp).min(available) * evscale;
            let wet = self.moisture[i] > 1e-12;
            if wet {
                latent = latent.min(self.moisture[i] as f64 * HFG / dt)
            } else {
                latent *= 0.06
            }
            let d = (-self.phi[i] as f64).clamp(0.12 * self.h, 0.85 * self.h);
            let kd = props[i].k / d;
            let ts = (hh * teq + kd * tc - latent) / (hh + kd);
            let q = kd * (ts - tc);
            self.power[i] += q * self.area[i] as f64;
            let qlat = (hc * (env - ts) + hr * (env - ts) - q).max(0.);
            if wet {
                self.moisture[i] = (self.moisture[i] as f64 - qlat * dt / HFG).max(0.) as f32;
                if self.moisture[i] < 1e-12 {
                    self.moisture[i] = 0.
                }
            }
        }
        for i in 0..self.temp.len() {
            if self.inside[i] > 0 {
                let cap = props[i].rho * props[i].cp * self.h.powi(3);
                self.next[i] = (self.temp[i] as f64 + dt * self.power[i] / cap) as f32
            } else {
                self.next[i] = f32::NAN
            }
        }
        std::mem::swap(&mut self.temp, &mut self.next);
        self.time += dt;
        let (ci, cold) = self
            .temp
            .iter()
            .enumerate()
            .filter(|(i, _)| self.inside[*i] > 0)
            .min_by(|a, b| a.1.partial_cmp(b.1).unwrap())
            .map(|(i, v)| (i, *v as f64))
            .unwrap();
        self.pasteurization += 10f64.powf((cold - 70.) / 10.) * dt;
        if !self.pulled && cold >= self.cfg.target_c {
            self.pulled = true;
            self.pull_time = self.time;
            self.carry = ci;
            self.pull_probe = cold;
            self.peak = cold;
            self.peak_time = self.time;
            self.next_output = self.time;
        }
        if self.pulled && self.temp[self.carry] as f64 > self.peak {
            self.peak = self.temp[self.carry] as f64;
            self.peak_time = self.time;
        }
        let limit = if self.pulled {
            self.pull_time + self.cfg.rest_s
        } else {
            self.cfg.max_cook_s
        };
        if self.time + 1e-7 >= limit {
            self.complete = true
        }
        if self.time + 1e-7 >= self.next_output {
            self.record();
            self.next_output += 30.;
        }
    }
    pub fn advance(&mut self, max_steps: usize) -> bool {
        for _ in 0..max_steps {
            if self.complete {
                break;
            }
            let limit = if self.pulled {
                self.pull_time + self.cfg.rest_s
            } else {
                self.cfg.max_cook_s
            };
            let d = self.dt.min(limit - self.time);
            if d <= 1e-9 {
                self.complete = true;
                break;
            }
            self.do_step(d);
        }
        if self.complete
            && self
                .history
                .last()
                .map(|v| (*v as f64 - self.temp[self.center] as f64).abs() > 1e-5)
                .unwrap_or(true)
        {
            self.record()
        }
        self.complete
    }
    pub fn result(&self, code: u32) -> f64 {
        match code {
            0 => self.pull_time,
            1 => self.pull_probe,
            2 => self.peak,
            3 => self.peak_time,
            4 => self.peak - self.pull_probe,
            5 => self.pasteurization,
            6 => self.time,
            7 => self.dt,
            _ => f64::NAN,
        }
    }
}

pub fn dirichlet_step(t: &[f32], n: usize, alpha: f64, h: f64, dt: f64) -> Vec<f32> {
    assert!(alpha * dt / (h * h) <= 1. / 6. + 1e-12);
    let r = (alpha * dt / (h * h)) as f32;
    let mut o = vec![0.; t.len()];
    for z in 1..n - 1 {
        for y in 1..n - 1 {
            for x in 1..n - 1 {
                let i = idx(n, z, y, x);
                o[i] = t[i]
                    + r * (t[i + 1] + t[i - 1] + t[i + n] + t[i - n] + t[i + n * n] + t[i - n * n]
                        - 6. * t[i]);
            }
        }
    }
    o
}

static mut STATE: *mut Simulation = std::ptr::null_mut();
#[no_mangle]
pub extern "C" fn roast_start(
    preset: u32,
    resolution: u32,
    mass: f64,
    oven: f64,
    initial: f64,
    target: f64,
    max_cook: f64,
    rest: f64,
    convection: u32,
    covered: u32,
    foil: u32,
) -> i32 {
    unsafe {
        if !STATE.is_null() {
            drop(Box::from_raw(STATE));
        }
        STATE = Box::into_raw(Box::new(Simulation::new(Config {
            preset,
            resolution: resolution as usize,
            mass_kg: mass,
            oven_c: oven,
            initial_c: initial,
            target_c: target,
            max_cook_s: max_cook,
            rest_s: rest,
            convection: convection != 0,
            covered: covered != 0,
            foil: foil != 0,
        })));
    }
    0
}
#[no_mangle]
pub extern "C" fn roast_advance(steps: u32) -> i32 {
    unsafe {
        if STATE.is_null() {
            return -1;
        }
        if (*STATE).advance(steps as usize) {
            1
        } else {
            0
        }
    }
}
#[no_mangle]
pub extern "C" fn roast_progress() -> f64 {
    unsafe {
        if STATE.is_null() {
            0.
        } else {
            let s = &*STATE;
            let end = if s.pulled {
                s.pull_time + s.cfg.rest_s
            } else {
                s.cfg.max_cook_s
            };
            (s.time / end).clamp(0., 1.)
        }
    }
}
#[no_mangle]
pub extern "C" fn roast_result(code: u32) -> f64 {
    unsafe {
        if STATE.is_null() {
            f64::NAN
        } else {
            (*STATE).result(code)
        }
    }
}
#[no_mangle]
pub extern "C" fn roast_grid_n() -> u32 {
    unsafe {
        if STATE.is_null() {
            0
        } else {
            (*STATE).n as u32
        }
    }
}
#[no_mangle]
pub extern "C" fn roast_temperature_ptr() -> *const f32 {
    unsafe {
        if STATE.is_null() {
            std::ptr::null()
        } else {
            (*STATE).temp.as_ptr()
        }
    }
}
#[no_mangle]
pub extern "C" fn roast_occupancy_ptr() -> *const u8 {
    unsafe {
        if STATE.is_null() {
            std::ptr::null()
        } else {
            (*STATE).inside.as_ptr()
        }
    }
}
#[no_mangle]
pub extern "C" fn roast_history_ptr() -> *const f32 {
    unsafe {
        if STATE.is_null() {
            std::ptr::null()
        } else {
            (*STATE).history.as_ptr()
        }
    }
}
#[no_mangle]
pub extern "C" fn roast_history_len() -> u32 {
    unsafe {
        if STATE.is_null() {
            0
        } else {
            (*STATE).history.len() as u32
        }
    }
}
#[no_mangle]
pub extern "C" fn roast_free() {
    unsafe {
        if !STATE.is_null() {
            drop(Box::from_raw(STATE));
            STATE = std::ptr::null_mut();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn golden_properties_and_radiation() {
        let rows = [
            (
                5.,
                1052.2965830758776,
                3625.4316349,
                0.5203300294277999,
                1.3638952300692707e-7,
            ),
            (
                60.,
                1036.399471027754,
                3652.1798256,
                0.5856787696032,
                1.5473200235767707e-7,
            ),
            (
                100.,
                1012.9316245556962,
                3685.36396,
                0.61019223912,
                1.6345799399351282e-7,
            ),
        ];
        for (t, r, c, k, a) in rows {
            let p = food_properties(t);
            assert!((p.rho - r).abs() < 1e-9);
            assert!((p.cp - c).abs() < 1e-8);
            assert!((p.k - k).abs() < 1e-12);
            assert!((p.alpha - a).abs() < 1e-16)
        }
        assert!((radiation_coefficient(60., 180., 0.9) - 12.693698591837109).abs() < 1e-10);
    }
    #[test]
    fn python_generated_fixture_matches() {
        let fixture = include_str!("../../fixtures/core_golden_v1.csv");
        for line in fixture.lines().filter(|l| !l.starts_with('#')) {
            let p: Vec<&str> = line.split(',').collect();
            match p[0] {
                "PROP" => {
                    let v: Vec<f64> = p[1..].iter().map(|x| x.parse().unwrap()).collect();
                    let q = food_properties(v[0]);
                    assert!((q.rho - v[1]).abs() < 1e-9);
                    assert!((q.cp - v[2]).abs() < 1e-8);
                    assert!((q.k - v[3]).abs() < 1e-12);
                    assert!((q.alpha - v[4]).abs() < 1e-16)
                }
                "RAD" => {
                    let v: Vec<f64> = p[1..].iter().map(|x| x.parse().unwrap()).collect();
                    assert!((radiation_coefficient(v[0], v[1], v[2]) - v[3]).abs() < 1e-12)
                }
                "STENCIL" => {
                    let v: Vec<f64> = p[1..].iter().map(|x| x.parse().unwrap()).collect();
                    let n = v[0] as usize;
                    let mut t = vec![0f32; n * n * n];
                    for z in 1..n - 1 {
                        for y in 1..n - 1 {
                            for x in 1..n - 1 {
                                let i = idx(n, z, y, x);
                                t[i] = (i % 7) as f32
                            }
                        }
                    }
                    for _ in 0..v[4] as usize {
                        t = dirichlet_step(&t, n, v[1], v[2], v[3])
                    }
                    assert!((t[62] as f64 - v[5]).abs() < 2e-6);
                    assert!((t.iter().sum::<f32>() as f64 - v[6]).abs() < 2e-5)
                }
                "INTEGRATION" => {
                    let v: Vec<f64> = p[1..].iter().map(|x| x.parse().unwrap()).collect();
                    let mut s = Simulation::new(Config {
                        preset: v[0] as u32,
                        resolution: v[1] as usize,
                        mass_kg: v[2],
                        oven_c: v[3],
                        initial_c: v[4],
                        target_c: v[5],
                        max_cook_s: v[6],
                        rest_s: v[7],
                        ..Config::default()
                    });
                    while !s.advance(50) {}
                    assert!((s.result(0) - v[8]).abs() < 1e-8);
                    assert!((s.result(4) - v[9]).abs() < 0.01);
                    assert!((s.result(5) - v[10]).abs() / v[10] < 0.005)
                }
                _ => panic!("unknown fixture row"),
            }
        }
    }
    #[test]
    fn integration_progresses_and_carries_over() {
        let mut s = Simulation::new(Config {
            resolution: 12,
            mass_kg: 0.25,
            initial_c: 20.,
            target_c: 30.,
            max_cook_s: 4000.,
            rest_s: 300.,
            ..Config::default()
        });
        while !s.advance(50) {}
        assert!(s.pulled);
        assert!(s.peak > s.pull_probe);
        assert!(s.history.len() > 12);
        assert!(s.pasteurization >= 0.);
    }
}
