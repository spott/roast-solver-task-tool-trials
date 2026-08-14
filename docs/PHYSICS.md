# Physics and numerical specification (M1–M6)

`PROJECT_PLAN.md` is the product authority; this document records implementation choices.

## Domain and properties

All values are SI internally and temperature differences use kelvin/°C interchangeably. Presets produce a signed distance field on a cell-centred Cartesian grid. `inside`, `phi`, outward SDF normals, reconstructed boundary area, wetted fraction, and pan mask form the geometry contract. Roast volume is scaled to `mass / 1060 kg m⁻³`; voxelization leaves a resolution-dependent volume error.

The property module uses a 75% water / 20% protein / 5% fat Choi–Okos-style component mixture. Density has weak thermal expansion. Properties are clipped to the cooking range and lagged one explicit step (Picard). There is no denaturation heat-capacity bump because there is no data to justify fitting one.

## Discretization and embedded boundary

The solver is conservative cell-centred finite volume. Internal Cartesian faces use harmonic conductivity and each face is visited once. Forward Euler uses

`dt <= 0.82 dx² / (6 max(alpha))`.

For each SDF sign-changing grid link, projected face area `dx²` is assigned to the inside cell and divided by the local normal L1 norm. This Crofton/cut-face reconstruction removes the orientation bias of naive stair-step area. It is binary-volume rather than a small-cell cut-volume scheme, avoiding the cut-cell time-step singularity. The cost is first-to-second-order boundary-position error; resolution convergence should always accompany precision claims.

At each surface cell the Robin flux is reconstructed through a half-cell conduction resistance:

`q = [h_conv T_air + h_rad T_wall - (h_conv+h_rad) T_cell - h_fg m_dot] /
     [1 + (h_conv+h_rad) (dx/2) / k]`.

`h_rad = epsilon sigma (Tw+Ts)(Tw²+Ts²)` is the exact secant linearization about the prior surface temperature. The update applies `q * reconstructed_area`, so integrated surface energy equals the discrete body enthalpy change. `StepAccounting` separately exposes convection, radiation and latent diagnostics. Pan-shadowed lower cells are insulated.

## Evaporation and rest

Every exposed cell owns an independent areal moisture reservoir (default 0.25 kg/m²). Lewis analogy computes mass transfer with `Le=0.9`; evaporation is limited by reservoir remaining in that cell. On depletion, evaporation becomes zero and convection is multiplied by the documented dry-crust factor 0.72. Covered mode suppresses evaporation. This is intentionally a simple two-stage surface model, not a tissue moisture transport model.

At target crossing, the boundary switches to 22°C room conditions (`h=7 W/m²K`, emissivity 0.85) and integration continues for the selected rest. The stable probe is fixed at the pull-time coldest cell in both implementations (before pull it follows the instantaneous coldest point). Carryover, peak, and peak delay derive from post-pull samples.

## Validation evidence

`tests/` provides:

1. a manufactured Dirichlet cube eigenmode and second-order interior convergence;
2. the exact convective-sphere series, solving `1 - lambda cot(lambda) = Bi`, as an embedded Robin anchor;
3. per-step surface-energy versus lagged-enthalpy equality (tight numerical tolerance), including evaporation;
4. staged reservoir depletion and finite dry-crust continuation;
5. preset SDF contract/volume checks and language-neutral Python/Rust property anchors.

The sphere tolerance includes binary cut-volume, area reconstruction, temperature-dependent properties, and finite resolution. Production browser defaults (34³) favor responsiveness, not the plan's eventual 128³ accuracy target. “Detailed” 44³ is the M6 browser option. The exact series helper supports higher-resolution convergence studies.

Baldwin/high-h water-bath tables and cylinder/slab series remain broad external references rather than empirical calibration data. No published table is copied or represented as a fitted fixture here.

## Known limitations

Homogeneous lean tissue, no bone/fat heterogeneity; approximate preset geometry; uncertain convection and moisture; no boiling clamp or shrinkage; insulated pan contact; no door cycling; no WebGPU; no photo reconstruction. Pasteurization uses `integral 10^((T-70)/7) dt` in minutes at the modeled coldest cell and does not replace a validated safety process.
