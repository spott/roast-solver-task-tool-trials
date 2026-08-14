//! Native and WebAssembly CPU implementation of the Roast Solver.
//!
//! The numerical contract mirrors `roast_solver/`: SI geometry and fluxes,
//! Celsius state, a conservative 7-point stencil, an interior level-set shell
//! for embedded-boundary area, radiation, finite surface-water reservoirs,
//! cook/rest phases, and conservative pasteurization integration.

use serde::{Deserialize, Serialize};
use std::f64::consts::PI;

const SIGMA: f64 = 5.670_374_419e-8;
const H_FG: f64 = 2.256e6;
const BIRD_UNIT_VOLUME: f64 = 1.702_286_069_853_643;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(default)]
pub struct Input {
    pub preset: String,
    pub mass_kg: f64,
    pub resolution: usize,
    pub material_density: f64,
    pub initial_c: f64,
    pub target_c: f64,
    pub oven_c: f64,
    pub convection_h: f64,
    pub emissivity: f64,
    pub wall_c: Option<f64>,
    pub covered: bool,
    pub ambient_vapor_density: f64,
    pub lewis_number: f64,
    pub surface_water_kg_m2: f64,
    pub pan_insulated: bool,
    pub max_cook_s: f64,
    pub rest_s: f64,
    pub sample_interval_s: f64,
    pub requested_dt_s: f64,
    pub rest_ambient_c: f64,
    pub rest_h: f64,
    pub foil_tent: bool,
    pub pasteurization_ref_c: f64,
    pub pasteurization_z_c: f64,
    pub denaturation_bump: bool,
}

impl Default for Input {
    fn default() -> Self {
        Self {
            preset: "roast".into(),
            mass_kg: 1.0,
            resolution: 32,
            material_density: 1060.0,
            initial_c: 5.0,
            target_c: 55.0,
            oven_c: 180.0,
            convection_h: 10.0,
            emissivity: 0.9,
            wall_c: None,
            covered: false,
            ambient_vapor_density: 0.010,
            lewis_number: 0.90,
            surface_water_kg_m2: 0.25,
            pan_insulated: true,
            max_cook_s: 5.0 * 3600.0,
            rest_s: 30.0 * 60.0,
            sample_interval_s: 30.0,
            requested_dt_s: 30.0,
            rest_ambient_c: 22.0,
            rest_h: 7.0,
            foil_tent: false,
            pasteurization_ref_c: 70.0,
            pasteurization_z_c: 10.0,
            denaturation_bump: false,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Record {
    pub time_s: f64,
    pub coldest_c: f64,
    pub probe_c: f64,
    pub surface_mean_c: f64,
    pub pasteurization_equivalent_min: f64,
    pub phase: String,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct Energy {
    pub convection_j: f64,
    pub radiation_j: f64,
    pub evaporation_j: f64,
    pub net_surface_j: f64,
    pub enthalpy_change_j: f64,
    pub relative_balance_error: f64,
}

#[derive(Clone, Debug, Serialize)]
pub struct Chunk {
    pub records: Vec<Record>,
    pub done: bool,
    pub phase: String,
    pub progress: f64,
    pub dimensions_zyx: [usize; 3],
    pub temperatures_c: Vec<f32>,
    pub inside: Vec<bool>,
    pub wet_fraction: Vec<f32>,
    pub pull_time_s: Option<f64>,
    pub pull_reached: bool,
    pub peak_core_c: f64,
    pub peak_time_s: f64,
    pub carryover_c: f64,
    pub dt_s: f64,
    pub energy: Energy,
}

#[derive(Clone, Debug)]
struct Geometry {
    dims: [usize; 3],
    inside: Vec<bool>,
    area: Vec<f64>,
    pan: Vec<bool>,
    h: f64,
}

impl Geometry {
    fn idx(&self, z: usize, y: usize, x: usize) -> usize {
        (z * self.dims[1] + y) * self.dims[2] + x
    }
}

fn component_density(t: f64) -> [f64; 5] {
    let t = t.clamp(-20.0, 150.0);
    [
        997.18 + 3.1439e-3 * t - 3.7574e-3 * t * t,
        1329.9 - 0.5184 * t,
        925.59 - 0.41757 * t,
        1599.1 - 0.31046 * t,
        2423.8 - 0.28063 * t,
    ]
}
fn component_cp(t: f64) -> [f64; 5] {
    let t = t.clamp(-20.0, 150.0);
    [
        4176.2 - 0.0909 * t + 5.4731e-3 * t * t,
        2008.2 + 1.2089 * t - 1.3129e-3 * t * t,
        1984.2 + 1.4733 * t - 4.8008e-3 * t * t,
        1548.8 + 1.9625 * t - 5.9399e-3 * t * t,
        1092.6 + 1.8896 * t - 3.6817e-3 * t * t,
    ]
}
fn component_k(t: f64) -> [f64; 5] {
    let t = t.clamp(-20.0, 150.0);
    [
        0.57109 + 1.7625e-3 * t - 6.7036e-6 * t * t,
        0.17881 + 1.1958e-3 * t - 2.7178e-6 * t * t,
        0.18071 - 2.7604e-4 * t - 1.7749e-7 * t * t,
        0.20141 + 1.3874e-3 * t - 4.3312e-6 * t * t,
        0.32962 + 1.4011e-3 * t - 2.9069e-6 * t * t,
    ]
}
const X: [f64; 5] = [0.75, 0.20, 0.03, 0.005, 0.015];
pub fn density(t: f64) -> f64 {
    let r = component_density(t);
    1.0 / (0..5).map(|i| X[i] / r[i]).sum::<f64>()
}
pub fn heat_capacity(t: f64, bump: bool) -> f64 {
    let c = component_cp(t);
    let mut v = (0..5).map(|i| X[i] * c[i]).sum::<f64>();
    if bump {
        v += 120.0 * (-0.5 * ((t.clamp(-20.0, 150.0) - 60.0) / 7.0).powi(2)).exp();
    }
    v
}
pub fn conductivity(t: f64) -> f64 {
    let r = component_density(t);
    let k = component_k(t);
    let volume: f64 = (0..5).map(|i| X[i] / r[i]).sum();
    (0..5).map(|i| (X[i] / r[i]) / volume * k[i]).sum()
}
pub fn diffusivity(t: f64) -> f64 {
    conductivity(t) / (density(t) * heat_capacity(t, false))
}

fn ellipsoid(x: f64, y: f64, z: f64, a: f64, b: f64, c: f64) -> f64 {
    let q = ((x / a).powi(2) + (y / b).powi(2) + (z / c).powi(2)).sqrt();
    (q - 1.0) * (x * x + y * y + z * z).sqrt() / q.max(1e-12)
}
fn capsule(x: f64, y: f64, z: f64, a: [f64; 3], b: [f64; 3], r: f64) -> f64 {
    let p = [x - a[0], y - a[1], z - a[2]];
    let ba = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
    let dot = p[0] * ba[0] + p[1] * ba[1] + p[2] * ba[2];
    let den = ba[0] * ba[0] + ba[1] * ba[1] + ba[2] * ba[2];
    let q = (dot / den).clamp(0.0, 1.0);
    ((p[0] - q * ba[0]).powi(2) + (p[1] - q * ba[1]).powi(2) + (p[2] - q * ba[2]).powi(2)).sqrt()
        - r
}
fn bird(x: f64, y: f64, z: f64) -> f64 {
    let mut outside = ellipsoid(x, y, z, 1.0, 0.67, 0.62);
    for d in [
        capsule(x, y, z, [-0.60, -0.40, -0.18], [-1.20, -0.50, -0.28], 0.20),
        capsule(x, y, z, [-0.60, 0.40, -0.18], [-1.20, 0.50, -0.28], 0.20),
        capsule(x, y, z, [0.20, -0.58, 0.08], [0.65, -0.83, -0.02], 0.12),
        capsule(x, y, z, [0.20, 0.58, 0.08], [0.65, 0.83, -0.02], 0.12),
    ] {
        outside = outside.min(d);
    }
    outside.max(-ellipsoid(x - 0.16, y, z + 0.01, 0.50, 0.35, 0.34))
}
fn rounded_box(x: f64, y: f64, z: f64, h: [f64; 3], r: f64) -> f64 {
    let q = [
        x.abs() - (h[0] - r),
        y.abs() - (h[1] - r),
        z.abs() - (h[2] - r),
    ];
    (q[0].max(0.0).powi(2) + q[1].max(0.0).powi(2) + q[2].max(0.0).powi(2)).sqrt()
        + q[0].max(q[1].max(q[2])).min(0.0)
        - r
}

fn make_geometry(input: &Input) -> Result<Geometry, String> {
    if input.mass_kg <= 0.0 || input.resolution < 12 {
        return Err("mass must be positive and resolution at least 12".into());
    }
    let volume = input.mass_kg / input.material_density;
    let preset = input.preset.to_lowercase();
    let (ext, longest, kind): ([f64; 3], f64, u8) = match preset.as_str() {
        "roast" => {
            let r = [1.0, 0.68, 0.58];
            let gamma = 0.887_263_817_503_075_3_f64; // gamma(1.4)
            let gamma22 = 1.101_802_490_879_712_8_f64; // gamma(2.2)
            let uv = 8.0 * r[0] * r[1] * r[2] * gamma.powi(3) / gamma22;
            let s = (volume / uv).cbrt();
            ([s * r[0], s * r[1], s * r[2]], 2.0 * s, 0)
        }
        "bird" => {
            let s = (volume / BIRD_UNIT_VOLUME).cbrt();
            ([1.45 * s, 1.0 * s, 0.8 * s], 2.65 * s, 1)
        }
        "slab" => {
            let r = [1.0, 0.72, 0.28];
            let s = (volume / (8.0 * r[0] * r[1] * r[2])).cbrt();
            ([s * r[0], s * r[1], s * r[2]], 2.0 * s, 2)
        }
        "ham" | "sphere" => {
            let r = (3.0 * volume / (4.0 * PI)).cbrt();
            ([r, r, r], 2.0 * r, 3)
        }
        _ => return Err(format!("unknown preset {:?}", input.preset)),
    };
    let h = longest / input.resolution as f64;
    let margin = 2.5 * h;
    let dims = [
        ((2.0 * ext[2] + 2.0 * margin) / h).ceil() as usize,
        ((2.0 * ext[1] + 2.0 * margin) / h).ceil() as usize,
        ((2.0 * ext[0] + 2.0 * margin) / h).ceil() as usize,
    ];
    let lo = [-ext[0] - margin, -ext[1] - margin, -ext[2] - margin];
    let n = dims.iter().product();
    let mut phi = vec![0.0; n];
    let mut inside = vec![false; n];
    for z in 0..dims[0] {
        for y in 0..dims[1] {
            for x in 0..dims[2] {
                let xx = lo[0] + (x as f64 + 0.5) * h;
                let yy = lo[1] + (y as f64 + 0.5) * h;
                let zz = lo[2] + (z as f64 + 0.5) * h;
                let p = match kind {
                    0 => {
                        let q = ((xx / ext[0]).abs().powf(2.5)
                            + (yy / ext[1]).abs().powf(2.5)
                            + (zz / ext[2]).abs().powf(2.5))
                        .powf(0.4);
                        (q - 1.0) * ext[2]
                    }
                    1 => {
                        let s = ext[0] / 1.45;
                        s * bird(xx / s, yy / s, zz / s)
                    }
                    2 => rounded_box(xx, yy, zz, ext, 0.1 * (2.0 * ext[2])),
                    _ => (xx * xx + yy * yy + zz * zz).sqrt() - ext[0],
                };
                let i = (z * dims[1] + y) * dims[2] + x;
                phi[i] = p;
                inside[i] = p <= 0.0;
            }
        }
    }
    let mut area = vec![0.0; n];
    let mut nz = vec![0.0; n];
    let mut bottom = f64::INFINITY;
    let mut top = f64::NEG_INFINITY;
    for z in 0..dims[0] {
        for y in 0..dims[1] {
            for x in 0..dims[2] {
                let i = (z * dims[1] + y) * dims[2] + x;
                if inside[i] {
                    let zz = lo[2] + (z as f64 + 0.5) * h;
                    bottom = bottom.min(zz);
                    top = top.max(zz);
                }
                let deriv = |axis: usize| {
                    let (p0, p1, den) = match axis {
                        0 => {
                            if x == 0 {
                                (i, i + 1, h)
                            } else if x + 1 == dims[2] {
                                (i - 1, i, h)
                            } else {
                                (i - 1, i + 1, 2.0 * h)
                            }
                        }
                        1 => {
                            if y == 0 {
                                (i, i + dims[2], h)
                            } else if y + 1 == dims[1] {
                                (i - dims[2], i, h)
                            } else {
                                (i - dims[2], i + dims[2], 2.0 * h)
                            }
                        }
                        _ => {
                            let s = dims[1] * dims[2];
                            if z == 0 {
                                (i, i + s, h)
                            } else if z + 1 == dims[0] {
                                (i - s, i, h)
                            } else {
                                (i - s, i + s, 2.0 * h)
                            }
                        }
                    };
                    (phi[p1] - phi[p0]) / den
                };
                let gx = deriv(0);
                let gy = deriv(1);
                let gz = deriv(2);
                let gn = (gx * gx + gy * gy + gz * gz).sqrt();
                if inside[i] && phi[i] >= -h {
                    area[i] = h * h * gn;
                    nz[i] = gz / gn.max(1e-12);
                }
            }
        }
    }
    if !area.iter().any(|a| *a > 0.0) {
        return Err("grid has no resolved boundary".into());
    }
    let height = top - bottom + h;
    let mut pan = vec![false; n];
    for z in 0..dims[0] {
        let zz = lo[2] + (z as f64 + 0.5) * h;
        for y in 0..dims[1] {
            for x in 0..dims[2] {
                let i = (z * dims[1] + y) * dims[2] + x;
                pan[i] = area[i] > 0.0 && nz[i] < -0.60 && zz < bottom + 0.22 * height;
            }
        }
    }
    Ok(Geometry {
        dims,
        inside,
        area,
        pan,
        h,
    })
}

fn saturation_density(t: f64) -> f64 {
    let t = t.clamp(-20.0, 100.0);
    let p = 610.94 * (17.625 * t / (t + 243.04)).exp();
    p / (461.5 * (t + 273.15))
}

pub struct Engine {
    input: Input,
    geometry: Geometry,
    t: Vec<f32>,
    wet: Vec<f64>,
    initial_wet: Vec<f64>,
    dt: f64,
    elapsed: f64,
    next_sample: f64,
    pasteur_s: f64,
    phase: u8,
    rest_end: f64,
    pull_time: Option<f64>,
    pull_temp: f64,
    pull_reached: bool,
    probe: usize,
    pending: Vec<Record>,
    all_records: Vec<Record>,
    energy: Energy,
}

impl Engine {
    pub fn new(input: Input) -> Result<Self, String> {
        if input.sample_interval_s <= 0.0
            || input.requested_dt_s <= 0.0
            || input.max_cook_s < 0.0
            || input.rest_s < 0.0
        {
            return Err("times must be non-negative and steps positive".into());
        }
        let geometry = make_geometry(&input)?;
        let mut amax: f64 = 0.0;
        let max_t = input.oven_c.max(input.initial_c) + 20.0;
        for j in 0..128 {
            let q = j as f64 / 127.0;
            amax = amax.max(diffusivity(-5.0 + q * (max_t + 5.0)));
        }
        let dt = input
            .requested_dt_s
            .min(0.9 * geometry.h * geometry.h / (6.0 * amax));
        let t = vec![input.initial_c as f32; geometry.inside.len()];
        let mut wet = vec![0.0; t.len()];
        for i in 0..t.len() {
            if geometry.area[i] > 0.0 {
                wet[i] = input.surface_water_kg_m2;
            }
        }
        let mut center = [0.0; 3];
        let mut count = 0.0;
        for z in 0..geometry.dims[0] {
            for y in 0..geometry.dims[1] {
                for x in 0..geometry.dims[2] {
                    let i = geometry.idx(z, y, x);
                    if geometry.inside[i] {
                        center[0] += z as f64;
                        center[1] += y as f64;
                        center[2] += x as f64;
                        count += 1.0;
                    }
                }
            }
        }
        center.iter_mut().for_each(|v| *v /= count);
        let mut probe = 0;
        let mut best = f64::INFINITY;
        for z in 0..geometry.dims[0] {
            for y in 0..geometry.dims[1] {
                for x in 0..geometry.dims[2] {
                    let i = geometry.idx(z, y, x);
                    if geometry.inside[i] {
                        let d = (z as f64 - center[0]).powi(2)
                            + (y as f64 - center[1]).powi(2)
                            + (x as f64 - center[2]).powi(2);
                        if d < best {
                            best = d;
                            probe = i;
                        }
                    }
                }
            }
        }
        let initial_wet = wet.clone();
        let mut e = Self {
            input,
            geometry,
            t,
            wet,
            initial_wet,
            dt,
            elapsed: 0.0,
            next_sample: 0.0,
            pasteur_s: 0.0,
            phase: 0,
            rest_end: 0.0,
            pull_time: None,
            pull_temp: 0.0,
            pull_reached: false,
            probe,
            pending: vec![],
            all_records: vec![],
            energy: Energy::default(),
        };
        e.sample();
        Ok(e)
    }
    fn sample(&mut self) {
        let mut cold = f64::INFINITY;
        let mut sw = 0.0;
        let mut sa = 0.0;
        for i in 0..self.t.len() {
            if self.geometry.inside[i] {
                cold = cold.min(self.t[i] as f64);
            }
            if self.geometry.area[i] > 0.0 {
                sw += self.t[i] as f64 * self.geometry.area[i];
                sa += self.geometry.area[i];
            }
        }
        let r = Record {
            time_s: self.elapsed,
            coldest_c: cold,
            probe_c: self.t[self.probe] as f64,
            surface_mean_c: sw / sa,
            pasteurization_equivalent_min: self.pasteur_s / 60.0,
            phase: if self.phase == 0 { "cook" } else { "rest" }.into(),
        };
        self.pending.push(r.clone());
        self.all_records.push(r);
    }
    fn step(&mut self, sd: f64, cooking: bool) {
        let n = self.t.len();
        let old: Vec<f64> = self.t.iter().map(|v| *v as f64).collect();
        let mut rho = vec![0.0; n];
        let mut cp = vec![0.0; n];
        let mut k = vec![0.0; n];
        let mut power = vec![0.0; n];
        for i in 0..n {
            if self.geometry.inside[i] {
                rho[i] = density(old[i]);
                cp[i] = heat_capacity(old[i], self.input.denaturation_bump);
                k[i] = conductivity(old[i]);
            }
        }
        let d = self.geometry.dims;
        let strides = [d[1] * d[2], d[2], 1];
        for stride in strides {
            for z in 0..d[0] {
                for y in 0..d[1] {
                    for x in 0..d[2] {
                        let i = self.geometry.idx(z, y, x);
                        let valid = match stride {
                            1 => x + 1 < d[2],
                            s if s == d[2] => y + 1 < d[1],
                            _ => z + 1 < d[0],
                        };
                        if valid {
                            let j = i + stride;
                            if self.geometry.inside[i] && self.geometry.inside[j] {
                                let kf = 2.0 * k[i] * k[j] / (k[i] + k[j]).max(1e-12);
                                let q = kf * self.geometry.h * (old[j] - old[i]);
                                power[i] += q;
                                power[j] -= q;
                            }
                        }
                    }
                }
            }
        }
        for i in 0..n {
            if self.geometry.area[i] <= 0.0 {
                continue;
            }
            let active = !(self.input.pan_insulated && self.geometry.pan[i]);
            if !active {
                continue;
            }
            let ts = old[i];
            let (air, wall, hc, eps, evap) = if cooking {
                (
                    self.input.oven_c,
                    self.input.wall_c.unwrap_or(self.input.oven_c),
                    self.input.convection_h,
                    self.input.emissivity,
                    !self.input.covered,
                )
            } else {
                let f = if self.input.foil_tent { 0.55 } else { 1.0 };
                let e = if self.input.foil_tent { 0.35 } else { 1.0 };
                (
                    self.input.rest_ambient_c,
                    self.input.rest_ambient_c,
                    self.input.rest_h * f,
                    self.input.emissivity * e,
                    false,
                )
            };
            let qc = hc * (air - ts);
            let tk = ts + 273.15;
            let wk = wall + 273.15;
            let hr = eps * SIGMA * (wk + tk) * (wk * wk + tk * tk);
            let qr = hr * (wall - ts);
            let mut mdot = 0.0;
            if evap {
                let hm = hc / (1010.0 * self.input.lewis_number.powf(2.0 / 3.0));
                mdot = (hm * (saturation_density(ts) - self.input.ambient_vapor_density).max(0.0))
                    .min(self.wet[i] / sd.max(1e-12));
            }
            let ql = H_FG * mdot;
            self.wet[i] = (self.wet[i] - mdot * sd).max(0.0);
            let qn = qc + qr - ql;
            power[i] += qn * self.geometry.area[i];
            self.energy.convection_j += qc * self.geometry.area[i] * sd;
            self.energy.radiation_j += qr * self.geometry.area[i] * sd;
            self.energy.evaporation_j += ql * self.geometry.area[i] * sd;
            self.energy.net_surface_j += qn * self.geometry.area[i] * sd;
        }
        let vol = self.geometry.h.powi(3);
        for i in 0..n {
            if self.geometry.inside[i] {
                let nv = old[i] + sd * power[i] / (rho[i] * cp[i] * vol);
                self.t[i] = nv as f32;
                self.energy.enthalpy_change_j += rho[i] * cp[i] * vol * (self.t[i] as f64 - old[i]);
            }
        }
        let cold = self
            .t
            .iter()
            .zip(&self.geometry.inside)
            .filter(|(_, b)| **b)
            .map(|(v, _)| *v as f64)
            .fold(f64::INFINITY, f64::min);
        self.pasteur_s += 10f64
            .powf((cold - self.input.pasteurization_ref_c) / self.input.pasteurization_z_c)
            * sd;
    }
    fn transition_to_rest(&mut self, reached: bool) {
        self.pull_time = Some(self.elapsed);
        self.pull_temp = self.coldest();
        self.pull_reached = reached;
        if self
            .all_records
            .last()
            .map(|r| r.time_s < self.elapsed - 1e-9)
            .unwrap_or(true)
        {
            self.sample();
        }
        self.phase = 1;
        self.rest_end = self.elapsed + self.input.rest_s;
        self.next_sample = self.elapsed;
        if self.input.rest_s <= 1e-9 {
            self.phase = 2;
        }
    }
    fn coldest(&self) -> f64 {
        self.t
            .iter()
            .zip(&self.geometry.inside)
            .filter(|(_, b)| **b)
            .map(|(v, _)| *v as f64)
            .fold(f64::INFINITY, f64::min)
    }
    pub fn run_steps(&mut self, max_steps: usize) -> Chunk {
        let mut steps = 0;
        while self.phase < 2 && steps < max_steps {
            if self.phase == 0 {
                if self.elapsed >= self.input.max_cook_s - 1e-9 {
                    self.transition_to_rest(false);
                    continue;
                }
                let sd = self.dt.min(self.input.max_cook_s - self.elapsed);
                self.step(sd, true);
                self.elapsed += sd;
                steps += 1;
                if self.elapsed + 1e-9 >= self.next_sample + self.input.sample_interval_s {
                    self.next_sample = self.elapsed;
                    self.sample();
                }
                if self.coldest() >= self.input.target_c {
                    self.transition_to_rest(true);
                }
            } else {
                if self.elapsed >= self.rest_end - 1e-9 {
                    self.phase = 2;
                    if self
                        .all_records
                        .last()
                        .map(|r| r.time_s < self.elapsed - 1e-9)
                        .unwrap_or(true)
                    {
                        self.sample();
                    }
                    continue;
                }
                let sd = self.dt.min(self.rest_end - self.elapsed);
                self.step(sd, false);
                self.elapsed += sd;
                steps += 1;
                if self.elapsed + 1e-9 >= self.next_sample + self.input.sample_interval_s {
                    self.next_sample = self.elapsed;
                    self.sample();
                }
            }
        }
        if self.phase == 2 && self.energy.relative_balance_error == 0.0 {
            self.energy.relative_balance_error =
                (self.energy.enthalpy_change_j - self.energy.net_surface_j).abs()
                    / self.energy.net_surface_j.abs().max(1.0);
        }
        self.chunk()
    }
    fn chunk(&mut self) -> Chunk {
        let records = std::mem::take(&mut self.pending);
        let pull = self.pull_time;
        let mut peak = self.pull_temp;
        let mut pt = pull.unwrap_or(0.0);
        if let Some(p) = pull {
            for r in &self.all_records {
                if r.time_s >= p - 1e-9 && r.coldest_c > peak {
                    peak = r.coldest_c;
                    pt = r.time_s;
                }
            }
        }
        let wet_fraction = self
            .wet
            .iter()
            .zip(&self.initial_wet)
            .map(|(wet, initial)| {
                if *initial > 0.0 {
                    (wet / initial) as f32
                } else {
                    0.0
                }
            })
            .collect();
        let progress = if self.phase == 0 {
            (self.elapsed / self.input.max_cook_s.max(1.0)).min(1.0) * 0.85
        } else if self.phase == 1 {
            0.85 + 0.15
                * ((self.elapsed - pull.unwrap_or(self.elapsed)) / self.input.rest_s.max(1.0))
                    .min(1.0)
        } else {
            1.0
        };
        Chunk {
            records,
            done: self.phase == 2,
            phase: match self.phase {
                0 => "cook",
                1 => "rest",
                _ => "done",
            }
            .into(),
            progress,
            dimensions_zyx: self.geometry.dims,
            temperatures_c: self.t.clone(),
            inside: self.geometry.inside.clone(),
            wet_fraction,
            pull_time_s: pull,
            pull_reached: self.pull_reached,
            peak_core_c: peak,
            peak_time_s: pt,
            carryover_c: if pull.is_some() {
                peak - self.pull_temp
            } else {
                0.0
            },
            dt_s: self.dt,
            energy: self.energy.clone(),
        }
    }
}

pub fn simulate(input: Input) -> Result<Chunk, String> {
    let mut e = Engine::new(input)?;
    let mut records = Vec::new();
    loop {
        let mut chunk = e.run_steps(10_000);
        records.append(&mut chunk.records);
        if chunk.done {
            chunk.records = records;
            return Ok(chunk);
        }
    }
}

#[cfg(feature = "wasm")]
mod wasm_api {
    use super::*;
    use wasm_bindgen::prelude::*;
    #[wasm_bindgen]
    pub struct WasmSimulation {
        engine: Engine,
    }
    #[wasm_bindgen]
    impl WasmSimulation {
        #[wasm_bindgen(constructor)]
        pub fn new(input_json: &str) -> Result<WasmSimulation, JsValue> {
            let input: Input =
                serde_json::from_str(input_json).map_err(|e| JsValue::from_str(&e.to_string()))?;
            Engine::new(input)
                .map(|engine| Self { engine })
                .map_err(|e| JsValue::from_str(&e))
        }
        pub fn run_chunk(&mut self, max_steps: usize) -> Result<String, JsValue> {
            serde_json::to_string(&self.engine.run_steps(max_steps))
                .map_err(|e| JsValue::from_str(&e.to_string()))
        }
    }
    #[wasm_bindgen]
    pub fn properties_json(t: f64) -> String {
        serde_json::json!({"density":density(t),"heat_capacity":heat_capacity(t,false),"conductivity":conductivity(t),"diffusivity":diffusivity(t)}).to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn property_ranges() {
        assert!((density(20.0) - 1060.0).abs() < 20.0);
        assert!(heat_capacity(20.0, false) > 3500.0);
        assert!(conductivity(20.0) > 0.4);
    }
    #[test]
    fn all_presets_build() {
        for p in ["roast", "bird", "slab", "ham"] {
            let mut i = Input::default();
            i.preset = p.into();
            i.resolution = 12;
            assert!(Engine::new(i).is_ok());
        }
    }
    #[test]
    fn short_run_balances() {
        let mut i = Input::default();
        i.resolution = 12;
        i.max_cook_s = 30.0;
        i.rest_s = 0.0;
        i.target_c = 999.0;
        i.requested_dt_s = 1.0;
        let r = simulate(i).unwrap();
        assert!(r.done);
        assert!(!r.records.is_empty());
        assert!(r.energy.relative_balance_error < 2e-4);
        assert!(r.temperatures_c.iter().all(|v| v.is_finite()));
    }

    #[test]
    fn matches_python_golden() {
        let path = format!(
            "{}/../fixtures/python_rust_golden.json",
            env!("CARGO_MANIFEST_DIR")
        );
        let golden: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
        assert_eq!(golden["empirically_calibrated"], false);
        let rel = golden["tolerances"]["property_relative"].as_f64().unwrap();
        for sample in golden["property_samples"].as_array().unwrap() {
            let t = sample["temperature_c"].as_f64().unwrap();
            for (name, actual) in [
                ("density", density(t)),
                ("heat_capacity", heat_capacity(t, false)),
                ("conductivity", conductivity(t)),
                ("diffusivity", diffusivity(t)),
            ] {
                let expected = sample[name].as_f64().unwrap();
                assert!(
                    (actual - expected).abs() / expected.abs() < rel,
                    "{name} at {t}"
                );
            }
        }
        let input: Input = serde_json::from_value(golden["scenario"].clone()).unwrap();
        let result = simulate(input).unwrap();
        let expected = &golden["expected"];
        let dims: Vec<usize> = serde_json::from_value(expected["dimensions_zyx"].clone()).unwrap();
        assert_eq!(result.dimensions_zyx.as_slice(), dims);
        assert_eq!(
            result.inside.iter().filter(|v| **v).count(),
            expected["inside_cells"].as_u64().unwrap() as usize
        );
        assert!((result.dt_s - expected["dt_s"].as_f64().unwrap()).abs() < 1e-12);
        let records = expected["records"].as_array().unwrap();
        assert_eq!(result.records.len(), records.len());
        let temp_tol = golden["tolerances"]["temperature_c_absolute"]
            .as_f64()
            .unwrap();
        for (actual, wanted) in result.records.iter().zip(records) {
            assert!((actual.time_s - wanted["time_s"].as_f64().unwrap()).abs() < 1e-9);
            for (a, key) in [
                (actual.coldest_c, "coldest_c"),
                (actual.probe_c, "probe_c"),
                (actual.surface_mean_c, "surface_mean_c"),
            ] {
                assert!(
                    (a - wanted[key].as_f64().unwrap()).abs() < temp_tol,
                    "{key} at {}: {a} vs {}",
                    actual.time_s,
                    wanted[key]
                );
            }
        }
        let expected_energy = expected["net_surface_j"].as_f64().unwrap();
        let energy_rel =
            (result.energy.net_surface_j - expected_energy).abs() / expected_energy.abs();
        assert!(
            energy_rel < golden["tolerances"]["energy_relative"].as_f64().unwrap(),
            "energy {energy_rel}"
        );
    }
}
