# Synthetic calibration fixtures

**This build is not empirically calibrated. No probe logs were supplied.**

`fixtures/synthetic_calibration.json` contains deterministic assumed values in
the ranges from `PROJECT_PLAN.md`. It exists to lock integration behavior and
provide UI defaults. The values were authored, not inferred from meat, oven, or
probe observations. In particular, the wet-surface closure and 30°C anchor are
synthetic model choices.

A future calibration pipeline may fit convection, emissivity and initial
surface moisture by preset against leave-in probe logs. It must preserve a raw
log, train/validation split, fitted parameter bounds, solver version, and error
metrics before any empirical accuracy claim is made.
