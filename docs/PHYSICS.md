# Reference physics and validation

This document describes the implemented M1–M4 model. It is a numerical model,
not food-safety advice and not an empirically calibrated predictor.

## Material model

`roast_solver.properties` evaluates the Choi–Okos polynomial correlations for
water, protein, fat, and ash at the lagged cell temperature. The fixed baseline
composition is 75% water, 20% protein, 3% fat, and 2% ash by mass. Density uses
reciprocal-volume mixing; heat capacity and conductivity use mass-fraction
mixing. The optional 50–70 °C effective-heat-capacity bump is **off** because no
probe data was supplied to calibrate it.

## Geometry and discretization

Every preset produces the same `GridGeometry` contract: cell occupancy, signed
distance (negative inside), outward normals, per-cut-cell surface area, wetted
area fraction, and pan mask. Roast is a volume-scaled superellipsoid; slab is a
rounded box; ham is a blended teardrop; bird is a smooth union of body, breast,
legs, and wing stubs with an ellipsoidal cavity removed. Weight is converted to
volume using 1060 kg/m³ by default.

Interior heat flow is a conservative 7-point finite-volume stencil. Face
conductivity is the harmonic mean and forward Euler uses
`dt <= 0.82 h²/(6 max(alpha))`. Production arrays are Float32; analytic
calculations and strict conservation tests can use Float64.

### Embedded boundary

A boundary cell is an inside cell with one or more outside axial neighbors. A
staircase would assign one full square to every exposed face. Instead this model
uses the SDF normal to undo projection inflation:

```
A_cut = N_exposed h² / (|nx| + |ny| + |nz|)
```

The Robin flux also includes the cell-center-to-surface distance `max(-phi,
0.08h)` as a meat-conduction resistance. The resulting W/m² is multiplied by
`A_cut` and deposited as a cell-energy source. This construction conserves
energy exactly in the discrete update while representing curved area much more
accurately than raw exposed faces. Bottom cells selected by height and outward
normal form an insulated pan patch.

## Surface physics

Convection is 10 W/m²K in a still oven and 20 W/m²K with the fan toggle.
Radiation is evaluated as the exact previous-temperature linearization

```
h_rad = epsilon sigma (Twall² + Tsurface²)(Twall + Tsurface)
```

using absolute temperature. Each exposed cell owns a moisture reservoir
(default 0.24 kg/m²). A Lewis-analogy mass-transfer coefficient and Buck vapor
pressure produce a candidate evaporation rate. It is capped by remaining cell
moisture and 88% of incoming sensible/radiant heat. On depletion that cell alone
enters a dry-crust stage at 8% of the wet transfer rate. Covered mode sets
saturated air and evaporation to zero. These reservoir and stage constants are
engineering priors, not fitted values.

At pull, the probe location is frozen at the pull-time coldest cell. Rest swaps
to a 22 °C natural-convection/radiation boundary; foil lowers convection and
emissivity. The solver continues until the requested rest duration and reports
probe peak, overshoot, and time to peak.

Pasteurization is shown as equivalent seconds at 70 °C using z=7 °C:
`integral 10^((T_cold-70)/7) dt`. It is deliberately labelled an advanced,
model-dependent output; users must apply an appropriate organism/product
standard and safety margin.

## Validation and synthetic fixtures

Tests include:

- a 3-D Dirichlet-box eigenmode and resolution convergence;
- exact convective sphere series roots of `1 - lambda cot(lambda) = Bi`;
- plane-wall and infinite-cylinder series anchors;
- surface-energy versus discrete body-enthalpy accounting;
- radiation, per-cell reservoir depletion, pan insulation, and rest behavior.

At Bi=0.794 and Fourier number 0.08, the embedded sphere center error is about
0.12% with 14 cells/radius and 0.03% with 32 cells/radius; the corrected area
error is about 0.4% and 0.3%, respectively (small grid-alignment oscillations
are expected). This meets the plan's <1% center target without pretending that
one analytic case validates a real roast.

`fixtures/synthetic_calibration.json` documents two scenarios and
`fixtures/python_golden.json` stores deterministic model outputs used for
cross-language regressions. Both are prominently marked synthetic. A Bi > 30 high-h water-bath sphere is
also checked against the exact series to isolate interior conduction. No
Baldwin table values or real probe observations are copied or claimed here.
Real calibration requires traceable bath/table data and
leave-in probe logs.
