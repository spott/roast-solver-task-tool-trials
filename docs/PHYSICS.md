# Physics and numerical specification

This document records the M1–M6 engineering choices made from `PROJECT_PLAN.md`.

## Material model

The interior solves

\[
\rho(T)c_p(T)\,\partial_tT=\nabla\cdot(k(T)\nabla T).
\]

`properties.py` evaluates Choi–Okos water/protein/fat/carbohydrate/ash polynomials for a 75/20/3/0/2 mass-percent synthetic lean composition. Specific heat and conductivity use a mass-weighted parallel mixture; density uses specific-volume mixing. The bulk values are bounded to the plan's lean-meat envelope (1050–1080 kg/m³, 3300–3600 J/kg/K, 0.45–0.50 W/m/K), because an unconstrained component mixture is not itself a measured bulk-meat correlation at temperature extremes. Properties are lagged one explicit step (Picard).

The optional 15 kJ/kg Gaussian effective-`cp` denaturation feature is disabled by default. No data support fitting it in this build.

## Geometry contract

Every source produces center occupancy, signed distance `phi`, normals from the physical-grid SDF gradient, embedded surface area, a wetted fraction, and a pan-contact mask. Presets are scaled by `(mass / 1060 kg/m³)^(1/3)`. The composed bird is the smooth union of body/breast ellipsoids, leg and wing capsules, minus an ellipsoidal cavity. The solver does not branch on geometry source.

The current cut-surface estimate uses a one-sided triangular regularized delta over `-1.5h <= phi <= 0`:

\[
A_i = 2(1+\phi_i/\epsilon)|\nabla\phi_i|h^3/\epsilon.
\]

This coarea estimate avoids Manhattan stair-step area and is orientation independent in the continuum limit. It is still a diffuse, center-occupancy embedded method—not a tiny-cell conservative cut-volume reconstruction. That distinction and the measured resolution behavior are reported in `VALIDATION.md`.

## Interior and boundary update

Internal face powers use harmonic face conductivity. Each face contribution is added to one voxel and subtracted from its neighbor, so interior conduction cannot create energy. Forward Euler uses

\[
\Delta t=0.72h^2/(6\alpha_{max}).
\]

Each embedded surface cell computes a ghost-surface balance. With distance `d=max(-phi,h/4)`, `G=k/d`, and lagged radiation coefficient

\[
h_r=\epsilon\sigma(T_w+T_s)(T_w^2+T_s^2),
\]

the dry provisional surface temperature is `(G Ti + hc Ta + hr Tw)/(G+hc+hr)`. Evaporation is evaluated, then the balance is solved once more with its latent sink. The final accounted flux uses nonlinear Stefan–Boltzmann radiation:

\[
q''=h_c(T_a-T_s)+\epsilon\sigma(T_w^4-T_s^4)-h_{fg}\dot m.
\]

The bottom patch (`n_z < -0.55` near minimum z) is insulated. This keeps crown and pan-shadowed behavior distinct.

## Evaporation stages

Lewis analogy gives

\[
h_m=h_c/(\rho_{air}c_{p,air}Le^{2/3}),\quad
\dot m=h_m\max(\rho_{v,sat}(T_s)-\rho_{v,air},0).
\]

Make-up air humidity is referenced at at most 30°C; treating relative humidity as saturation at 180°C would create nonphysical absolute humidity. Every surface cell starts with its own 0.25 kg/m² synthetic reservoir. Flux is capped by the mass remaining in that cell for the current step. On depletion, latent cooling stops and the dry-crust convection coefficient rises 15%. Covered mode uses near-saturated air and an additional 0.03 evaporation factor. Reservoir and factors are model assumptions, not fitted values.

## Pull, rest, and outputs

Cooking changes to room-air boundary conditions when the instantaneous coldest occupied voxel reaches the target. Rest continues at 22°C and 7 W/m²K; the API also supports a foil tent (lower convection and emissivity). A stable probe is the deepest SDF voxel. Reported carryover is its rest peak minus its pull value.

The safety integral is

\[
F_{70,z=10}=\int 10^{(T_{cold}-70)/10}\,dt/60.
\]

It is shown behind an advanced disclosure and is explicitly not a safety guarantee. Species, pathogen, handling history, measurement uncertainty, and official guidance remain outside this thermal integral.

## Numerical precision and ports

Python fields are Float32; powers and energy accumulators use Float64. Rust uses the same formulas, Float32 fields, and Float64 antisymmetric face powers. The browser preview uses 31³ to preserve responsiveness on low-end devices. Release WASM is compiled with the `simd128` target feature (allowing LLVM vectorization). The ABI exposes progressive `solver_step` calls and direct read-only field memory; no generated binding runtime is needed.
