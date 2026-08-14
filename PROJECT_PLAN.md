# Roast Solver — Project Plan (3D architecture)

A webpage that predicts internal time–temperature curves for roasts, poultry, etc. by solving the 3D heat equation with honest boundary conditions. v1 uses parametric shape presets; v2 reconstructs geometry from a photo. Both feed the same solver through a single interface: a signed distance field.

## 0. Architecture in one sentence

**Geometry sources (preset SDF now, photo→mesh→SDF later) → voxelized SDF + surface normals/areas → 3D explicit finite-difference solver with embedded-boundary Robin BC → T(x,t) field → outputs (coldest-point curve, pull time, carryover, doneness field, pasteurization integral).**

The solver never knows where the SDF came from. That contract is the whole design.

## 1. Physics model

### 1.1 Governing equation

ρ(T) cp(T) ∂T/∂t = ∇·(k(T) ∇T), lean-meat baseline (≈75% water):

| Property | Value |
|---|---|
| ρ | 1050–1080 kg/m³ (also weight → volume) |
| cp | 3300–3600 J/(kg·K) |
| k | 0.45–0.50 W/(m·K) |
| α | 1.2–1.4 × 10⁻⁷ m²/s |

Temperature dependence via Choi–Okos composition model; lag properties one step (Picard). Optional effective-cp bump for protein denaturation (50–70°C) if calibration demands it.

### 1.2 Boundary condition (Robin, three terms — Bi ≈ 2–4 so none of this is optional)

q'' = h_conv (T_oven − T_s) + εσ (T_wall⁴ − T_s⁴) − h_fg · ṁ_evap

- **Convection:** h ≈ 8–12 W/m²K still oven, 15–25 with fan (the convection toggle).
- **Radiation:** ε ≈ 0.85–0.95; linearized h_rad ≈ 15–20 W/m²K at roasting temperatures. Linearize about previous-step T_s.
- **Evaporation:** wet surface rides near wet-bulb temperature. Lewis-analogy mass transfer h_m = h_conv/(ρ_air cp_air Le^(2/3)); finite surface-moisture reservoir (~0.1–0.5 kg/m², calibrated); on depletion switch to dry-crust regime. Covered/dutch-oven mode means saturated air and evaporation ≈ 0.
- **Pan contact patch:** insulated in v1. In 3D the patch is a real bottom region of the SDF surface.

### 1.3 Rest / carryover

At pull time, swap BC to ambient (h ≈ 5–10, room temperature, foil tent = reduced h and ε) and keep integrating. Report core overshoot and time of peak core temperature.

## 2. Geometry pipeline

### 2.1 Interface

A geometry source provides on the solver Cartesian grid:

- occupancy (inside/outside per cell)
- signed distance φ near the boundary
- per-boundary-cell unit normal from ∇φ/|∇φ|
- wetted-area fraction

Everything downstream is source-agnostic.

### 2.2 v1 analytic/composed SDF presets

- Roast: superellipsoid, anisotropically scaled to V = m/ρ at preset aspect ratios.
- Whole bird: body spheroid ∪ leg/thigh capsules ∪ wing stubs, minus cavity spheroid, with smooth-min blending.
- Slab: rounded box.
- Ham: sphere/teardrop.

## 3. Solver

### 3.1 Explicit discretization

Use forward Euler, a 7-point stencil, and Float32 arrays. Stability: dt ≤ h²/(6α). At h = 1.5 mm, dt ≈ 3 s. A production box is roughly 128³ with 3–5k steps. WASM + SIMD runs in a worker and progressively streams T(t). WebGPU is later and not required through M6.

### 3.2 Embedded-boundary Robin BC

Naive stair-stepping overestimates surface area and inflates heating rate. Required treatment:

- identify boundary cells from φ sign changes
- compute true area fractions and normals via cut-cell weighting, or use Gibou–Fedkiw-style ghost values extrapolated along normals
- apply flux per boundary cell with its own wet reservoir/crust state
- preserve distinct behavior for pan-shadowed bottom and exposed crown

This is the most validation-critical component.

### 3.3 Validation suite before UI

1. Voxelized sphere against the exact Robin-BC series solution, with eigenvalues from 1 − λ cot λ = Bi. Target <1% center-temperature error at production resolution.
2. Energy budget: integrated surface flux equals body enthalpy change.
3. Resolution convergence on a preset shape.
4. Baldwin sous-vide tables/high-h water bath to isolate the interior model.
5. Slab/cylinder analytic regression anchors.

## 4. Outputs

- T(t) at the instantaneous coldest point and at a stable probe location (preferably the pull-time coldest point).
- Pull-time recommendation, predicted carryover, peak core temperature, and time of peak during rest.
- 3D doneness visualization with scrubbable slices and isosurface/doneness bands.
- Pasteurization integral ∫10^((T−T_ref)/z) dt at the coldest point, exposed carefully behind an advanced toggle.
- What-if overlays for oven temperature, convection, initial temperature, and covered/uncovered mode.

## 5. Software plan

1. **Python reference:** NumPy implementation where physics and embedded boundaries are proven; Nix flake; permanent regression oracle.
2. **Web core:** Rust→WASM SIMD version of the same kernel, with golden-output tests against Python on a fixed scenario matrix; progressive T(t) streaming from a worker.
3. **Frontend:** static client-side app. Inputs include preset, weight, oven temperature, convection, starting temperature, target temperature, and covered/uncovered. Show curves plus 3D slices/isosurfaces.
4. Photo inference is v2 and out of scope through M6.

## 6. Calibration data

Use analytic solutions, Baldwin tables, and published charts for broad checks. The production design accepts leave-in probe logs for fitting convection, emissivity, and surface-moisture reservoir by preset. For this build, no real logs are available: use clearly labeled, documented synthetic calibration fixtures and avoid claiming empirical accuracy.

## 7. Milestones in scope

1. **M1 — Physics spec + property module + SDF preset library:** superellipsoid roast, composed bird with cavity, slab.
2. **M2 — Python 3D explicit solver, interior only:** Dirichlet-box tests and convergence.
3. **M3 — Embedded-boundary Robin BC:** analytic embedded sphere and energy-budget validation.
4. **M4 — Full BC physics:** radiation, staged evaporation with per-cell state, rest phase; documented synthetic calibration for this build.
5. **M5 — Web core port:** Rust/WASM SIMD, regression-locked to Python, progressive T(t) streaming from a worker.
6. **M6 — UI:** inputs, curves, slice/isosurface viewer, pull-time/carryover, and pasteurization readout.

## 8. Explicitly out of scope

- M7 WebGPU acceleration
- M8 photo-to-mesh pipeline
- heterogeneous bone/fat fields
- claims of real-world calibration without probe logs

## 9. Open engineering choices

Use M3 evidence to choose grid resolution; start WASM-first; frame pasteurization conservatively. Make reasonable documented choices without waiting for user input.
