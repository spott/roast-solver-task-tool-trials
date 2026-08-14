# Reference physics and numerics (M1–M4)

The NumPy implementation in `python/roast_solver` is the permanent readable
oracle. It solves

`rho(T) cp(T) dT/dt = div(k(T) grad(T))`

with Choi–Okos component property polynomials for a declared 75% water lean
composition. Properties are lagged one explicit step. Density is bounded to the
project's 1050–1080 kg/m³ bulk range because shrinkage is not modeled.

## Geometry and embedded boundary

All presets produce one signed-distance function. Voxelization samples volume
and each Cartesian face at sub-cell points. The embedded area vector is the
negative vector sum of occupied Cartesian face areas (the discrete divergence
theorem), avoiding six-face stair-step area. Its magnitude and direction are the
surface area and outward normal. Roast and slab are analytic superquadric and
rounded-box SDFs. Bird is a smooth union of a torso, leg/thigh capsules and wing
stubs with a spheroidal cavity subtracted.

Shared occupied face fractions weight equal-and-opposite conductive fluxes.
Tiny cut cells are a known explicit-scheme problem, so fractions below 0.25 use
a documented effective-volume merge. Geometry areas are unchanged, and this
same effective volume is used by both update and energy ledger.

## Surface physics

Every embedded surface cell owns a moisture reservoir and crust flag. Its
lagged-temperature heat flux is:

* convection `h (T_air - T_s)`;
* radiation `epsilon sigma (T_wall^4 - T_s^4)`, evaluated through its exact
  secant coefficient at the old temperature;
* evaporation based on a Lewis-analogy mass-transfer ceiling and an
  energy-limited synthetic wet-surface closure. Available water limits each
  cell independently; depletion changes it to dry crust;
* zero net flux on downward-facing insulated pan cells.

Covered mode reduces evaporation to 2%. This closure and its 30°C wet-bulb
anchor are engineering assumptions, not fitted measurements. During rest the
environment changes to room air/walls; foil reduces convection and emissivity.
The coldest-point lethality integral uses an explicitly configurable reference
and z-value and must not be interpreted as food-safety advice.

## Stability and accounting

The timestep is bounded from each cell's lagged capacity divided by the sum of
conductive and bounded surface conductances, with safety factor 0.35. Every
conductive link is applied with equal and opposite power. The ledger compares
`sum(rho cp V_eff delta_T)` for each lagged explicit step with integrated net
embedded-surface power. This is exact to floating-point roundoff; it is the
discrete enthalpy increment, not an assertion that lagged `cp` equals a fully
implicit enthalpy solve.
