//! Rust port of the NumPy reference kernel. The wasm wrapper exchanges JSON so
//! its worker protocol stays stable independently of wasm-bindgen glue details.
use serde::{Deserialize, Serialize};

const SIGMA: f64 = 5.670_374_419e-8;
const H_FG: f64 = 2.257e6;
const R_VAPOR: f64 = 461.5;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(default)]
pub struct Config {
    pub preset: String,
    pub mass_kg: f64,
    pub spacing_m: f64,
    pub initial_c: f64,
    pub oven_c: f64,
    pub target_c: f64,
    pub convection: bool,
    pub covered: bool,
    pub max_roast_s: f64,
    pub rest_s: f64,
    pub sample_interval_s: f64,
    pub moisture_kg_m2: f64,
}
impl Default for Config {
    fn default() -> Self {
        Self {
            preset: "roast".into(),
            mass_kg: 1.8,
            spacing_m: 0.006,
            initial_c: 5.0,
            oven_c: 180.0,
            target_c: 57.0,
            convection: false,
            covered: false,
            max_roast_s: 6.0 * 3600.0,
            rest_s: 30.0 * 60.0,
            sample_interval_s: 60.0,
            moisture_kg_m2: 0.24,
        }
    }
}

#[derive(Clone, Copy)]
struct Environment {
    air: f64,
    wall: f64,
    h: f64,
    epsilon: f64,
    humidity: f64,
    covered: bool,
    evaporation: bool,
}
impl Environment {
    fn oven(c: &Config) -> Self {
        Self {
            air: c.oven_c,
            wall: c.oven_c,
            h: if c.convection { 20.0 } else { 10.0 },
            epsilon: 0.9,
            humidity: if c.covered { 1.0 } else { 0.1 },
            covered: c.covered,
            evaporation: !c.covered,
        }
    }
    fn rest() -> Self {
        Self {
            air: 22.,
            wall: 22.,
            h: 7.,
            epsilon: 0.9,
            humidity: 0.45,
            covered: false,
            evaporation: false,
        }
    }
}

#[derive(Clone)]
pub struct Grid {
    pub dims: [usize; 3],
    pub spacing: f64,
    pub origin: [f64; 3],
    pub phi: Vec<f32>,
    pub inside: Vec<bool>,
    pub normals: Vec<[f32; 3]>,
    pub area: Vec<f32>,
    pub pan: Vec<bool>,
}
impl Grid {
    fn idx(&self, x: usize, y: usize, z: usize) -> usize {
        (x * self.dims[1] + y) * self.dims[2] + z
    }
    pub fn volume(&self) -> f64 {
        self.inside.iter().filter(|v| **v).count() as f64 * self.spacing.powi(3)
    }
    pub fn surface_area(&self) -> f64 {
        self.area.iter().map(|v| *v as f64).sum()
    }
}

fn smooth_min(a: f64, b: f64, r: f64) -> f64 {
    let h = (0.5 + 0.5 * (b - a) / r).clamp(0., 1.);
    b * (1. - h) + a * h - r * h * (1. - h)
}
fn ellipsoid(x: f64, y: f64, z: f64, a: f64, b: f64, c: f64) -> f64 {
    (((x / a).powi(2) + (y / b).powi(2) + (z / c).powi(2)).sqrt() - 1.) * a.min(b).min(c)
}
fn capsule(p: [f64; 3], a: [f64; 3], b: [f64; 3], r: f64) -> f64 {
    let ba = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
    let pa = [p[0] - a[0], p[1] - a[1], p[2] - a[2]];
    let h = ((pa[0] * ba[0] + pa[1] * ba[1] + pa[2] * ba[2])
        / (ba[0] * ba[0] + ba[1] * ba[1] + ba[2] * ba[2]))
        .clamp(0., 1.);
    ((pa[0] - ba[0] * h).powi(2) + (pa[1] - ba[1] * h).powi(2) + (pa[2] - ba[2] * h).powi(2)).sqrt()
        - r
}
fn rounded_box(x: f64, y: f64, z: f64, h: [f64; 3], r: f64) -> f64 {
    let q = [x.abs() - h[0] + r, y.abs() - h[1] + r, z.abs() - h[2] + r];
    (q[0].max(0.).powi(2) + q[1].max(0.).powi(2) + q[2].max(0.).powi(2)).sqrt()
        + q[0].max(q[1]).max(q[2]).min(0.)
        - r
}

fn shape_info(name: &str) -> (f64, [[f64; 2]; 3]) {
    match name {
        "roast" => (
            1.681014924144357,
            [[-1.05, 1.05], [-0.651, 0.651], [-0.546, 0.546]],
        ),
        "slab" => (
            1.2279990317809413,
            [[-1.05, 1.05], [-0.756, 0.756], [-0.231, 0.231]],
        ),
        "bird" => (
            1.4177634547564366,
            [[-0.95, 1.18], [-0.94, 0.94], [-0.68, 0.68]],
        ),
        "ham" => (
            1.7952401792588788,
            [[-0.98, 1.15], [-0.75, 0.75], [-0.72, 0.72]],
        ),
        _ => panic!("unknown preset"),
    }
}
fn unit_sdf(name: &str, x: f64, y: f64, z: f64) -> f64 {
    match name {
        "roast" => {
            (((x.abs()).powf(2.6) + (y.abs() / 0.62).powf(2.6) + (z.abs() / 0.52).powf(2.6))
                .powf(1. / 2.6)
                - 1.)
                * 0.52
        }
        "slab" => rounded_box(x, y, z, [1., 0.72, 0.22], 0.12),
        "ham" => smooth_min(
            ellipsoid(x, y, z, 0.9, 0.68, 0.65),
            ellipsoid(x - 0.42, y, z, 0.68, 0.52, 0.50),
            0.12,
        ),
        "bird" => {
            let mut u = smooth_min(
                ellipsoid(x, y, z, 0.86, 0.62, 0.56),
                ellipsoid(x + 0.22, y, z + 0.16, 0.72, 0.58, 0.46),
                0.10,
            );
            for side in [-1., 1.] {
                u = smooth_min(
                    u,
                    capsule(
                        [x, y, z],
                        [0.34, side * 0.40, -0.20],
                        [0.92, side * 0.62, -0.42],
                        0.18,
                    ),
                    0.07,
                );
                u = smooth_min(
                    u,
                    capsule(
                        [x, y, z],
                        [-0.18, side * 0.48, 0.10],
                        [0.30, side * 0.83, -0.02],
                        0.11,
                    ),
                    0.05,
                );
            }
            u.max(-ellipsoid(x - 0.06, y, z - 0.05, 0.42, 0.30, 0.30))
        }
        _ => panic!("unknown preset"),
    }
}

pub fn voxelize(config: &Config) -> Grid {
    let (unit_volume, bounds) = shape_info(&config.preset);
    let scale = ((config.mass_kg / 1060.) / unit_volume).cbrt();
    let mut dims = [0; 3];
    let mut origin = [0.; 3];
    for a in 0..3 {
        let lo = bounds[a][0] * scale - 2. * config.spacing_m;
        let hi = bounds[a][1] * scale + 2. * config.spacing_m;
        dims[a] = ((hi - lo) / config.spacing_m).ceil() as usize + 1;
        let center = (lo + hi) / 2.;
        origin[a] = center - (dims[a] as f64 - 1.) / 2. * config.spacing_m;
    }
    let count = dims[0] * dims[1] * dims[2];
    let mut phi = vec![0f32; count];
    let mut inside = vec![false; count];
    let index = |x: usize, y: usize, z: usize| (x * dims[1] + y) * dims[2] + z;
    for x in 0..dims[0] {
        for y in 0..dims[1] {
            for z in 0..dims[2] {
                let p = [
                    origin[0] + x as f64 * config.spacing_m,
                    origin[1] + y as f64 * config.spacing_m,
                    origin[2] + z as f64 * config.spacing_m,
                ];
                let v = (scale * unit_sdf(&config.preset, p[0] / scale, p[1] / scale, p[2] / scale))
                    as f32;
                let i = index(x, y, z);
                phi[i] = v;
                inside[i] = v <= 0.;
            }
        }
    }
    let mut normals = vec![[0f32; 3]; count];
    let h = config.spacing_m;
    for x in 1..dims[0] - 1 {
        for y in 1..dims[1] - 1 {
            for z in 1..dims[2] - 1 {
                let i = index(x, y, z);
                let gx =
                    (phi[index(x + 1, y, z)] as f64 - phi[index(x - 1, y, z)] as f64) / (2. * h);
                let gy =
                    (phi[index(x, y + 1, z)] as f64 - phi[index(x, y - 1, z)] as f64) / (2. * h);
                let gz =
                    (phi[index(x, y, z + 1)] as f64 - phi[index(x, y, z - 1)] as f64) / (2. * h);
                let m = (gx * gx + gy * gy + gz * gz).sqrt().max(1e-12);
                normals[i] = [(gx / m) as f32, (gy / m) as f32, (gz / m) as f32];
            }
        }
    }
    let mut area = vec![0f32; count];
    let mut min_z = f64::INFINITY;
    for x in 0..dims[0] {
        for y in 0..dims[1] {
            for z in 0..dims[2] {
                let i = index(x, y, z);
                if !inside[i] {
                    continue;
                }
                min_z = min_z.min(origin[2] + z as f64 * h);
                let mut exposed = 0;
                for (dx, dy, dz) in [
                    (1, 0, 0),
                    (-1, 0, 0),
                    (0, 1, 0),
                    (0, -1, 0),
                    (0, 0, 1),
                    (0, 0, -1),
                ] {
                    let xx = x as isize + dx;
                    let yy = y as isize + dy;
                    let zz = z as isize + dz;
                    if xx < 0
                        || yy < 0
                        || zz < 0
                        || xx >= dims[0] as isize
                        || yy >= dims[1] as isize
                        || zz >= dims[2] as isize
                        || !inside[index(xx as usize, yy as usize, zz as usize)]
                    {
                        exposed += 1
                    }
                }
                if exposed > 0 {
                    let n = normals[i];
                    let l1 = (n[0].abs() + n[1].abs() + n[2].abs()).max(1.);
                    area[i] = (exposed as f64 * h * h / l1 as f64) as f32;
                }
            }
        }
    }
    let mut pan = vec![false; count];
    for x in 0..dims[0] {
        for y in 0..dims[1] {
            for z in 0..dims[2] {
                let i = index(x, y, z);
                let zz = origin[2] + z as f64 * h;
                pan[i] = area[i] > 0. && normals[i][2] < -0.45 && zz < min_z + 1.6 * h;
            }
        }
    }
    Grid {
        dims,
        spacing: h,
        origin,
        phi,
        inside,
        normals,
        area,
        pan,
    }
}

pub fn properties(t: f64) -> (f64, f64, f64) {
    let rho_i = [
        997.18 + 3.1439e-3 * t - 3.7574e-3 * t * t,
        1329.9 - 0.5184 * t,
        925.59 - 0.41757 * t,
        2423.8 - 0.28063 * t,
    ];
    let cp_i = [
        4176.2 - 0.090864 * t + 0.0054731 * t * t,
        2008.2 + 1.2089 * t - 0.0013129 * t * t,
        1984.2 + 1.4733 * t - 0.0048008 * t * t,
        1092.6 + 1.8896 * t - 0.0036817 * t * t,
    ];
    let k_i = [
        0.57109 + 0.0017625 * t - 0.0000067036 * t * t,
        0.17881 + 0.0011958 * t - 0.0000027178 * t * t,
        0.18071 - 0.0027604 * t - 0.00000017749 * t * t,
        0.32962 + 0.0014011 * t - 0.0000029069 * t * t,
    ];
    let f = [0.75, 0.20, 0.03, 0.02];
    let mut vr = 0.;
    let mut cp = 0.;
    let mut k = 0.;
    for i in 0..4 {
        vr += f[i] / rho_i[i];
        cp += f[i] * cp_i[i];
        k += f[i] * k_i[i];
    }
    (1. / vr, cp, k)
}

#[derive(Clone, Serialize)]
pub struct Sample {
    pub time_s: f64,
    pub phase: String,
    pub coldest_c: f32,
    pub probe_c: f32,
    pub hottest_c: f32,
    pub pasteurization_p70_s: f64,
}
#[derive(Serialize)]
pub struct Snapshot {
    pub done: bool,
    pub phase: String,
    pub progress: f64,
    pub pull_time_s: Option<f64>,
    pub carryover_c: f64,
    pub peak_core_c: f64,
    pub peak_time_after_pull_s: f64,
    pub pasteurization_p70_s: f64,
    pub samples: Vec<Sample>,
    pub slice_width: usize,
    pub slice_height: usize,
    pub slice_c: Vec<Option<f32>>,
    pub energy_relative_error: f64,
}

pub struct CoreSimulation {
    pub config: Config,
    pub grid: Grid,
    pub temp: Vec<f32>,
    moisture: Vec<f32>,
    stage: Vec<u8>,
    rate: Vec<f64>,
    pub time: f64,
    phase: u8,
    pull_time: Option<f64>,
    pull_probe: f64,
    probe: usize,
    peak: f64,
    peak_time: f64,
    pasteur: f64,
    surface_e: f64,
    enthalpy_e: f64,
    next_sample: f64,
    pub samples: Vec<Sample>,
}
impl CoreSimulation {
    pub fn new(config: Config) -> Result<Self, String> {
        if config.mass_kg <= 0. || config.spacing_m <= 0. || config.target_c <= config.initial_c {
            return Err("invalid positive mass/spacing or target".into());
        }
        if !["roast", "slab", "bird", "ham"].contains(&config.preset.as_str()) {
            return Err("unknown preset".into());
        }
        let grid = voxelize(&config);
        let n = grid.phi.len();
        let mut moisture = vec![0.; n];
        let mut stage = vec![0; n];
        for i in 0..n {
            if grid.area[i] > 0. {
                moisture[i] = config.moisture_kg_m2 as f32;
            }
            if grid.pan[i] {
                stage[i] = 2
            }
        }
        let center = [
            (grid.dims[0] - 1) as f64 / 2.,
            (grid.dims[1] - 1) as f64 / 2.,
            (grid.dims[2] - 1) as f64 / 2.,
        ];
        let mut probe = 0;
        let mut best = f64::INFINITY;
        for x in 0..grid.dims[0] {
            for y in 0..grid.dims[1] {
                for z in 0..grid.dims[2] {
                    let i = grid.idx(x, y, z);
                    if grid.inside[i] {
                        let d = (x as f64 - center[0]).powi(2)
                            + (y as f64 - center[1]).powi(2)
                            + (z as f64 - center[2]).powi(2);
                        if d < best {
                            best = d;
                            probe = i
                        }
                    }
                }
            }
        }
        let init = config.initial_c as f32;
        let mut s = Self {
            config,
            grid,
            temp: vec![init; n],
            moisture,
            stage,
            rate: vec![0.; n],
            time: 0.,
            phase: 0,
            pull_time: None,
            pull_probe: init as f64,
            probe,
            peak: init as f64,
            peak_time: 0.,
            pasteur: 0.,
            surface_e: 0.,
            enthalpy_e: 0.,
            next_sample: 0.,
            samples: vec![],
        };
        s.record();
        Ok(s)
    }
    pub fn stable_dt(&self) -> f64 {
        let mut max_a: f64 = 0.;
        for sample in 0..=64 {
            let t = -5. + sample as f64 * 255. / 64.;
            let (r, c, k) = properties(t);
            max_a = max_a.max(k / (r * c));
        }
        0.82 * self.grid.spacing.powi(2) / (6. * max_a)
    }
    fn values(&self) -> (f32, f32) {
        let mut lo = f32::INFINITY;
        let mut hi = f32::NEG_INFINITY;
        for (i, t) in self.temp.iter().enumerate() {
            if self.grid.inside[i] {
                lo = lo.min(*t);
                hi = hi.max(*t)
            }
        }
        (lo, hi)
    }
    fn record(&mut self) {
        let (lo, hi) = self.values();
        self.samples.push(Sample {
            time_s: self.time,
            phase: if self.phase == 0 { "roast" } else { "rest" }.into(),
            coldest_c: lo,
            probe_c: self.temp[self.probe],
            hottest_c: hi,
            pasteurization_p70_s: self.pasteur,
        });
    }
    fn saturation(t: f64) -> f64 {
        let t = t.clamp(-20., 99.);
        let p = 611.21 * ((18.678 - t / 234.5) * (t / (257.14 + t))).exp();
        p / (R_VAPOR * (t + 273.15))
    }
    fn step(&mut self, dt: f64, env: Environment) {
        let n = self.temp.len();
        self.rate.fill(0.);
        let mut rho = vec![0.; n];
        let mut cp = vec![0.; n];
        let mut k = vec![0.; n];
        for i in 0..n {
            let p = properties(self.temp[i] as f64);
            rho[i] = p.0;
            cp[i] = p.1;
            k[i] = p.2
        }
        let a = self.grid.spacing.powi(2);
        let h = self.grid.spacing;
        for x in 0..self.grid.dims[0] {
            for y in 0..self.grid.dims[1] {
                for z in 0..self.grid.dims[2] {
                    let i = self.grid.idx(x, y, z);
                    if !self.grid.inside[i] {
                        continue;
                    }
                    for j in [
                        if x + 1 < self.grid.dims[0] {
                            Some(self.grid.idx(x + 1, y, z))
                        } else {
                            None
                        },
                        if y + 1 < self.grid.dims[1] {
                            Some(self.grid.idx(x, y + 1, z))
                        } else {
                            None
                        },
                        if z + 1 < self.grid.dims[2] {
                            Some(self.grid.idx(x, y, z + 1))
                        } else {
                            None
                        },
                    ]
                    .into_iter()
                    .flatten()
                    {
                        if self.grid.inside[j] {
                            let kf = 2. * k[i] * k[j] / (k[i] + k[j]).max(1e-12);
                            let p = kf * a / h * (self.temp[j] as f64 - self.temp[i] as f64);
                            self.rate[i] += p;
                            self.rate[j] -= p;
                        }
                    }
                    if self.grid.area[i] > 0. && !self.grid.pan[i] {
                        let tc = self.temp[i] as f64;
                        let tk = tc + 273.15;
                        let tw = env.wall + 273.15;
                        let hr = env.epsilon * SIGMA * (tw * tw + tk * tk) * (tw + tk);
                        let ht = env.h + hr;
                        let drive = env.h * (env.air - tc) + hr * (env.wall - tc);
                        let dist = (-(self.grid.phi[i] as f64)).clamp(0.08 * h, 1.5 * h);
                        let sensible = drive / (1. + ht * dist / k[i].max(1e-6));
                        let mut evap = 0.;
                        if env.evaporation && !env.covered {
                            let hm = env.h / (1.15 * 1007. * 0.86f64.powf(2. / 3.));
                            let raw = hm
                                * (Self::saturation(tc) - env.humidity * Self::saturation(env.air))
                                    .max(0.)
                                * if self.stage[i] == 0 { 1. } else { 0.08 };
                            evap = raw
                                .min(self.moisture[i] as f64 / dt)
                                .min(0.88 * sensible.max(0.) / H_FG);
                            self.moisture[i] = (self.moisture[i] - ((evap * dt) as f32)).max(0.);
                            if self.moisture[i] <= 1e-8 {
                                self.stage[i] = 1
                            }
                        }
                        self.rate[i] += (sensible - H_FG * evap) * self.grid.area[i] as f64;
                    }
                }
            }
        }
        let mut se = 0.;
        let mut he = 0.;
        for i in 0..n {
            if self.grid.inside[i] {
                let de = dt * self.rate[i];
                let delta = de / (rho[i] * cp[i] * h.powi(3));
                self.temp[i] = (self.temp[i] as f64 + delta) as f32;
                he += de;
            }
        }
        // Internal face powers cancel, so this sum is the net boundary energy.
        se += dt * self.rate.iter().sum::<f64>();
        self.surface_e += se;
        self.enthalpy_e += he;
        let (lo, _) = self.values();
        self.pasteur += dt * 10f64.powf((lo as f64 - 70.) / 7.);
        self.time += dt;
    }
    pub fn advance_steps(&mut self, max_steps: usize) {
        for _ in 0..max_steps {
            if self.phase == 2 {
                break;
            }
            let phase_end = if self.phase == 0 {
                self.config.max_roast_s
            } else {
                self.pull_time.unwrap() + self.config.rest_s
            };
            let dt = self.stable_dt().min(phase_end - self.time);
            let env = if self.phase == 0 {
                Environment::oven(&self.config)
            } else {
                Environment::rest()
            };
            self.step(dt, env);
            if self.time + 1e-7 >= self.next_sample + self.config.sample_interval_s {
                self.record();
                self.next_sample = self.time;
            }
            let cold = self.values().0 as f64;
            if self.phase == 0
                && (cold >= self.config.target_c || self.time >= self.config.max_roast_s - 1e-8)
            {
                self.pull_time = Some(self.time);
                let mut lo = f32::INFINITY;
                for i in 0..self.temp.len() {
                    if self.grid.inside[i] && self.temp[i] < lo {
                        lo = self.temp[i];
                        self.probe = i
                    }
                }
                self.pull_probe = self.temp[self.probe] as f64;
                self.peak = self.pull_probe;
                self.peak_time = 0.;
                self.phase = 1;
                self.record();
            }
            if self.phase == 1 {
                let p = self.temp[self.probe] as f64;
                if p > self.peak {
                    self.peak = p;
                    self.peak_time = self.time - self.pull_time.unwrap();
                }
                if self.time >= self.pull_time.unwrap() + self.config.rest_s - 1e-8 {
                    self.phase = 2;
                    self.record();
                }
            }
        }
    }
    pub fn run_for_test(&mut self, duration: f64) {
        let end = self.time + duration;
        let env = Environment::oven(&self.config);
        while self.time < end - 1e-9 {
            let dt = self.stable_dt().min(end - self.time);
            self.step(dt, env);
            if self.time + 1e-7 >= self.next_sample + self.config.sample_interval_s {
                self.record();
                self.next_sample = self.time;
            }
        }
        if (self.samples.last().unwrap().time_s - self.time).abs() > 1e-7 {
            self.record()
        }
    }
    pub fn snapshot(&self) -> Snapshot {
        let axis =
            if self.grid.dims[0] >= self.grid.dims[1] && self.grid.dims[0] >= self.grid.dims[2] {
                0
            } else if self.grid.dims[1] >= self.grid.dims[2] {
                1
            } else {
                2
            };
        let cut = self.grid.dims[axis] / 2;
        let (w, h) = match axis {
            0 => (self.grid.dims[2], self.grid.dims[1]),
            1 => (self.grid.dims[2], self.grid.dims[0]),
            _ => (self.grid.dims[1], self.grid.dims[0]),
        };
        let mut slice = Vec::with_capacity(w * h);
        for v in 0..h {
            for u in 0..w {
                let (x, y, z) = match axis {
                    0 => (cut, v, u),
                    1 => (v, cut, u),
                    _ => (v, u, cut),
                };
                let i = self.grid.idx(x, y, z);
                slice.push(if self.grid.inside[i] {
                    Some(self.temp[i])
                } else {
                    None
                })
            }
        }
        let total = self.config.max_roast_s + self.config.rest_s;
        Snapshot {
            done: self.phase == 2,
            phase: match self.phase {
                0 => "roast",
                1 => "rest",
                _ => "done",
            }
            .into(),
            progress: (self.time / total).min(1.),
            pull_time_s: self.pull_time,
            carryover_c: self.peak - self.pull_probe,
            peak_core_c: self.peak,
            peak_time_after_pull_s: self.peak_time,
            pasteurization_p70_s: self.pasteur,
            samples: self.samples.clone(),
            slice_width: w,
            slice_height: h,
            slice_c: slice,
            energy_relative_error: (self.surface_e - self.enthalpy_e).abs()
                / self.surface_e.abs().max(self.enthalpy_e.abs()).max(1.),
        }
    }
}

#[cfg(target_arch = "wasm32")]
use wasm_bindgen::prelude::*;
#[cfg_attr(target_arch = "wasm32", wasm_bindgen)]
pub struct RoastSimulation {
    inner: CoreSimulation,
}
#[cfg_attr(target_arch = "wasm32", wasm_bindgen)]
impl RoastSimulation {
    #[cfg_attr(target_arch = "wasm32", wasm_bindgen(constructor))]
    pub fn new(config_json: &str) -> Result<RoastSimulation, String> {
        let c: Config = serde_json::from_str(config_json).map_err(|e| e.to_string())?;
        Ok(Self {
            inner: CoreSimulation::new(c)?,
        })
    }
    pub fn advance(&mut self, max_steps: usize) -> String {
        self.inner.advance_steps(max_steps);
        serde_json::to_string(&self.inner.snapshot()).unwrap()
    }
    pub fn snapshot(&self) -> String {
        serde_json::to_string(&self.inner.snapshot()).unwrap()
    }
}
