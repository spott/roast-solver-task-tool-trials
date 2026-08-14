# Physics and numerical contract (M1–M4)

## State and properties

The reference solves

`rho(T) cp(T) dT/dt = div(k(T) grad(T))`

on occupied cell centres. `roast_solver/properties.py` implements mass-fraction
Choi–Okos component correlations for 75% water, 20% protein, 4% fat, and 1% ash.
Properties are evaluated from the previous temperature (one Picard lag). The
optional 50–70 °C effective-cp feature is **off**, because this build has no data
to identify it.

Geometry enters only through `GridGeometry`: occupancy, signed distance,
outward normal, physical surface area per cut cell, and pan contact. Presets are
analytic SDFs: a superellipsoid roast, composed body/limb bird with cavity,
rounded slab, teardrop ham, and validation sphere. They are scaled to
`weight / 1060 kg m-3`.

## Discretization and embedded boundary

The interior is a cell-centred finite-volume seven-point stencil. Conductivity
at a shared face is the harmonic mean and the face power is added to one cell
and subtracted from the other. The time step is bounded by both
`0.82 h²/(6 alpha)` and surface conductance/cell capacity.

For every inside cell adjoining outside, sign-changing faces form a projected
area vector. Its Euclidean magnitude is the reconstructed surface area; its
direction is blended with the SDF normal. Thus an oblique interface uses the
magnitude of its area vector instead of summing all exposed voxel faces. This is
a first-order cut-cell reconstruction, not a body-fitted mesh. The lower,
downward-facing patch is tagged as insulated pan contact.

Boundary power is applied exactly once as `area * q''`:

* convection: `h (Tenv - Ts)`, h = 10 W/m²K still or 20 fan;
* radiation: `epsilon sigma (Twall^4 - Ts^4)`, evaluated at previous-step Ts
  (the lagged nonlinear/linearized Robin term);
* evaporation: Lewis-analogy transfer with a **per-cell** areal water reservoir.
  Mass loss is capped by remaining reservoir each step. At depletion the cell
  is dry-crust stage and latent cooling becomes zero. Covered mode uses a nearly
  saturated boundary layer and 5% vapour-removal multiplier;
* pan cells receive none of these terms (v1 insulated patch).

The energy ledger accumulates convection, radiation, latent heat, net boundary
input, and the exact discrete sensible-energy increment. Shared interior powers
cancel pairwise. Floating-point residual is tested in `tests/test_solver.py`.

## Pull, rest, and outputs

Pull occurs when the instantaneous coldest occupied cell reaches target. A
source-agnostic stable probe is chosen once as the deepest-SDF cell and sampled
for the full cook/rest curve; the separate coldest curve remains conservative.
Rest swaps the environment to 22 °C and
h = 7 W/m²K (foil settings are available in Python). Integration continues to
report peak core and peak time. Pasteurization is integrated per cell as
`integral 10^((T-70)/7) dt / 60`; the UI displays the minimum-cell value. It is
an explanatory model output, not a safety certification.

The Python solver is the high-fidelity reference. The interactive Rust core
uses constant mid-range properties and a lower grid for responsiveness, while
preserving the conservative stencil, reconstructed-area boundary, radiation,
per-cell moisture, rest, and lethality equations. This practical approximation
is shown as an engine/model assumption in the UI and locked at kernel level by
a cross-language Float32 golden fixture.
