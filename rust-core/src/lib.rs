//! Dependency-free Rust/WASM port of the NumPy reference kernel.
//!
//! The browser ABI at the bottom deliberately uses scalar arguments and raw
//! pointers, so the static site needs no generated JavaScript glue.

const SIGMA: f32 = 5.670_374_4e-8;
const H_FG: f32 = 2_257_000.0;
const RV: f32 = 461.5;

#[derive(Clone, Copy, Debug)]
pub struct Config {
    pub preset: u32,
    pub mass_kg: f32,
    pub oven_c: f32,
    pub initial_c: f32,
    pub target_c: f32,
    pub convection: bool,
    pub covered: bool,
    pub n: usize,
    pub max_cook_s: f32,
    pub rest_s: f32,
}

#[derive(Clone, Copy, Debug)]
pub struct Properties {
    pub rho: f32,
    pub cp: f32,
    pub k: f32,
}

pub fn properties(t: f32) -> Properties {
    let x = [0.75_f32, 0.20, 0.03, 0.0, 0.02];
    let cp = [
        1000.0 * (4.1762 - 9.0864e-5 * t + 5.4731e-6 * t * t),
        1000.0 * (2.0082 + 1.2089e-3 * t - 1.3129e-6 * t * t),
        1000.0 * (1.9842 + 1.4733e-3 * t - 4.8008e-6 * t * t),
        1000.0 * (1.5488 + 1.9625e-3 * t - 5.9399e-6 * t * t),
        1000.0 * (1.0926 + 1.8896e-3 * t - 3.6817e-6 * t * t),
    ];
    let k = [
        0.57109 + 1.7625e-3 * t - 6.7036e-6 * t * t,
        0.17881 + 1.1958e-3 * t - 2.7178e-6 * t * t,
        0.18071 - 2.7604e-4 * t - 1.7749e-7 * t * t,
        0.20141 + 1.3874e-3 * t - 4.3312e-6 * t * t,
        0.32962 + 1.4011e-3 * t - 2.9069e-6 * t * t,
    ];
    let density = [
        997.18 + 3.1439e-3 * t - 3.7574e-3 * t * t,
        1329.9 - 0.5184 * t,
        925.59 - 0.41757 * t,
        1599.1 - 0.31046 * t,
        2423.8 - 0.28063 * t,
    ];
    let mut cp_mix = 0.0;
    let mut k_mix = 0.0;
    let mut specific_volume = 0.0;
    for i in 0..5 {
        cp_mix += x[i] * cp[i];
        k_mix += x[i] * k[i];
        specific_volume += x[i] / density[i];
    }
    Properties {
        rho: (1.0 / specific_volume).clamp(1050.0, 1080.0),
        cp: cp_mix.clamp(3300.0, 3600.0),
        k: k_mix.clamp(0.45, 0.50),
    }
}

fn smooth_min(a: f32, b: f32, r: f32) -> f32 {
    let h = (0.5 + 0.5 * (b - a) / r).clamp(0.0, 1.0);
    b * (1.0 - h) + a * h - r * h * (1.0 - h)
}

fn ellipsoid(x: f32, y: f32, z: f32, a: f32, b: f32, c: f32) -> f32 {
    let k0 = ((x / a).powi(2) + (y / b).powi(2) + (z / c).powi(2)).sqrt();
    let k1 = ((x / (a * a)).powi(2) + (y / (b * b)).powi(2) + (z / (c * c)).powi(2)).sqrt();
    if k1 > 1e-12 {
        k0 * (k0 - 1.0) / k1
    } else {
        -a.min(b).min(c)
    }
}

fn capsule(p: [f32; 3], a: [f32; 3], b: [f32; 3], radius: f32) -> f32 {
    let pa = [p[0] - a[0], p[1] - a[1], p[2] - a[2]];
    let ba = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
    let dot = pa[0] * ba[0] + pa[1] * ba[1] + pa[2] * ba[2];
    let len2 = ba[0] * ba[0] + ba[1] * ba[1] + ba[2] * ba[2];
    let h = (dot / len2).clamp(0.0, 1.0);
    ((pa[0] - h * ba[0]).powi(2) + (pa[1] - h * ba[1]).powi(2) + (pa[2] - h * ba[2]).powi(2)).sqrt()
        - radius
}

fn rounded_box(x: f32, y: f32, z: f32, half: [f32; 3], radius: f32) -> f32 {
    let q = [
        x.abs() - (half[0] - radius),
        y.abs() - (half[1] - radius),
        z.abs() - (half[2] - radius),
    ];
    let outside = q.iter().map(|v| v.max(0.0).powi(2)).sum::<f32>().sqrt();
    outside + q[0].max(q[1]).max(q[2]).min(0.0) - radius
}

fn base_sdf(preset: u32, x: f32, y: f32, z: f32) -> f32 {
    match preset {
        0 => {
            let p = 2.5;
            let r = ((x / 1.45).abs().powf(p) + y.abs().powf(p) + (z / 0.72).abs().powf(p))
                .powf(1.0 / p);
            (r - 1.0) * 0.72
        }
        1 => {
            let body = ellipsoid(x, y, z, 1.18, 0.78, 0.72);
            let breast = ellipsoid(x - 0.28, y, z - 0.12, 0.92, 0.73, 0.60);
            let mut outer = smooth_min(body, breast, 0.16);
            let parts = [
                capsule([x, y, z], [-0.55, 0.45, -0.24], [-1.20, 0.66, -0.42], 0.22),
                capsule(
                    [x, y, z],
                    [-0.55, -0.45, -0.24],
                    [-1.20, -0.66, -0.42],
                    0.22,
                ),
                capsule([x, y, z], [0.20, 0.61, 0.05], [-0.45, 1.02, -0.08], 0.13),
                capsule([x, y, z], [0.20, -0.61, 0.05], [-0.45, -1.02, -0.08], 0.13),
            ];
            for part in parts {
                outer = smooth_min(outer, part, 0.09);
            }
            let cavity = ellipsoid(x + 0.22, y, z + 0.06, 0.56, 0.38, 0.34);
            outer.max(-cavity)
        }
        2 => rounded_box(x, y, z, [1.45, 0.92, 0.42], 0.13),
        _ => {
            let taper = (1.0 - 0.18 * (x + 0.2)).clamp(0.62, 1.2);
            ellipsoid(x, y / taper, z / taper, 1.25, 0.90, 0.88)
        }
    }
}

fn base_volume(preset: u32) -> f32 {
    // Deterministic values from the Python midpoint-volume fixture.
    match preset {
        0 => 5.294_745,
        1 => 2.934_553_6,
        2 => 4.296_086,
        _ => 3.895_207_6,
    }
}

fn vapor_density(t: f32) -> f32 {
    let tc = t.clamp(-20.0, 99.5);
    let pressure = 133.322_37 * 10_f32.powf(8.07131 - 1730.63 / (233.426 + tc));
    pressure / (RV * (tc + 273.15))
}

pub struct Simulation {
    pub config: Config,
    pub n: usize,
    pub h: f32,
    pub temperature: Vec<f32>,
    phi: Vec<f32>,
    inside: Vec<u8>,
    area: Vec<f32>,
    pan: Vec<u8>,
    moisture: Vec<f32>,
    surface_temperature: Vec<f32>,
    power: Vec<f64>,
    conductivity: Vec<f32>,
    capacity: Vec<f32>,
    pub dt: f32,
    pub time_s: f32,
    pub phase_time_s: f32,
    pub phase: u32,
    pub pull_time_s: f32,
    pub pull_probe_c: f32,
    pub peak_probe_c: f32,
    pub peak_after_pull_s: f32,
    pub pasteurization_minutes: f32,
    pub evaporated_kg: f32,
    probe: usize,
}

impl Simulation {
    pub fn new(mut config: Config) -> Self {
        config.n = config.n.clamp(15, 65) | 1;
        let n = config.n;
        let count = n * n * n;
        let volume = config.mass_kg / 1060.0;
        let scale = (volume / base_volume(config.preset)).cbrt();
        let extent = 1.72 * scale;
        let h = 2.0 * extent / (n as f32 - 1.0 - 5.0);
        let axis_extent = h * (n as f32 - 1.0) * 0.5;
        let mut phi = vec![0.0; count];
        let idx = |i: usize, j: usize, k: usize| (i * n + j) * n + k;
        for i in 0..n {
            for j in 0..n {
                for k in 0..n {
                    let x = -axis_extent + i as f32 * h;
                    let y = -axis_extent + j as f32 * h;
                    let z = -axis_extent + k as f32 * h;
                    phi[idx(i, j, k)] =
                        scale * base_sdf(config.preset, x / scale, y / scale, z / scale);
                }
            }
        }
        let inside: Vec<u8> = phi.iter().map(|p| (*p <= 0.0) as u8).collect();
        let epsilon = 1.5 * h;
        let mut area = vec![0.0; count];
        let mut nz = vec![0.0; count];
        let derivative = |i: usize, j: usize, k: usize, axis: usize| -> f32 {
            let (a, b) = match axis {
                0 => (
                    idx(i.saturating_sub(1), j, k),
                    idx((i + 1).min(n - 1), j, k),
                ),
                1 => (
                    idx(i, j.saturating_sub(1), k),
                    idx(i, (j + 1).min(n - 1), k),
                ),
                _ => (
                    idx(i, j, k.saturating_sub(1)),
                    idx(i, j, (k + 1).min(n - 1)),
                ),
            };
            let span = if match axis {
                0 => i,
                1 => j,
                _ => k,
            } == 0
                || match axis {
                    0 => i,
                    1 => j,
                    _ => k,
                } == n - 1
            {
                h
            } else {
                2.0 * h
            };
            (phi[b] - phi[a]) / span
        };
        let mut min_surface_z = 0.0_f32;
        for i in 0..n {
            for j in 0..n {
                for k in 0..n {
                    let p = idx(i, j, k);
                    let gx = derivative(i, j, k, 0);
                    let gy = derivative(i, j, k, 1);
                    let gz = derivative(i, j, k, 2);
                    let mag = (gx * gx + gy * gy + gz * gz).sqrt().max(1e-12);
                    nz[p] = gz / mag;
                    if phi[p] <= 0.0 && phi[p] >= -epsilon {
                        area[p] = 2.0 * (1.0 + phi[p] / epsilon) / epsilon * mag * h * h * h;
                        let z = -axis_extent + k as f32 * h;
                        min_surface_z = min_surface_z.min(z);
                    }
                }
            }
        }
        let mut pan = vec![0_u8; count];
        for i in 0..n {
            for j in 0..n {
                for k in 0..n {
                    let p = idx(i, j, k);
                    let z = -axis_extent + k as f32 * h;
                    pan[p] =
                        (area[p] > 0.0 && nz[p] < -0.55 && z <= min_surface_z + 1.75 * h) as u8;
                }
            }
        }
        let mut temperature = vec![f32::NAN; count];
        let mut probe = 0;
        let mut deepest = f32::INFINITY;
        for p in 0..count {
            if inside[p] != 0 {
                temperature[p] = config.initial_c;
                if phi[p] < deepest {
                    deepest = phi[p];
                    probe = p;
                }
            }
        }
        let alpha_bound = 1.45e-7_f32;
        let dt = 0.72 * h * h / (6.0 * alpha_bound);
        Self {
            config,
            n,
            h,
            temperature,
            phi,
            inside,
            area,
            pan,
            moisture: vec![0.25; count],
            surface_temperature: vec![config.initial_c; count],
            power: vec![0.0; count],
            conductivity: vec![0.0; count],
            capacity: vec![1.0; count],
            dt,
            time_s: 0.0,
            phase_time_s: 0.0,
            phase: 0,
            pull_time_s: -1.0,
            pull_probe_c: f32::NAN,
            peak_probe_c: config.initial_c,
            peak_after_pull_s: 0.0,
            pasteurization_minutes: 0.0,
            evaporated_kg: 0.0,
            probe,
        }
    }

    fn index(&self, i: usize, j: usize, k: usize) -> usize {
        (i * self.n + j) * self.n + k
    }
    pub fn coldest(&self) -> f32 {
        self.temperature
            .iter()
            .zip(&self.inside)
            .filter(|(_, m)| **m != 0)
            .map(|(t, _)| *t)
            .fold(f32::INFINITY, f32::min)
    }
    pub fn hottest(&self) -> f32 {
        self.temperature
            .iter()
            .zip(&self.inside)
            .filter(|(_, m)| **m != 0)
            .map(|(t, _)| *t)
            .fold(f32::NEG_INFINITY, f32::max)
    }
    pub fn probe_temperature(&self) -> f32 {
        self.temperature[self.probe]
    }
    pub fn moisture_fraction(&self) -> f32 {
        let remaining: f32 = self
            .moisture
            .iter()
            .zip(&self.area)
            .map(|(m, a)| m * a)
            .sum();
        let initial: f32 = self.area.iter().sum::<f32>() * 0.25;
        if initial > 0.0 {
            remaining / initial
        } else {
            0.0
        }
    }

    pub fn step(&mut self) {
        if self.phase == 2 {
            return;
        }
        let remaining = if self.phase == 0 {
            self.config.max_cook_s - self.phase_time_s
        } else {
            self.config.rest_s - self.phase_time_s
        };
        let dt = self.dt.min(remaining);
        if dt <= 1e-7 {
            self.phase = 2;
            return;
        }
        let count = self.temperature.len();
        self.power.fill(0.0);
        for p in 0..count {
            if self.inside[p] != 0 {
                let pr = properties(self.temperature[p]);
                self.conductivity[p] = pr.k;
                self.capacity[p] = pr.rho * pr.cp * self.h.powi(3);
            }
        }
        for i in 0..self.n {
            for j in 0..self.n {
                for k in 0..self.n {
                    let p = self.index(i, j, k);
                    if self.inside[p] == 0 {
                        continue;
                    }
                    if i + 1 < self.n {
                        self.face(p, self.index(i + 1, j, k));
                    }
                    if j + 1 < self.n {
                        self.face(p, self.index(i, j + 1, k));
                    }
                    if k + 1 < self.n {
                        self.face(p, self.index(i, j, k + 1));
                    }
                }
            }
        }
        let (ambient, wall, hbase, emissivity, rh, covered) = if self.phase == 0 {
            (
                self.config.oven_c,
                self.config.oven_c,
                if self.config.convection { 20.0 } else { 10.0 },
                0.90,
                if self.config.covered { 0.98 } else { 0.15 },
                self.config.covered,
            )
        } else {
            (22.0, 22.0, 7.0, 0.90, 0.45, false)
        };
        for p in 0..count {
            if self.area[p] <= 0.0 || self.pan[p] != 0 {
                continue;
            }
            let tc = self.temperature[p];
            let k = self.conductivity[p];
            let ts0 = self.surface_temperature[p];
            let tsk = (ts0 + 273.15).clamp(200.0, 500.0);
            let twk = wall + 273.15;
            let hrad = emissivity * SIGMA * (twk + tsk) * (twk * twk + tsk * tsk);
            let hconv = hbase * if self.moisture[p] <= 1e-8 { 1.15 } else { 1.0 };
            let conductance = k / (-self.phi[p]).max(0.25 * self.h);
            let dry_ts =
                (conductance * tc + hconv * ambient + hrad * wall) / (conductance + hconv + hrad);
            let hm = hconv / (1.18 * 1006.0 * 0.90_f32.powf(2.0 / 3.0));
            let mut mf =
                hm * (vapor_density(dry_ts) - rh * vapor_density(ambient.min(30.0))).max(0.0);
            if covered {
                mf *= 0.03;
            }
            if self.moisture[p] <= 0.0 {
                mf = 0.0;
            }
            mf = mf.min(self.moisture[p] / dt);
            let latent = H_FG * mf;
            let ts = ((conductance * tc + hconv * ambient + hrad * wall - latent)
                / (conductance + hconv + hrad))
                .clamp(
                    ambient.min(wall).min(tc) - 25.0,
                    ambient.max(wall).max(tc) + 5.0,
                );
            let conv = hconv * (ambient - ts);
            let rad = emissivity * SIGMA * ((wall + 273.15).powi(4) - (ts + 273.15).powi(4));
            self.power[p] += ((conv + rad - latent) * self.area[p]) as f64;
            let removed = (mf * dt).min(self.moisture[p]);
            self.moisture[p] -= removed;
            self.evaporated_kg += removed * self.area[p];
            self.surface_temperature[p] = ts;
        }
        for p in 0..count {
            if self.inside[p] != 0 {
                self.temperature[p] += (dt as f64 * self.power[p] / self.capacity[p] as f64) as f32;
            }
        }
        self.time_s += dt;
        self.phase_time_s += dt;
        let cold = self.coldest();
        self.pasteurization_minutes +=
            dt / 60.0 * 10_f32.powf(((cold - 70.0) / 10.0).clamp(-12.0, 4.0));
        let probe = self.probe_temperature();
        if self.pull_time_s < 0.0 {
            self.peak_probe_c = self.peak_probe_c.max(probe);
        } else if probe >= self.peak_probe_c {
            self.peak_probe_c = probe;
            self.peak_after_pull_s = self.time_s - self.pull_time_s;
        }
        if self.phase == 0 && cold >= self.config.target_c {
            self.phase = 1;
            self.phase_time_s = 0.0;
            self.pull_time_s = self.time_s;
            self.pull_probe_c = probe;
            self.peak_probe_c = probe;
            self.peak_after_pull_s = 0.0;
        } else if (self.phase == 0 && self.phase_time_s >= self.config.max_cook_s - 1e-4)
            || (self.phase == 1 && self.phase_time_s >= self.config.rest_s - 1e-4)
        {
            self.phase = 2;
        }
    }

    fn face(&mut self, a: usize, b: usize) {
        if self.inside[b] == 0 {
            return;
        }
        let ka = self.conductivity[a];
        let kb = self.conductivity[b];
        let kf = 2.0 * ka * kb / (ka + kb).max(1e-12);
        let q = (kf * (self.temperature[b] - self.temperature[a]) * self.h) as f64;
        self.power[a] += q;
        self.power[b] -= q;
    }
    pub fn step_many(&mut self, steps: u32) -> u32 {
        for _ in 0..steps {
            if self.phase == 2 {
                break;
            }
            self.step();
        }
        self.phase
    }
}

static mut SOLVER: Option<Simulation> = None;

#[no_mangle]
pub extern "C" fn solver_new(
    preset: u32,
    mass_kg: f32,
    oven_c: f32,
    initial_c: f32,
    target_c: f32,
    convection: u32,
    covered: u32,
    n: u32,
    max_cook_s: f32,
    rest_s: f32,
) -> u32 {
    let config = Config {
        preset,
        mass_kg,
        oven_c,
        initial_c,
        target_c,
        convection: convection != 0,
        covered: covered != 0,
        n: n as usize,
        max_cook_s,
        rest_s,
    };
    unsafe {
        SOLVER = Some(Simulation::new(config));
    }
    1
}
#[no_mangle]
pub extern "C" fn solver_step(steps: u32) -> u32 {
    unsafe { SOLVER.as_mut().map(|s| s.step_many(steps)).unwrap_or(2) }
}
#[no_mangle]
pub extern "C" fn solver_time() -> f32 {
    unsafe { SOLVER.as_ref().map(|s| s.time_s).unwrap_or(0.0) }
}
#[no_mangle]
pub extern "C" fn solver_coldest() -> f32 {
    unsafe { SOLVER.as_ref().map(|s| s.coldest()).unwrap_or(f32::NAN) }
}
#[no_mangle]
pub extern "C" fn solver_probe() -> f32 {
    unsafe {
        SOLVER
            .as_ref()
            .map(|s| s.probe_temperature())
            .unwrap_or(f32::NAN)
    }
}
#[no_mangle]
pub extern "C" fn solver_hottest() -> f32 {
    unsafe { SOLVER.as_ref().map(|s| s.hottest()).unwrap_or(f32::NAN) }
}
#[no_mangle]
pub extern "C" fn solver_pasteurization() -> f32 {
    unsafe {
        SOLVER
            .as_ref()
            .map(|s| s.pasteurization_minutes)
            .unwrap_or(0.0)
    }
}
#[no_mangle]
pub extern "C" fn solver_pull_time() -> f32 {
    unsafe { SOLVER.as_ref().map(|s| s.pull_time_s).unwrap_or(-1.0) }
}
#[no_mangle]
pub extern "C" fn solver_pull_probe() -> f32 {
    unsafe { SOLVER.as_ref().map(|s| s.pull_probe_c).unwrap_or(f32::NAN) }
}
#[no_mangle]
pub extern "C" fn solver_peak() -> f32 {
    unsafe { SOLVER.as_ref().map(|s| s.peak_probe_c).unwrap_or(f32::NAN) }
}
#[no_mangle]
pub extern "C" fn solver_peak_after_pull() -> f32 {
    unsafe { SOLVER.as_ref().map(|s| s.peak_after_pull_s).unwrap_or(0.0) }
}
#[no_mangle]
pub extern "C" fn solver_evaporated_kg() -> f32 {
    unsafe { SOLVER.as_ref().map(|s| s.evaporated_kg).unwrap_or(0.0) }
}
#[no_mangle]
pub extern "C" fn solver_moisture_fraction() -> f32 {
    unsafe {
        SOLVER
            .as_ref()
            .map(|s| s.moisture_fraction())
            .unwrap_or(0.0)
    }
}
#[no_mangle]
pub extern "C" fn solver_field_ptr() -> *const f32 {
    unsafe {
        SOLVER
            .as_ref()
            .map(|s| s.temperature.as_ptr())
            .unwrap_or(std::ptr::null())
    }
}
#[no_mangle]
pub extern "C" fn solver_field_len() -> u32 {
    unsafe {
        SOLVER
            .as_ref()
            .map(|s| s.temperature.len() as u32)
            .unwrap_or(0)
    }
}
#[no_mangle]
pub extern "C" fn solver_grid_size() -> u32 {
    unsafe { SOLVER.as_ref().map(|s| s.n as u32).unwrap_or(0) }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn property_anchor() {
        let p = properties(60.0);
        assert!((p.rho - 1054.0).abs() < 15.0);
        assert!((p.cp - 3540.0).abs() < 120.0);
        assert!((p.k - 0.50).abs() < 1e-5);
    }
    #[test]
    fn progressive_state_reaches_completion() {
        let mut s = Simulation::new(Config {
            preset: 0,
            mass_kg: 0.25,
            oven_c: 180.0,
            initial_c: 20.0,
            target_c: 21.0,
            convection: true,
            covered: false,
            n: 17,
            max_cook_s: 1800.0,
            rest_s: 60.0,
        });
        while s.phase != 2 {
            s.step_many(100);
        }
        assert!(s.pull_time_s > 0.0);
        assert!(s.peak_probe_c >= 21.0);
    }
}
