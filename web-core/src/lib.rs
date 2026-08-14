//! Rust/WASM implementation of the NumPy reference model.
//!
//! The core intentionally uses f64 and the same 3x3x3 sub-cell quadrature as
//! `python/roast_solver`.  This is a CPU browser baseline, not the excluded
//! WebGPU milestone.
use std::f64::consts::PI;
use wasm_bindgen::prelude::*;

const SIGMA: f64 = 5.670_374_419e-8;
const H_FG: f64 = 2.30e6;
const MIN_EFFECTIVE_FRACTION: f64 = 0.25;

#[derive(Clone, Copy, Debug)]
pub struct Properties {
    pub rho: f64,
    pub cp: f64,
    pub k: f64,
}

pub fn properties(temp_c: f64) -> Properties {
    let t = temp_c.clamp(-20.0, 150.0);
    let x = [0.75, 0.20, 0.03, 0.008, 0.012];
    let cp = [
        4.1762 - 9.0864e-5 * t + 5.4731e-6 * t * t,
        2.0082 + 1.2089e-3 * t - 1.3129e-6 * t * t,
        1.9842 + 1.4733e-3 * t - 4.8008e-6 * t * t,
        1.5488 + 1.9625e-3 * t - 5.9399e-6 * t * t,
        1.0926 + 1.8896e-3 * t - 3.6817e-6 * t * t,
    ];
    let k = [
        0.57109 + 1.7625e-3 * t - 6.7036e-6 * t * t,
        0.17881 + 1.1958e-3 * t - 2.7178e-6 * t * t,
        0.18071 - 2.7604e-4 * t - 1.7749e-7 * t * t,
        0.20141 + 1.3874e-3 * t - 4.3312e-6 * t * t,
        0.32962 + 1.4011e-3 * t - 2.9069e-6 * t * t,
    ];
    let rho_component = [
        997.18 + 3.1439e-3 * t - 3.7574e-3 * t * t,
        1329.9 - 0.5184 * t,
        925.59 - 0.41757 * t,
        1599.1 - 0.31046 * t,
        2423.8 - 0.28063 * t,
    ];
    let mut cp_mix = 0.0;
    let mut k_mix = 0.0;
    let mut reciprocal = 0.0;
    for q in 0..5 {
        cp_mix += x[q] * cp[q];
        k_mix += x[q] * k[q];
        reciprocal += x[q] / rho_component[q];
    }
    Properties {
        rho: (1.0 / reciprocal).clamp(1050.0, 1080.0),
        cp: 1000.0 * cp_mix,
        k: k_mix,
    }
}

#[derive(Clone, Debug)]
pub struct Boundary {
    pub oven_c: f64,
    pub wall_c: f64,
    pub h_conv: f64,
    pub emissivity: f64,
    pub covered: bool,
    pub initial_moisture_kg_m2: f64,
    pub vapor_density_kg_m3: f64,
    pub pan_insulated: bool,
    pub ambient_c: f64,
    pub rest_h: f64,
    pub foil_tent: bool,
}
impl Default for Boundary {
    fn default() -> Self {
        Self {
            oven_c: 180.0,
            wall_c: 180.0,
            h_conv: 10.0,
            emissivity: 0.9,
            covered: false,
            initial_moisture_kg_m2: 0.25,
            vapor_density_kg_m3: 0.008,
            pan_insulated: true,
            ambient_c: 22.0,
            rest_h: 7.0,
            foil_tent: false,
        }
    }
}

#[derive(Clone, Copy, Debug, Default)]
pub struct Ledger {
    pub convection_j: f64,
    pub radiation_j: f64,
    pub evaporation_j: f64,
    pub net_surface_j: f64,
    pub discrete_enthalpy_j: f64,
    pub residual_j: f64,
}

#[derive(Clone, Debug)]
pub struct Geometry {
    pub n: usize,
    pub spacing: f64,
    pub origin: f64,
    pub volume_fraction: Vec<f64>,
    pub effective_fraction: Vec<f64>,
    pub active: Vec<bool>,
    pub faces: [Vec<f64>; 6],
    pub area: Vec<f64>,
    pub pan: Vec<bool>,
}
impl Geometry {
    #[inline]
    pub fn idx(&self, i: usize, j: usize, k: usize) -> usize {
        (i * self.n + j) * self.n + k
    }
    pub fn volume(&self) -> f64 {
        self.volume_fraction.iter().sum::<f64>() * self.spacing.powi(3)
    }
    pub fn embedded_area(&self) -> f64 {
        self.area.iter().sum()
    }
}

#[derive(Clone, Copy)]
enum Preset {
    Roast,
    Ham,
    Slab,
    Bird,
}
impl Preset {
    fn parse(s: &str) -> Result<Self, String> {
        match s {
            "roast" => Ok(Self::Roast),
            "ham" => Ok(Self::Ham),
            "slab" => Ok(Self::Slab),
            "bird" => Ok(Self::Bird),
            _ => Err(format!("unknown preset {s}")),
        }
    }
}

// Lanczos approximation, sufficient to reproduce the preset volume scale.
fn gamma(z: f64) -> f64 {
    const P: [f64; 9] = [
        0.999_999_999_999_809_9,
        676.520_368_121_885_1,
        -1259.139_216_722_402_8,
        771.323_428_777_653_1,
        -176.615_029_162_140_6,
        12.507_343_278_687_905,
        -0.138_571_095_265_720_12,
        9.984_369_578_019_572e-6,
        1.505_632_735_149_311_6e-7,
    ];
    if z < 0.5 {
        return PI / ((PI * z).sin() * gamma(1.0 - z));
    }
    let zz = z - 1.0;
    let mut x = P[0];
    for (i, p) in P.iter().enumerate().skip(1) {
        x += p / (zz + i as f64);
    }
    let t = zz + 7.5;
    (2.0 * PI).sqrt() * t.powf(zz + 0.5) * (-t).exp() * x
}
fn superellipsoid(x: f64, y: f64, z: f64, a: f64, b: f64, c: f64, p: f64) -> f64 {
    ((x.abs() / a).powf(p) + (y.abs() / b).powf(p) + (z.abs() / c).powf(p))
        .powf(1.0 / p)
        .sub(1.0)
        * a.min(b).min(c)
}
trait Sub {
    fn sub(self, x: Self) -> Self;
}
impl Sub for f64 {
    fn sub(self, x: f64) -> f64 {
        self - x
    }
}
fn rounded_box(x: f64, y: f64, z: f64, h: [f64; 3], r: f64) -> f64 {
    let q = [
        x.abs() - (h[0] - r),
        y.abs() - (h[1] - r),
        z.abs() - (h[2] - r),
    ];
    let outside = (q[0].max(0.0).powi(2) + q[1].max(0.0).powi(2) + q[2].max(0.0).powi(2)).sqrt();
    outside + q[0].max(q[1]).max(q[2]).min(0.0) - r
}
fn capsule(p: [f64; 3], a: [f64; 3], b: [f64; 3], r: f64) -> f64 {
    let pa = [p[0] - a[0], p[1] - a[1], p[2] - a[2]];
    let ba = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
    let h = ((pa[0] * ba[0] + pa[1] * ba[1] + pa[2] * ba[2])
        / (ba[0] * ba[0] + ba[1] * ba[1] + ba[2] * ba[2]))
        .clamp(0.0, 1.0);
    ((pa[0] - ba[0] * h).powi(2) + (pa[1] - ba[1] * h).powi(2) + (pa[2] - ba[2] * h).powi(2)).sqrt()
        - r
}
fn smooth_min(a: f64, b: f64, k: f64) -> f64 {
    let h = (0.5 + 0.5 * (b - a) / k).clamp(0.0, 1.0);
    b * (1.0 - h) + a * h - k * h * (1.0 - h)
}
fn smooth_max(a: f64, b: f64, k: f64) -> f64 {
    -smooth_min(-a, -b, k)
}

#[derive(Clone, Copy)]
struct Shape {
    preset: Preset,
    dims: [f64; 3],
}
impl Shape {
    fn new(preset: Preset, mass: f64) -> Self {
        let volume = mass / 1060.0;
        match preset {
            Preset::Roast | Preset::Ham => {
                let (r, p) = if matches!(preset, Preset::Roast) {
                    ([1.35, 0.85, 0.78], 2.5)
                } else {
                    ([1.15, 0.92, 0.88], 2.2)
                };
                let unit = 8.0 * r.iter().product::<f64>() * gamma(1.0 + 1.0 / p).powi(3)
                    / gamma(1.0 + 3.0 / p);
                let s = (volume / unit).cbrt();
                Self {
                    preset,
                    dims: [s * r[0], s * r[1], s * r[2]],
                }
            }
            Preset::Slab => {
                let r = [1.7, 1.15, 0.42];
                let s = (volume / (8.0 * r.iter().product::<f64>())).cbrt();
                Self {
                    preset,
                    dims: [s * r[0], s * r[1], s * r[2]],
                }
            }
            Preset::Bird => {
                let r = [1.05, 0.78, 0.82];
                let s = (volume / (3.55 * r.iter().product::<f64>())).cbrt();
                Self {
                    preset,
                    dims: [s * r[0], s * r[1], s * r[2]],
                }
            }
        }
    }
    fn extent(&self) -> [f64; 3] {
        match self.preset {
            Preset::Roast | Preset::Ham => [
                1.08 * self.dims[0],
                1.08 * self.dims[1],
                1.08 * self.dims[2],
            ],
            Preset::Slab => [
                1.08 * self.dims[0],
                1.08 * self.dims[1],
                1.08 * self.dims[2],
            ],
            Preset::Bird => [
                1.45 * self.dims[0],
                1.45 * self.dims[1],
                1.15 * self.dims[2],
            ],
        }
    }
    fn sdf(&self, x: f64, y: f64, z: f64) -> f64 {
        let [a, b, c] = self.dims;
        match self.preset {
            Preset::Roast => superellipsoid(x, y, z, a, b, c, 2.5),
            Preset::Ham => superellipsoid(x, y, z, a, b, c, 2.2),
            Preset::Slab => rounded_box(x, y, z, [a, b, c], 0.12 * a.min(b).min(c)),
            Preset::Bird => {
                let mut d = superellipsoid(x, y, z, a, b, c, 2.2);
                for sy in [-1.0, 1.0] {
                    d = smooth_min(
                        d,
                        capsule(
                            [x, y, z],
                            [0.45 * a, sy * 0.55 * b, -0.15 * c],
                            [1.15 * a, sy * 0.85 * b, -0.55 * c],
                            0.20 * a,
                        ),
                        0.10 * a,
                    );
                    d = smooth_min(
                        d,
                        capsule(
                            [x, y, z],
                            [-0.1 * a, sy * 0.72 * b, 0.12 * c],
                            [-0.55 * a, sy * 1.25 * b, 0.05 * c],
                            0.12 * a,
                        ),
                        0.08 * a,
                    );
                }
                let cavity = superellipsoid(x + 0.18 * a, y, z, 0.50 * a, 0.42 * b, 0.48 * c, 2.0);
                smooth_max(d, -cavity, 0.05 * a)
            }
        }
    }
}

pub fn make_geometry(preset: &str, mass: f64, n: usize) -> Result<Geometry, String> {
    if !(8..=64).contains(&n) {
        return Err("resolution must be in 8..=64".into());
    }
    if mass <= 0.0 {
        return Err("mass must be positive".into());
    }
    let shape = Shape::new(Preset::parse(preset)?, mass);
    let side = 2.0 * shape.extent().iter().copied().fold(0.0, f64::max) * 1.10;
    let h = side / n as f64;
    let origin = -0.5 * side + 0.5 * h;
    let len = n * n * n;
    let mut vf = vec![0.0; len];
    let mut faces: [Vec<f64>; 6] = std::array::from_fn(|_| vec![0.0; len]);
    let idx = |i: usize, j: usize, k: usize| (i * n + j) * n + k;
    let offsets = [-1.0 / 3.0, 0.0, 1.0 / 3.0];
    for i in 0..n {
        for j in 0..n {
            for k in 0..n {
                let q = idx(i, j, k);
                let c = [
                    origin + i as f64 * h,
                    origin + j as f64 * h,
                    origin + k as f64 * h,
                ];
                let mut count = 0;
                for ox in offsets {
                    for oy in offsets {
                        for oz in offsets {
                            if shape.sdf(c[0] + ox * h, c[1] + oy * h, c[2] + oz * h) <= 0.0 {
                                count += 1
                            }
                        }
                    }
                }
                vf[q] = count as f64 / 27.0;
                for axis in 0..3 {
                    for side_index in 0..2 {
                        let mut count = 0;
                        for oa in offsets {
                            for ob in offsets {
                                let mut p = c;
                                p[axis] += if side_index == 0 { -0.5 * h } else { 0.5 * h };
                                let other = match axis {
                                    0 => [1, 2],
                                    1 => [0, 2],
                                    _ => [0, 1],
                                };
                                p[other[0]] += oa * h;
                                p[other[1]] += ob * h;
                                if shape.sdf(p[0], p[1], p[2]) <= 0.0 {
                                    count += 1
                                }
                            }
                        }
                        faces[2 * axis + side_index][q] = count as f64 / 9.0;
                    }
                }
            }
        }
    }
    let active: Vec<bool> = vf.iter().map(|&v| v > 0.0).collect();
    let effective_fraction = vf
        .iter()
        .map(|&v| {
            if v > 0.0 {
                v.max(MIN_EFFECTIVE_FRACTION)
            } else {
                0.0
            }
        })
        .collect();
    let mut area = vec![0.0; len];
    let mut pan = vec![false; len];
    for q in 0..len {
        if active[q] {
            let v = [
                faces[0][q] - faces[1][q],
                faces[2][q] - faces[3][q],
                faces[4][q] - faces[5][q],
            ];
            let norm = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]).sqrt();
            area[q] = norm * h * h;
            if norm > 0.0 {
                pan[q] = v[2] / norm < -0.45;
            }
        }
    }
    Ok(Geometry {
        n,
        spacing: h,
        origin,
        volume_fraction: vf,
        effective_fraction,
        active,
        faces,
        area,
        pan,
    })
}

#[derive(Clone, Copy, Debug)]
pub struct Sample {
    pub time_s: f64,
    pub coldest_c: f64,
    pub center_c: f64,
    pub mean_c: f64,
    pub pasteurization_s: f64,
}
#[derive(Clone, Debug)]
pub struct Core {
    pub geometry: Geometry,
    pub boundary: Boundary,
    pub temperature: Vec<f64>,
    pub moisture: Vec<f64>,
    pub crust: Vec<bool>,
    pub time_s: f64,
    pub pasteurization_s: f64,
    pub ledger: Ledger,
    center: usize,
}
impl Core {
    pub fn new(geometry: Geometry, boundary: Boundary, initial_c: f64) -> Self {
        let len = geometry.active.len();
        let mut temperature = vec![f64::NAN; len];
        let mut moisture = vec![0.0; len];
        for q in 0..len {
            if geometry.active[q] {
                temperature[q] = initial_c;
            }
            if geometry.area[q] > 0.0 {
                moisture[q] = boundary.initial_moisture_kg_m2;
            }
        }
        let c = (geometry.n as f64 - 1.0) / 2.0;
        let mut center = 0;
        let mut best = f64::INFINITY;
        for i in 0..geometry.n {
            for j in 0..geometry.n {
                for k in 0..geometry.n {
                    let q = geometry.idx(i, j, k);
                    if geometry.active[q] {
                        let d = (i as f64 - c).powi(2)
                            + (j as f64 - c).powi(2)
                            + (k as f64 - c).powi(2);
                        if d < best {
                            best = d;
                            center = q;
                        }
                    }
                }
            }
        }
        Self {
            geometry,
            boundary,
            temperature,
            moisture,
            crust: vec![false; len],
            time_s: 0.0,
            pasteurization_s: 0.0,
            ledger: Ledger::default(),
            center,
        }
    }
    fn conduction(&self, p: &[Properties]) -> (Vec<f64>, Vec<f64>) {
        let g = &self.geometry;
        let mut power = vec![0.0; g.active.len()];
        let mut sum = vec![0.0; g.active.len()];
        for axis in 0..3 {
            for i in 0..g.n {
                for j in 0..g.n {
                    for k in 0..g.n {
                        let pos = [i, j, k];
                        if pos[axis] + 1 >= g.n {
                            continue;
                        }
                        let mut hi = pos;
                        hi[axis] += 1;
                        let loq = g.idx(i, j, k);
                        let hiq = g.idx(hi[0], hi[1], hi[2]);
                        if !(g.active[loq] && g.active[hiq]) {
                            continue;
                        }
                        let frac = 0.5 * (g.faces[2 * axis + 1][loq] + g.faces[2 * axis][hiq]);
                        let kk = 2.0 * p[loq].k * p[hiq].k / (p[loq].k + p[hiq].k).max(1e-12);
                        let conductance = kk * frac * g.spacing;
                        let flow = conductance * (self.temperature[hiq] - self.temperature[loq]);
                        power[loq] += flow;
                        power[hiq] -= flow;
                        sum[loq] += conductance;
                        sum[hiq] += conductance;
                    }
                }
            }
        }
        (power, sum)
    }
    fn saturation(temp: f64) -> f64 {
        let t = temp.clamp(0.0, 99.0);
        let pressure = 133.322 * 10f64.powf(8.07131 - 1730.63 / (233.426 + t));
        pressure / (461.5 * (t + 273.15))
    }
    fn surface(&self, rest: bool, dt: Option<f64>) -> (Vec<f64>, [f64; 4], Vec<f64>) {
        let g = &self.geometry;
        let b = &self.boundary;
        let (air, wall, h, eps) = if rest {
            (
                b.ambient_c,
                b.ambient_c,
                b.rest_h * if b.foil_tent { 0.55 } else { 1.0 },
                b.emissivity * if b.foil_tent { 0.35 } else { 1.0 },
            )
        } else {
            (b.oven_c, b.wall_c, b.h_conv, b.emissivity)
        };
        let mut net = vec![0.0; g.active.len()];
        let mut totals = [0.0; 4];
        let mut hrad_out = vec![0.0; g.active.len()];
        for q in 0..g.active.len() {
            if g.area[q] <= 1e-15 {
                continue;
            }
            let t = self.temperature[q];
            let conv = h * (air - t);
            let tk = t + 273.15;
            let wk = wall + 273.15;
            let hrad = eps * SIGMA * (wk + tk) * (wk * wk + tk * tk);
            let rad = hrad * (wall - t);
            hrad_out[q] = hrad;
            let mut evap = 0.0;
            if self.moisture[q] > 0.0 && !g.pan[q] {
                let hm = h / (1.18 * 1007.0 * 0.9f64.powf(2.0 / 3.0));
                let mut potential = hm * (Self::saturation(t) - b.vapor_density_kg_m3).max(0.0);
                if b.covered {
                    potential *= 0.02
                }
                if rest {
                    potential *= 0.35
                }
                let available = (conv + rad).max(0.0) + 25.0 * (t - 30.0).max(0.0);
                evap = (H_FG * potential).min(available);
                if let Some(d) = dt {
                    evap = evap.min(self.moisture[q] * H_FG / d);
                }
            }
            let (conv, rad, evap) = if b.pan_insulated && g.pan[q] {
                (0.0, 0.0, 0.0)
            } else {
                (conv, rad, evap)
            };
            net[q] = conv + rad - evap;
            totals[0] += conv * g.area[q];
            totals[1] += rad * g.area[q];
            totals[2] += evap * g.area[q];
            totals[3] += net[q] * g.area[q];
        }
        (net, totals, hrad_out)
    }
    pub fn stable_dt(&self, rest: bool) -> f64 {
        let p: Vec<_> = self
            .temperature
            .iter()
            .enumerate()
            .map(|(q, &t)| properties(if self.geometry.active[q] { t } else { 5.0 }))
            .collect();
        let (_, mut conductance) = self.conduction(&p);
        let (_, _, hrad) = self.surface(rest, None);
        let h = if rest {
            self.boundary.rest_h
        } else {
            self.boundary.h_conv
        };
        let mut dt = f64::INFINITY;
        for q in 0..self.geometry.active.len() {
            if self.geometry.active[q] {
                conductance[q] += self.geometry.area[q] * (h + hrad[q] + 25.0);
                let cap = p[q].rho
                    * p[q].cp
                    * self.geometry.effective_fraction[q]
                    * self.geometry.spacing.powi(3);
                dt = dt.min(cap / conductance[q].max(1e-20));
            }
        }
        (0.35 * dt).min(5.0)
    }
    pub fn step(&mut self, dt: f64, rest: bool) {
        let p: Vec<_> = self
            .temperature
            .iter()
            .enumerate()
            .map(|(q, &t)| properties(if self.geometry.active[q] { t } else { 5.0 }))
            .collect();
        let (mut power, _) = self.conduction(&p);
        let (surface, totals, _) = self.surface(rest, Some(dt));
        let old = self.temperature.clone();
        let mut delta = 0.0;
        for q in 0..power.len() {
            if self.geometry.active[q] {
                power[q] += surface[q] * self.geometry.area[q];
                let cap = p[q].rho
                    * p[q].cp
                    * self.geometry.effective_fraction[q]
                    * self.geometry.spacing.powi(3);
                self.temperature[q] = old[q] + dt * power[q] / cap;
                delta += cap * (self.temperature[q] - old[q]);
            }
            if self.geometry.area[q] > 0.0 {
                // Recompute only the local evaporative term to advance the staged reservoir exactly.
                let t = old[q];
                let b = &self.boundary;
                let h = if rest {
                    b.rest_h * if b.foil_tent { 0.55 } else { 1.0 }
                } else {
                    b.h_conv
                };
                let wall = if rest { b.ambient_c } else { b.wall_c };
                let eps = if rest {
                    b.emissivity * if b.foil_tent { 0.35 } else { 1.0 }
                } else {
                    b.emissivity
                };
                let conv = h * ((if rest { b.ambient_c } else { b.oven_c }) - t);
                let tk = t + 273.15;
                let wk = wall + 273.15;
                let rad = eps * SIGMA * (wk + tk) * (wk * wk + tk * tk) * (wall - t);
                let mut evap = 0.0;
                if self.moisture[q] > 0.0 && !self.geometry.pan[q] {
                    let hm = h / (1.18 * 1007.0 * 0.9f64.powf(2.0 / 3.0));
                    let mut potential = hm * (Self::saturation(t) - b.vapor_density_kg_m3).max(0.0);
                    if b.covered {
                        potential *= 0.02
                    }
                    if rest {
                        potential *= 0.35
                    }
                    evap = (H_FG * potential)
                        .min((conv + rad).max(0.0) + 25.0 * (t - 30.0).max(0.0))
                        .min(self.moisture[q] * H_FG / dt);
                }
                if b.pan_insulated && self.geometry.pan[q] {
                    evap = 0.0
                }
                self.moisture[q] = (self.moisture[q] - evap * dt / H_FG).max(0.0);
                if self.moisture[q] <= 1e-12 {
                    self.crust[q] = true;
                }
            }
        }
        let expected = totals[3] * dt;
        self.ledger.convection_j += totals[0] * dt;
        self.ledger.radiation_j += totals[1] * dt;
        self.ledger.evaporation_j += totals[2] * dt;
        self.ledger.net_surface_j += expected;
        self.ledger.discrete_enthalpy_j += delta;
        self.ledger.residual_j += delta - expected;
        let cold = self
            .temperature
            .iter()
            .copied()
            .filter(|v| v.is_finite())
            .fold(f64::INFINITY, f64::min);
        self.pasteurization_s += 10f64.powf((cold - 70.0) / 7.5) * dt;
        self.time_s += dt;
    }
    pub fn run_for(&mut self, duration: f64, rest: bool) {
        let end = self.time_s + duration;
        while self.time_s < end - 1e-10 {
            let dt = self.stable_dt(rest).min(end - self.time_s);
            self.step(dt, rest)
        }
    }
    pub fn sample(&self) -> Sample {
        let mut cold = f64::INFINITY;
        let mut sum = 0.0;
        let mut count = 0;
        for (q, &t) in self.temperature.iter().enumerate() {
            if self.geometry.active[q] {
                cold = cold.min(t);
                sum += t;
                count += 1;
            }
        }
        Sample {
            time_s: self.time_s,
            coldest_c: cold,
            center_c: self.temperature[self.center],
            mean_c: sum / count as f64,
            pasteurization_s: self.pasteurization_s,
        }
    }
    pub fn center_slice(&self) -> Vec<f32> {
        let k = self.geometry.n / 2;
        let mut out = Vec::with_capacity(self.geometry.n * self.geometry.n);
        for i in 0..self.geometry.n {
            for j in 0..self.geometry.n {
                out.push(self.temperature[self.geometry.idx(i, j, k)] as f32)
            }
        }
        out
    }
    pub fn moisture_remaining_kg(&self) -> f64 {
        self.moisture
            .iter()
            .zip(&self.geometry.area)
            .map(|(m, a)| m * a)
            .sum()
    }
}

#[wasm_bindgen]
pub struct Simulation {
    core: Core,
}
#[wasm_bindgen]
impl Simulation {
    #[wasm_bindgen(constructor)]
    pub fn new(
        preset: &str,
        mass_kg: f64,
        resolution: usize,
        initial_c: f64,
        oven_c: f64,
        h_conv: f64,
        emissivity: f64,
        covered: bool,
    ) -> Result<Simulation, JsValue> {
        let geometry =
            make_geometry(preset, mass_kg, resolution).map_err(|e| JsValue::from_str(&e))?;
        let mut boundary = Boundary::default();
        boundary.oven_c = oven_c;
        boundary.wall_c = oven_c;
        boundary.h_conv = h_conv;
        boundary.emissivity = emissivity;
        boundary.covered = covered;
        Ok(Self {
            core: Core::new(geometry, boundary, initial_c),
        })
    }
    pub fn set_rest_conditions(&mut self, ambient_c: f64, rest_h: f64, foil_tent: bool) {
        self.core.boundary.ambient_c = ambient_c;
        self.core.boundary.rest_h = rest_h.max(0.0);
        self.core.boundary.foil_tent = foil_tent;
    }
    pub fn run_chunk(&mut self, seconds: f64, rest: bool) -> String {
        self.core.run_for(seconds.max(0.0), rest);
        self.summary_json()
    }
    pub fn summary_json(&self) -> String {
        let s = self.core.sample();
        format!("{{\"time_s\":{:0.12},\"coldest_c\":{:0.9},\"center_c\":{:0.9},\"mean_c\":{:0.9},\"pasteurization_s\":{:0.12},\"moisture_remaining_kg\":{:0.12},\"energy_residual_j\":{:0.9}}}",s.time_s,s.coldest_c,s.center_c,s.mean_c,s.pasteurization_s,self.core.moisture_remaining_kg(),self.core.ledger.residual_j)
    }
    pub fn center_slice(&self) -> Vec<f32> {
        self.core.center_slice()
    }
    pub fn resolution(&self) -> usize {
        self.core.geometry.n
    }
}
